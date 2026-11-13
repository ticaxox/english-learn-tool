from __future__ import annotations

import hashlib
import json
from datetime import date, datetime, time, timedelta
from typing import Any
from uuid import UUID
from zoneinfo import ZoneInfo

from arq.connections import ArqRedis
from sqlalchemy import delete, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.errors import AppError
from app.models.ai import AiJob
from app.models.challenge import (
    ChallengeBossResult,
    ChallengeNode,
    ChallengeNodeProgress,
    ChallengePlanContext,
    DailyChallengePlan,
)
from app.models.identity import User
from app.models.learning import DailyPlan, DailyPlanWord, MemoryConfig, MemorySession
from app.models.practice import PracticeSession
from app.schemas.ai_tasks import ChallengePlanContext as AiChallengeContext
from app.schemas.ai_tasks import ChallengePlanOutput, ChallengePlanRequest
from app.schemas.challenge import (
    ChallengeBossSubmitResponse,
    ChallengeGenerateResponse,
    ChallengeHistoryItem,
    ChallengeHistoryResponse,
    ChallengeJobResponse,
    ChallengeNodeDetailResponse,
    ChallengeNodeResponse,
    ChallengePlanResponse,
    ChallengeStartResponse,
)
from app.schemas.learning import SessionCreateRequest
from app.schemas.practice import PracticeAnswerInput, PracticeCreateRequest, PracticeSubmitRequest
from app.services.ai_jobs import create_ai_job, get_user_job
from app.services.auth import utcnow
from app.services.gamification import award
from app.services.learning import ensure_daily_plan, local_date_for
from app.services.memory import start_session
from app.services.practice import create_practice_for_challenge, submit_practice_session
from app.services.wordbook_queue import WORDBOOK_QUEUE_NAME

CHALLENGE_LOCK_BASE = 20_261_023_009
CHALLENGE_CONTEXT_TTL_DAYS = 7
CHALLENGE_MAIN_NODE_LIMIT = 6
CHALLENGE_NODE_LIMIT = 7


def _context_hash(value: dict[str, Any]) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def _local_zone(user: User, settings: Settings) -> ZoneInfo:
    return ZoneInfo(user.profile.timezone if user.profile else settings.app_timezone)


def _expires_at(user: User, settings: Settings, local_day: date) -> datetime:
    zone = _local_zone(user, settings)
    next_day = local_day + timedelta(days=1)
    return datetime.combine(next_day, time.min, tzinfo=zone).astimezone(ZoneInfo("UTC"))


async def _load_plan(
    session: AsyncSession, user: User, challenge_id: UUID, *, lock: bool = False
) -> DailyChallengePlan:
    statement = select(DailyChallengePlan).where(
        DailyChallengePlan.id == challenge_id,
        DailyChallengePlan.user_id == user.id,
    )
    if lock:
        statement = statement.with_for_update()
    plan = await session.scalar(statement)
    if plan is None:
        raise AppError(
            status_code=404,
            code="CHALLENGE_NOT_FOUND",
            message="The daily challenge was not found.",
        )
    return plan


async def _load_node(
    session: AsyncSession,
    user: User,
    challenge_id: UUID,
    node_id: UUID,
    *,
    lock: bool = False,
) -> tuple[DailyChallengePlan, ChallengeNode, ChallengeNodeProgress | None]:
    plan = await _load_plan(session, user, challenge_id, lock=lock)
    statement = select(ChallengeNode).where(
        ChallengeNode.id == node_id,
        ChallengeNode.plan_id == plan.id,
    )
    if lock:
        statement = statement.with_for_update()
    node = await session.scalar(statement)
    if node is None:
        raise AppError(
            status_code=404,
            code="CHALLENGE_NODE_NOT_FOUND",
            message="The challenge node was not found.",
        )
    progress = await session.scalar(
        select(ChallengeNodeProgress).where(
            ChallengeNodeProgress.node_id == node.id,
            ChallengeNodeProgress.user_id == user.id,
        )
    )
    return plan, node, progress


async def _plan_words(session: AsyncSession, plan: DailyChallengePlan) -> dict[UUID, DailyPlanWord]:
    rows = list(
        (
            await session.scalars(
                select(DailyPlanWord).where(DailyPlanWord.plan_id == plan.daily_plan_id)
            )
        ).all()
    )
    return {row.entry_id: row for row in rows}


async def _node_complete(
    session: AsyncSession,
    plan: DailyChallengePlan,
    node: ChallengeNode,
    progress: ChallengeNodeProgress,
    words: dict[UUID, DailyPlanWord],
) -> bool:
    entry_ids = [UUID(value) for value in node.word_entry_ids]
    if node.node_type in {"REVIEW", "NEW_WORDS"}:
        return bool(entry_ids) and all(
            words.get(entry_id) is not None and words[entry_id].completed_at is not None
            for entry_id in entry_ids
        )
    if node.node_type == "WORD_DRILL":
        if progress.memory_session_id is None:
            return False
        memory = await session.get(MemorySession, progress.memory_session_id)
        return memory is not None and memory.status == "completed"
    if node.node_type == "AI_PRACTICE":
        if progress.practice_session_id is None:
            return False
        practice = await session.get(PracticeSession, progress.practice_session_id)
        return practice is not None and practice.status == "submitted"
    if node.node_type == "BOSS":
        result = await session.scalar(
            select(ChallengeBossResult.id).where(ChallengeBossResult.plan_id == plan.id)
        )
        if result is not None:
            return True
        if progress.practice_session_id is None:
            return False
        practice = await session.get(PracticeSession, progress.practice_session_id)
        return practice is not None and practice.status == "submitted"
    return False


async def _add_side_stop(
    session: AsyncSession, plan: DailyChallengePlan, nodes: list[ChallengeNode]
) -> ChallengeNode | None:
    """One optional side stop, built from the words the plan already carries.

    The generator is free to leave the side path out, but a trail with no
    shortcut reads as a corridor. Nothing new is asked of the learner: the
    stop just re-drills ten of today's own words, and it never blocks the
    main line.
    """
    words: list[str] = []
    for node in nodes:
        for entry_id in node.word_entry_ids or []:
            if entry_id not in words:
                words.append(str(entry_id))
        if len(words) >= 10:
            break
    if not words:
        return None
    side = ChallengeNode(
        plan_id=plan.id,
        client_key="side-stop",
        node_type="OPTIONAL_SIDE",
        order_index=max(node.order_index for node in nodes) + 10,
        title="支线 · 顺路再练一组",
        description="路边的小摊：用今天这几个词多做一组，不算进主线。",
        estimated_minutes=5,
        word_entry_ids=words[:10],
        practice_spec={"drill_mode": "choice"},
        optional=True,
    )
    session.add(side)
    await session.flush()
    session.add(
        ChallengeNodeProgress(
            node_id=side.id,
            plan_id=plan.id,
            user_id=plan.user_id,
            status="unlocked",
        )
    )
    await session.flush()
    return side


async def _sync_plan(
    session: AsyncSession, plan: DailyChallengePlan, user: User, settings: Settings
) -> None:
    nodes = list(
        (
            await session.scalars(
                select(ChallengeNode)
                .where(ChallengeNode.plan_id == plan.id)
                .order_by(ChallengeNode.order_index.asc())
            )
        ).all()
    )
    if not nodes:
        return
    if plan.status == "ready" and not any(node.optional for node in nodes):
        side = await _add_side_stop(session, plan, nodes)
        if side is not None:
            nodes = sorted([*nodes, side], key=lambda node: node.order_index)
    progress_rows = list(
        (
            await session.scalars(
                select(ChallengeNodeProgress)
                .where(ChallengeNodeProgress.plan_id == plan.id)
                .with_for_update()
            )
        ).all()
    )
    progress = {row.node_id: row for row in progress_rows}
    words = await _plan_words(session, plan)
    changed = False
    for node in nodes:
        row = progress.get(node.id)
        if row is None:
            row = ChallengeNodeProgress(
                node_id=node.id,
                plan_id=plan.id,
                user_id=user.id,
                status="unlocked" if node.optional or node.order_index == 1 else "locked",
            )
            session.add(row)
            progress[node.id] = row
            changed = True
        if row.status != "completed" and await _node_complete(session, plan, node, row, words):
            row.status = "completed"
            row.completed_at = row.completed_at or utcnow()
            row.stars = await _node_stars(session, node, row)
            changed = True
            await award(
                session,
                settings,
                user,
                source_type="boss" if node.node_type == "BOSS" else "challenge_node",
                source_id=str(node.id),
            )

    main_nodes = [node for node in nodes if not node.optional]
    for index, node in enumerate(main_nodes):
        row = progress[node.id]
        if row.status == "completed":
            if index + 1 < len(main_nodes):
                next_row = progress[main_nodes[index + 1].id]
                if next_row.status == "locked":
                    next_row.status = "unlocked"
                    changed = True
        elif index == 0 and row.status == "locked":
            row.status = "unlocked"
            changed = True
    for node in nodes:
        if node.optional and progress[node.id].status == "locked":
            progress[node.id].status = "unlocked"
            changed = True

    today = local_date_for(settings, user)
    if plan.local_date < today and plan.status not in {"completed", "expired"}:
        plan.status = "expired"
        changed = True
    if all(progress[node.id].status == "completed" for node in main_nodes):
        if plan.status != "completed":
            plan.status = "completed"
            plan.challenge_completed_at = plan.challenge_completed_at or utcnow()
            changed = True
    if changed:
        await session.commit()


async def _node_stars(
    session: AsyncSession, node: ChallengeNode, progress: ChallengeNodeProgress
) -> int:
    """3 for a flawless finish, 2 when a linked set was answered well, 1 otherwise."""
    if progress.practice_session_id is None:
        return 1
    practice = await session.get(PracticeSession, progress.practice_session_id)
    if practice is None:
        return 1
    if practice.wrong_count == 0:
        return 3 if node.node_type == "BOSS" else 2
    return 1


async def _node_response(
    session: AsyncSession,
    plan: DailyChallengePlan,
    node: ChallengeNode,
    progress: ChallengeNodeProgress | None,
) -> ChallengeNodeResponse:
    if progress is None:
        status = "unlocked" if node.optional or node.order_index == 1 else "locked"
        resource_type = None
        resource_id = None
    else:
        status = progress.status
        resource_type = "memory" if progress.memory_session_id else None
        resource_id = progress.memory_session_id
        if progress.practice_session_id:
            resource_type = "practice"
            resource_id = progress.practice_session_id
    return ChallengeNodeResponse(
        id=node.id,
        client_key=node.client_key,
        node_type=node.node_type,
        order_index=node.order_index,
        title=node.title,
        description=node.description,
        estimated_minutes=node.estimated_minutes,
        word_entry_ids=[UUID(value) for value in node.word_entry_ids],
        practice_spec=node.practice_spec,
        optional=node.optional,
        status=status,
        resource_type=resource_type,
        resource_id=resource_id,
        started_at=progress.started_at if progress else None,
        completed_at=progress.completed_at if progress else None,
        stars=progress.stars if progress else 0,
        error_code=progress.error_code if progress else None,
        error_message=progress.error_message if progress else None,
    )


NODE_TYPE_LABELS = {
    "REVIEW": "复习",
    "NEW_WORDS": "学习新词",
    "WORD_DRILL": "专项巩固",
    "AI_PRACTICE": "AI 练习",
    "BOSS": "终点挑战",
    "OPTIONAL_SIDE": "可选支线",
}
PRACTICE_TYPE_LABELS = {
    "fill_blank": "填空",
    "reading": "阅读",
    "translation": "翻译",
    "writing": "作文",
}
STATUS_LABELS = {
    "locked": "未解锁",
    "unlocked": "已解锁",
    "in_progress": "进行中",
    "completed": "已完成",
    "failed": "失败",
}


def _node_question_type(node: ChallengeNode) -> str:
    if node.node_type in {"REVIEW", "NEW_WORDS"}:
        return "翻卡记忆"
    if node.node_type == "WORD_DRILL":
        return "拼写" if node.practice_spec.get("drill_mode") == "spelling" else "选择"
    spec_type = node.practice_spec.get("practice_type")
    if isinstance(spec_type, str):
        return PRACTICE_TYPE_LABELS.get(spec_type, spec_type)
    if node.node_type == "BOSS":
        return "综合挑战"
    if node.node_type == "OPTIONAL_SIDE":
        return "可选练习"
    return "综合练习"


def _memory_module(node: ChallengeNode) -> str:
    if node.node_type == "WORD_DRILL":
        return "spelling" if node.practice_spec.get("drill_mode") == "spelling" else "choice"
    return "flashcard"


def _node_link(
    plan: DailyChallengePlan, node: ChallengeNode, response: ChallengeNodeResponse
) -> str:
    if response.resource_type == "practice" and response.resource_id:
        return f"/practice/{response.resource_id}"
    if response.resource_type == "memory" and response.resource_id:
        return (
            f"/memory?sessionId={response.resource_id}"
            f"&module={_memory_module(node)}&challengeId={plan.id}&nodeId={node.id}"
        )
    return "待开始"


def build_challenge_map_dsl(
    plan: DailyChallengePlan,
    nodes: list[ChallengeNode],
    responses: list[ChallengeNodeResponse],
) -> str:
    """Serialise the map as the Markdown-like language the page renders."""

    response_by_id = {response.id: response for response in responses}
    main = sorted((node for node in nodes if not node.optional), key=lambda n: n.order_index)
    optional = sorted((node for node in nodes if node.optional), key=lambda n: n.order_index)
    main_index = {node.id: index for index, node in enumerate(main)}

    def next_main(node: ChallengeNode) -> ChallengeNode | None:
        index = main_index.get(node.id, -1)
        candidate = index + 1
        return main[candidate] if 0 <= candidate < len(main) else None

    def optional_parent(node: ChallengeNode) -> ChallengeNode | None:
        earlier = [item for item in main if item.order_index < node.order_index]
        return earlier[-1] if earlier else (main[0] if main else None)

    lines = [f"# {plan.title or '今天的学习地图'}"]
    if plan.summary:
        lines.append(f"> {plan.summary.replace(chr(10), ' ').strip()}")
    lines.append("")

    ordered = main + optional
    for node in ordered:
        response = response_by_id.get(node.id)
        status = response.status if response is not None else "locked"
        if node.optional:
            parent = optional_parent(node)
            previous = parent.client_key if parent else "开始"
            following = next_main(parent).client_key if parent and next_main(parent) else "终点"
        else:
            previous_node = main[main_index[node.id] - 1] if main_index[node.id] > 0 else None
            previous = previous_node.client_key if previous_node else "开始"
            following = next_main(node).client_key if next_main(node) else "终点"
        link = _node_link(plan, node, response) if response is not None else "待开始"
        lines.extend(
            [
                f"## [{node.client_key}] {node.title}",
                f"- 类型: {NODE_TYPE_LABELS.get(node.node_type, node.node_type)}",
                f"- 题目类型: {_node_question_type(node)}",
                f"- 状态: {STATUS_LABELS.get(status, status)}",
                f"- 星数: {response.stars if response is not None else 0}",
                f"- 时长: {node.estimated_minutes} 分钟",
                f"- 说明: {node.description.replace(chr(10), ' ').strip()}",
                f"- 链接: {link}",
                f"- 前置: {previous}",
                f"- 分支: {following}",
                f"- 可选: {'是' if node.optional else '否'}",
                "",
            ]
        )
    return "\n".join(lines).strip()


async def _plan_response(
    session: AsyncSession, plan: DailyChallengePlan, user: User, settings: Settings
) -> ChallengePlanResponse:
    nodes = list(
        (
            await session.scalars(
                select(ChallengeNode)
                .where(ChallengeNode.plan_id == plan.id)
                .order_by(ChallengeNode.order_index.asc())
            )
        ).all()
    )
    progress_rows = list(
        (
            await session.scalars(
                select(ChallengeNodeProgress).where(ChallengeNodeProgress.plan_id == plan.id)
            )
        ).all()
    )
    progress = {row.node_id: row for row in progress_rows}
    main = [node for node in nodes if not node.optional]
    completed = sum(progress[node.id].status == "completed" for node in main if node.id in progress)
    node_responses = [
        await _node_response(session, plan, node, progress.get(node.id)) for node in nodes
    ]
    return ChallengePlanResponse(
        id=plan.id,
        local_date=plan.local_date,
        status=plan.status,
        title=plan.title,
        summary=plan.summary,
        target_minutes=plan.target_minutes,
        daily_plan_id=plan.daily_plan_id,
        ai_job_id=plan.ai_job_id,
        generated_at=plan.generated_at,
        locked_at=plan.locked_at,
        challenge_completed_at=plan.challenge_completed_at,
        expires_at=plan.expires_at,
        error_code=plan.error_code,
        error_message=plan.error_message,
        main_completed=completed,
        main_total=len(main),
        map_dsl=build_challenge_map_dsl(plan, nodes, node_responses),
        nodes=node_responses,
    )


async def _build_context(
    session: AsyncSession, user: User, settings: Settings, plan: DailyChallengePlan
) -> AiChallengeContext:
    daily_plan = await session.get(DailyPlan, plan.daily_plan_id)
    if daily_plan is None:
        raise AppError(
            status_code=409,
            code="CHALLENGE_DAILY_PLAN_MISSING",
            message="The daily study plan is unavailable.",
        )
    rows = list(
        (
            await session.scalars(
                select(DailyPlanWord)
                .where(DailyPlanWord.plan_id == daily_plan.id)
                .order_by(DailyPlanWord.position.asc())
            )
        ).all()
    )
    new_entry_ids = [row.entry_id for row in rows if row.reason == "new"]
    due_entry_ids = [row.entry_id for row in rows if row.reason == "due"]
    if not new_entry_ids and not due_entry_ids:
        raise AppError(
            status_code=409,
            code="CHALLENGE_DAILY_PLAN_EMPTY",
            message="The daily study plan has no challenge entries.",
        )
    memory_config = await session.get(MemoryConfig, user.id)
    preferences = (memory_config.preferences or {}) if memory_config else {}
    challenge_prefs = preferences.get("challenge", {}) if isinstance(preferences, dict) else {}

    def _kept(value: object, defaults: list[str]) -> list[str]:
        if not isinstance(value, list):
            return list(defaults)
        chosen = [item for item in defaults if item in value]
        return chosen or list(defaults)

    return AiChallengeContext(
        local_date=plan.local_date.isoformat(),
        target_minutes=plan.target_minutes,
        new_entry_ids=new_entry_ids,
        due_entry_ids=due_entry_ids,
        allowed_practice_types=_kept(
            challenge_prefs.get("practiceTypes"),
            ["fill_blank", "reading", "translation", "writing"],
        ),
        allowed_drill_modes=_kept(
            challenge_prefs.get("drillModes"), ["choice", "spelling", "flashcard"]
        ),
        plan_id=plan.id,
        wordbook_id=plan.wordbook_id,
        target_new_words=len(new_entry_ids),
    )


async def _enqueue_job(pool: ArqRedis, job_id: UUID) -> None:
    await pool.enqueue_job(
        "process_ai_job",
        str(job_id),
        _job_id=f"ai:{job_id}",
        _queue_name=WORDBOOK_QUEUE_NAME,
    )


async def _mark_generation_failed(
    session: AsyncSession, plan: DailyChallengePlan, code: str, message: str
) -> None:
    plan.status = "failed"
    plan.error_code = code[:64]
    plan.error_message = message[:500]
    await session.commit()


async def generate_today(
    session: AsyncSession,
    pool: ArqRedis,
    user: User,
    settings: Settings,
) -> ChallengeGenerateResponse:
    now = utcnow()
    local_date = local_date_for(settings, user, now=now)
    daily_plan = await ensure_daily_plan(session, user, settings=settings, now=now)
    await session.execute(
        text("SELECT pg_advisory_xact_lock(:key)"),
        {"key": CHALLENGE_LOCK_BASE + (user.id.int % 1_000_000)},
    )
    plan = await session.scalar(
        select(DailyChallengePlan)
        .where(
            DailyChallengePlan.user_id == user.id,
            DailyChallengePlan.local_date == local_date,
        )
        .with_for_update()
    )
    if plan is not None and plan.status in {"ready", "completed"}:
        return ChallengeGenerateResponse(
            challenge_id=plan.id,
            status=plan.status,
            job_id=plan.ai_job_id,
            status_url=f"{settings.api_v1_prefix}/challenges/jobs/{plan.ai_job_id}"
            if plan.ai_job_id
            else None,
            replayed=True,
        )
    if plan is not None and plan.status == "generating" and plan.ai_job_id is not None:
        return ChallengeGenerateResponse(
            challenge_id=plan.id,
            status=plan.status,
            job_id=plan.ai_job_id,
            status_url=f"{settings.api_v1_prefix}/challenges/jobs/{plan.ai_job_id}",
            replayed=True,
        )
    if plan is None:
        plan = DailyChallengePlan(
            user_id=user.id,
            local_date=local_date,
            daily_plan_id=daily_plan.id,
            wordbook_id=daily_plan.wordbook_id,
            target_minutes=daily_plan.study_minutes_target,
            expires_at=_expires_at(user, settings, local_date),
            status="generating",
            generation_attempts=0,
        )
        session.add(plan)
        await session.flush()
    else:
        plan.daily_plan_id = daily_plan.id
        plan.wordbook_id = daily_plan.wordbook_id
        plan.target_minutes = daily_plan.study_minutes_target
        plan.expires_at = _expires_at(user, settings, local_date)
        plan.status = "generating"
        plan.error_code = None
        plan.error_message = None
    plan.generation_attempts += 1
    context = await _build_context(session, user, settings, plan)
    context_data = context.model_dump(mode="json")
    context_hash = _context_hash(context_data)
    snapshot = await session.scalar(
        select(ChallengePlanContext).where(ChallengePlanContext.plan_id == plan.id)
    )
    if snapshot is None:
        snapshot = ChallengePlanContext(
            plan_id=plan.id,
            user_id=user.id,
            context=context_data,
            content_hash=context_hash,
            expires_at=now + timedelta(days=CHALLENGE_CONTEXT_TTL_DAYS),
        )
        session.add(snapshot)
    else:
        snapshot.context = context_data
        snapshot.content_hash = context_hash
        snapshot.expires_at = now + timedelta(days=CHALLENGE_CONTEXT_TTL_DAYS)
    request = ChallengePlanRequest(task_type="challenge_plan", context=context)
    job, _ = await create_ai_job(
        session,
        pool,
        user,
        settings,
        request,
        idempotency_key=f"challenge:{plan.id}:{plan.generation_attempts}",
        commit=False,
    )
    plan.ai_job_id = job.id
    await session.commit()
    try:
        await _enqueue_job(pool, job.id)
    except Exception as exc:
        await _mark_generation_failed(
            session, plan, "CHALLENGE_QUEUE_UNAVAILABLE", "The challenge queue is unavailable."
        )
        raise AppError(
            status_code=503,
            code="CHALLENGE_QUEUE_UNAVAILABLE",
            message="The challenge task queue is unavailable.",
            headers={"Retry-After": "5"},
        ) from exc
    return ChallengeGenerateResponse(
        challenge_id=plan.id,
        status="generating",
        job_id=job.id,
        status_url=f"{settings.api_v1_prefix}/challenges/jobs/{job.id}",
    )


async def get_today(session: AsyncSession, user: User, settings: Settings) -> ChallengePlanResponse:
    local_date = local_date_for(settings, user)
    plan = await session.scalar(
        select(DailyChallengePlan).where(
            DailyChallengePlan.user_id == user.id,
            DailyChallengePlan.local_date == local_date,
        )
    )
    if plan is None:
        raise AppError(
            status_code=404,
            code="CHALLENGE_NOT_GENERATED",
            message="Today's challenge has not been generated.",
        )
    await _sync_plan(session, plan, user, settings)
    await session.refresh(plan)
    return await _plan_response(session, plan, user, settings)


async def get_challenge(
    session: AsyncSession, user: User, settings: Settings, challenge_id: UUID
) -> ChallengePlanResponse:
    plan = await _load_plan(session, user, challenge_id)
    await _sync_plan(session, plan, user, settings)
    await session.refresh(plan)
    return await _plan_response(session, plan, user, settings)


async def get_node_detail(
    session: AsyncSession,
    user: User,
    settings: Settings,
    challenge_id: UUID,
    node_id: UUID,
) -> ChallengeNodeDetailResponse:
    plan = await _load_plan(session, user, challenge_id)
    await _sync_plan(session, plan, user, settings)
    _, node, progress = await _load_node(session, user, challenge_id, node_id)
    node_response = await _node_response(session, plan, node, progress)
    if node_response.status == "completed":
        actions = ["view_result"]
    elif node_response.status == "in_progress":
        actions = ["resume"]
    elif node_response.status in {"unlocked", "failed"}:
        actions = ["start"]
    else:
        actions = []
    return ChallengeNodeDetailResponse(
        challenge_id=plan.id,
        node=node_response,
        allowed_actions=actions,
    )


async def _mark_node_failed(
    session: AsyncSession, progress: ChallengeNodeProgress, code: str, message: str
) -> None:
    progress.status = "failed"
    progress.error_code = code[:64]
    progress.error_message = message[:500]
    await session.commit()


def _module_for_node(node: ChallengeNode) -> str:
    if node.node_type == "WORD_DRILL":
        mode = node.practice_spec.get("drill_mode")
        if mode == "spelling":
            return "spelling"
        if mode == "flashcard":
            return "flashcard"
        return "choice"
    if node.node_type == "NEW_WORDS":
        return "flashcard"
    return "choice"


def _practice_payload(
    node: ChallengeNode, plan: DailyChallengePlan, words: dict[UUID, DailyPlanWord]
) -> PracticeCreateRequest:
    spec = node.practice_spec if isinstance(node.practice_spec, dict) else {}
    practice_type = str(spec.get("practice_type", "fill_blank"))
    count = int(spec.get("count", 5))
    source = spec.get("source")
    if source not in {"today_new", "today_review", "memory_mistakes", "whole_book", "difficulty"}:
        has_new = any(word.reason == "new" for word in words.values())
        source = "today_new" if has_new else "today_review"
    if node.node_type == "BOSS":
        practice_type = "fill_blank"
        if count not in {5, 10}:
            count = 5
    try:
        return PracticeCreateRequest(
            practice_type=practice_type,
            source=source,
            count=count,
            wordbook_id=plan.wordbook_id,
        )
    except Exception as exc:
        raise AppError(
            status_code=409,
            code="CHALLENGE_NODE_PRACTICE_INVALID",
            message="The challenge node practice parameters are invalid.",
        ) from exc


async def start_node(
    session: AsyncSession,
    pool: ArqRedis,
    user: User,
    settings: Settings,
    challenge_id: UUID,
    node_id: UUID,
) -> ChallengeStartResponse:
    plan = await _load_plan(session, user, challenge_id)
    await _sync_plan(session, plan, user, settings)
    plan, node, progress = await _load_node(session, user, challenge_id, node_id, lock=True)
    if plan.status in {"generating", "failed", "expired"}:
        raise AppError(
            status_code=409,
            code="CHALLENGE_NOT_STARTABLE",
            message="The challenge is not startable.",
        )
    if plan.local_date != local_date_for(settings, user):
        raise AppError(
            status_code=409,
            code="CHALLENGE_READ_ONLY",
            message="A past challenge is read-only.",
        )
    if progress is None:
        progress = ChallengeNodeProgress(
            node_id=node.id,
            plan_id=plan.id,
            user_id=user.id,
            status="unlocked" if node.optional or node.order_index == 1 else "locked",
        )
        session.add(progress)
        await session.flush()
    if progress.status == "locked":
        raise AppError(
            status_code=409,
            code="CHALLENGE_NODE_LOCKED",
            message="Complete the previous main node first.",
        )
    if progress.status == "completed":
        resource_type = "practice" if progress.practice_session_id else "memory"
        resource_id = progress.practice_session_id or progress.memory_session_id
        return ChallengeStartResponse(
            challenge_id=plan.id,
            node_id=node.id,
            status="completed",
            resource_type=resource_type if resource_id else None,
            resource_id=resource_id,
            message="The node is already complete.",
        )
    if progress.status == "in_progress" and (
        progress.memory_session_id is not None or progress.practice_session_id is not None
    ):
        resource_type = "practice" if progress.practice_session_id else "memory"
        resource_id = progress.practice_session_id or progress.memory_session_id
        return ChallengeStartResponse(
            challenge_id=plan.id,
            node_id=node.id,
            status="in_progress",
            resource_type=resource_type,
            resource_id=resource_id,
            message="The node task can be resumed.",
        )
    progress.status = "in_progress"
    progress.started_at = progress.started_at or utcnow()
    progress.error_code = None
    progress.error_message = None
    await session.flush()
    words = await _plan_words(session, plan)

    if node.node_type in {"REVIEW", "NEW_WORDS", "WORD_DRILL", "OPTIONAL_SIDE"}:
        try:
            memory = await start_session(
                session,
                user,
                settings=settings,
                payload=SessionCreateRequest(
                    wordbook_id=plan.wordbook_id,
                    module=_module_for_node(node),
                    limit=min(200, max(1, len(node.word_entry_ids) or 20)),
                ),
            )
        except AppError:
            await session.rollback()
            plan, node, progress = await _load_node(session, user, challenge_id, node_id, lock=True)
            if progress is not None:
                await _mark_node_failed(
                    session,
                    progress,
                    "CHALLENGE_NODE_START_FAILED",
                    "The node task could not be started.",
                )
            raise
        progress.memory_session_id = memory.session_id
        await session.commit()
        return ChallengeStartResponse(
            challenge_id=plan.id,
            node_id=node.id,
            status="in_progress",
            resource_type="memory",
            resource_id=memory.session_id,
            message="The memory task is ready.",
        )

    try:
        payload = _practice_payload(node, plan, words)
        practice, job_id = await create_practice_for_challenge(
            session,
            pool,
            user,
            settings,
            payload,
            idempotency_key=f"challenge:{node.id}",
        )
        progress.practice_session_id = practice.id
        await session.commit()
        if job_id is not None:
            try:
                await _enqueue_job(pool, job_id)
            except Exception as exc:
                await _mark_node_failed(
                    session,
                    progress,
                    "CHALLENGE_QUEUE_UNAVAILABLE",
                    "The practice queue is unavailable.",
                )
                raise AppError(
                    status_code=503,
                    code="CHALLENGE_QUEUE_UNAVAILABLE",
                    message="The challenge task queue is unavailable.",
                    headers={"Retry-After": "5"},
                ) from exc
        return ChallengeStartResponse(
            challenge_id=plan.id,
            node_id=node.id,
            status="in_progress",
            resource_type="practice",
            resource_id=practice.id,
            job_id=job_id,
            message="The practice task is ready.",
        )
    except AppError:
        await session.rollback()
        plan, node, progress = await _load_node(session, user, challenge_id, node_id, lock=True)
        if progress is not None and progress.status != "completed":
            await _mark_node_failed(
                session,
                progress,
                "CHALLENGE_NODE_START_FAILED",
                "The node task could not be started.",
            )
        raise


def _answer_digest(answers: list[dict[str, str]]) -> str:
    normalized = sorted((item.get("question_id", ""), item.get("answer", "")) for item in answers)
    return hashlib.sha256(
        json.dumps(normalized, ensure_ascii=False, separators=(",", ":")).encode()
    ).hexdigest()


async def submit_boss(
    session: AsyncSession,
    pool: ArqRedis,
    user: User,
    settings: Settings,
    challenge_id: UUID,
    node_id: UUID,
    answers: list[dict[str, str]],
    *,
    idempotency_key: str,
) -> ChallengeBossSubmitResponse:
    plan = await _load_plan(session, user, challenge_id)
    await _sync_plan(session, plan, user, settings)
    plan, node, progress = await _load_node(session, user, challenge_id, node_id, lock=True)
    if node.node_type != "BOSS":
        raise AppError(
            status_code=409,
            code="CHALLENGE_NODE_NOT_BOSS",
            message="Only the final challenge node can be submitted here.",
        )
    if plan.local_date != local_date_for(settings, user):
        raise AppError(
            status_code=409,
            code="CHALLENGE_READ_ONLY",
            message="A past challenge is read-only.",
        )
    if progress is None or progress.practice_session_id is None:
        raise AppError(
            status_code=409,
            code="CHALLENGE_NODE_NOT_STARTED",
            message="Start the final challenge before submitting answers.",
        )
    existing = await session.scalar(
        select(ChallengeBossResult).where(ChallengeBossResult.plan_id == plan.id)
    )
    if existing is not None:
        if existing.idempotency_key != idempotency_key:
            raise AppError(
                status_code=409,
                code="CHALLENGE_BOSS_ALREADY_SUBMITTED",
                message="The final challenge has already been submitted.",
            )
        return ChallengeBossSubmitResponse(
            challenge_id=plan.id,
            node_id=node.id,
            status="completed",
            score=existing.score,
            completed=True,
            submission_id=existing.practice_submission_id,
            result={"question_stats": existing.question_stats},
            message="The final challenge was already submitted.",
        )
    if len(answers) < 5 or len(answers) > 10:
        raise AppError(
            status_code=422,
            code="CHALLENGE_BOSS_ANSWER_COUNT",
            message="The final challenge requires 5 to 10 answers.",
        )
    answer_values = [
        answer.model_dump() if isinstance(answer, PracticeAnswerInput) else answer
        for answer in answers
    ]
    request = PracticeSubmitRequest(
        answers=[PracticeAnswerInput.model_validate(answer) for answer in answer_values]
    )
    result = await submit_practice_session(
        session,
        pool,
        user,
        settings,
        progress.practice_session_id,
        request,
        idempotency_key=f"challenge-boss:{plan.id}",
    )
    if result.status == "failed":
        progress.status = "failed"
        progress.error_code = result.error_code or "CHALLENGE_BOSS_SUBMISSION_FAILED"
        progress.error_message = result.error_message or "The final challenge submission failed."
        await session.commit()
        return ChallengeBossSubmitResponse(
            challenge_id=plan.id,
            node_id=node.id,
            status="failed",
            completed=False,
            error_code=progress.error_code,
            error_message=progress.error_message,
            message="The final challenge submission failed.",
        )
    if result.status == "scoring":
        await session.commit()
        return ChallengeBossSubmitResponse(
            challenge_id=plan.id,
            node_id=node.id,
            status="scoring",
            completed=False,
            message="The final challenge is being scored.",
        )
    result_data = result.result.model_dump(mode="json") if result.result else {}
    score = result_data.get("score")
    questions = result_data.get("questions", [])
    question_stats = {
        "total": len(questions),
        "correct": sum(1 for item in questions if item.get("is_correct") is True),
        "mistakes": sum(1 for item in questions if item.get("is_mistake") is True),
    }
    boss_result = ChallengeBossResult(
        plan_id=plan.id,
        node_id=node.id,
        user_id=user.id,
        practice_submission_id=result.submission_id,
        idempotency_key=idempotency_key,
        score=float(score) if score is not None else None,
        question_stats=question_stats,
        answer_digest=_answer_digest(answer_values),
        submitted_at=utcnow(),
    )
    session.add(boss_result)
    progress.status = "completed"
    progress.completed_at = utcnow()
    progress.error_code = None
    progress.error_message = None
    await session.flush()
    await _sync_plan(session, plan, user, settings)
    return ChallengeBossSubmitResponse(
        challenge_id=plan.id,
        node_id=node.id,
        status="completed",
        score=boss_result.score,
        completed=True,
        submission_id=boss_result.practice_submission_id,
        result={"question_stats": question_stats},
        message="The final challenge is complete.",
    )


async def get_history(
    session: AsyncSession,
    user: User,
    settings: Settings,
    *,
    limit: int = 20,
    offset: int = 0,
) -> ChallengeHistoryResponse:
    plans = list(
        (
            await session.scalars(
                select(DailyChallengePlan)
                .where(DailyChallengePlan.user_id == user.id)
                .order_by(DailyChallengePlan.local_date.desc(), DailyChallengePlan.id.desc())
                .offset(offset)
                .limit(limit + 1)
            )
        ).all()
    )
    has_more = len(plans) > limit
    visible = plans[:limit]
    items: list[ChallengeHistoryItem] = []
    for plan in visible:
        await _sync_plan(session, plan, user, settings)
        await session.refresh(plan)
        response = await _plan_response(session, plan, user, settings)
        items.append(
            ChallengeHistoryItem(
                id=response.id,
                local_date=response.local_date,
                status=response.status,
                title=response.title,
                summary=response.summary,
                target_minutes=response.target_minutes,
                main_completed=response.main_completed,
                main_total=response.main_total,
                challenge_completed_at=response.challenge_completed_at,
            )
        )
    return ChallengeHistoryResponse(
        items=items,
        next_cursor=str(offset + limit) if has_more else None,
        has_more=has_more,
    )


async def get_challenge_job(
    session: AsyncSession, user: User, job_id: UUID
) -> ChallengeJobResponse:
    job = await get_user_job(session, user, job_id)
    plan = await session.scalar(
        select(DailyChallengePlan).where(
            DailyChallengePlan.user_id == user.id,
            DailyChallengePlan.ai_job_id == job_id,
        )
    )
    return ChallengeJobResponse(
        job_id=job.id,
        challenge_id=plan.id if plan else None,
        status=job.status,
        error_code=job.error.code if job.error else None,
        error_message=job.error.message if job.error else None,
        retryable=bool(job.error and job.error.retryable),
    )


async def materialize_challenge_plan(session: AsyncSession, job: AiJob, settings: Settings) -> None:
    plan_id = job.input_context.get("plan_id")
    if not plan_id:
        return
    plan = await session.get(DailyChallengePlan, UUID(str(plan_id)), with_for_update=True)
    if plan is None or plan.ai_job_id != job.id or plan.status in {"ready", "completed"}:
        return
    output = ChallengePlanOutput.model_validate(job.result or {})
    context = AiChallengeContext.model_validate(job.input_context)
    await session.execute(
        delete(ChallengeNodeProgress).where(ChallengeNodeProgress.plan_id == plan.id)
    )
    await session.execute(delete(ChallengeNode).where(ChallengeNode.plan_id == plan.id))
    main_nodes = sorted(
        (node for node in output.nodes if node.node_type != "OPTIONAL_SIDE"),
        key=lambda node: node.order or 0,
    )
    optional_nodes = [node for node in output.nodes if node.node_type == "OPTIONAL_SIDE"]
    nodes_to_create = main_nodes + optional_nodes
    created: list[tuple[ChallengeNode, bool]] = []
    for index, node in enumerate(nodes_to_create, start=1):
        node_type = node.node_type
        practice_spec: dict[str, Any] = {}
        if node_type in {"AI_PRACTICE", "BOSS"}:
            practice_spec = {
                "practice_type": node.practice_type,
                "count": node.practice_count,
                "source": (
                    "whole_book"
                    if node_type == "BOSS"
                    else "today_new"
                    if any(
                        str(entry_id) in {str(value) for value in context.new_entry_ids}
                        for entry_id in node.word_entry_ids
                    )
                    else "today_review"
                ),
            }
        elif node_type == "WORD_DRILL":
            practice_spec = {"drill_mode": node.drill_mode}
        row = ChallengeNode(
            plan_id=plan.id,
            client_key=node.client_key or node.id,
            node_type=node_type,
            order_index=node.order or index,
            title=node.title,
            description=node.description,
            estimated_minutes=node.estimated_minutes,
            word_entry_ids=[str(entry_id) for entry_id in node.word_entry_ids],
            practice_spec=practice_spec,
            optional=node.optional,
        )
        session.add(row)
        await session.flush()
        created.append((row, node.optional))
    for index, (row, optional) in enumerate(created):
        status = "unlocked" if optional or index == 0 else "locked"
        session.add(
            ChallengeNodeProgress(
                node_id=row.id,
                plan_id=plan.id,
                user_id=plan.user_id,
                status=status,
            )
        )
    plan.title = output.title
    plan.summary = output.summary
    plan.status = "ready"
    plan.generated_at = utcnow()
    plan.locked_at = utcnow()
    plan.error_code = None
    plan.error_message = None


async def mark_challenge_failed(session: AsyncSession, job: AiJob) -> None:
    plan_id = job.input_context.get("plan_id")
    if not plan_id:
        return
    plan = await session.get(DailyChallengePlan, UUID(str(plan_id)), with_for_update=True)
    if plan is None or plan.status in {"ready", "completed"}:
        return
    plan.status = "failed"
    plan.error_code = (job.error_code or "CHALLENGE_GENERATION_FAILED")[:64]
    plan.error_message = "The daily challenge could not be generated. Please retry."
    await session.execute(
        delete(ChallengeNodeProgress).where(ChallengeNodeProgress.plan_id == plan.id)
    )
    await session.execute(delete(ChallengeNode).where(ChallengeNode.plan_id == plan.id))


async def expire_and_cleanup_challenges(
    session: AsyncSession, settings: Settings, *, now: datetime | None = None
) -> dict[str, int]:
    current = now or utcnow()
    plans = list(
        (
            await session.scalars(
                select(DailyChallengePlan).where(
                    DailyChallengePlan.status.not_in(("completed", "expired")),
                    DailyChallengePlan.expires_at < current,
                )
            )
        ).all()
    )
    for plan in plans:
        plan.status = "expired"
    contexts = await session.execute(
        delete(ChallengePlanContext).where(ChallengePlanContext.expires_at < current)
    )
    if plans:
        await session.commit()
    return {"expired": len(plans), "contexts": int(contexts.rowcount or 0)}


async def regenerate_today(
    session: AsyncSession,
    pool: ArqRedis,
    user: User,
    settings: Settings,
) -> ChallengeGenerateResponse:
    """Throw today's map away and build it again.

    A map the model failed to fill leaves an empty plan behind: the plan exists,
    so asking for today's map only ever replays it. This is the way out — but
    only while nothing has been done, because a map someone has already started
    is not a draft, and losing their progress would be worse than an empty map.
    """
    local_date = local_date_for(settings, user)
    plan = await session.scalar(
        select(DailyChallengePlan)
        .where(
            DailyChallengePlan.user_id == user.id,
            DailyChallengePlan.local_date == local_date,
        )
        .with_for_update()
    )
    if plan is None:
        raise AppError(
            status_code=404,
            code="CHALLENGE_NOT_GENERATED",
            message="Today's challenge has not been generated.",
        )
    if plan.status == "completed":
        raise AppError(
            status_code=409,
            code="CHALLENGE_ALREADY_COMPLETED",
            message="Today's challenge is already finished.",
        )
    # "unlocked" only means a node is available to open; the learner has not
    # spent anything on it yet. Anything further means real work.
    started = await session.scalar(
        select(func.count(ChallengeNodeProgress.id)).where(
            ChallengeNodeProgress.plan_id == plan.id,
            ChallengeNodeProgress.status.in_(("in_progress", "completed", "failed")),
        )
    )
    if started:
        raise AppError(
            status_code=409,
            code="CHALLENGE_ALREADY_STARTED",
            message="This map has already been started, so it cannot be rebuilt.",
        )

    await session.execute(
        delete(ChallengeNodeProgress).where(ChallengeNodeProgress.plan_id == plan.id)
    )
    await session.execute(delete(ChallengeNode).where(ChallengeNode.plan_id == plan.id))
    # Marking it failed is what lets generate_today build a new one instead of
    # replaying the empty map it would otherwise find.
    plan.status = "failed"
    plan.error_code = None
    plan.error_message = None
    await session.commit()

    return await generate_today(session, pool, user, settings)
