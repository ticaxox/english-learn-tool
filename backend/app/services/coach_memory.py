"""Typed memories the coach keeps about a learner.

The old design stored everything in one 6,000-character document that grew with
every practice run and chat message. This service keeps the same idea but splits
it: facts are rows with provenance and a status, recalled on demand, while the
profile and recent learning state are computed at answer time and never stored.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.models.coach_memory import CoachMemory
from app.models.identity import User, UserProfile
from app.models.learning import MemoryConfig
from app.models.practice import PracticeSession
from app.models.wordbooks import Wordbook, WordbookActivation
from app.schemas.coach_memory import (
    CoachMemoryCreate,
    CoachMemoryListResponse,
    CoachMemoryResponse,
    CoachMemoryUpdate,
)

MAX_ACTIVE = 200
RECALL_LIMIT = 8
RECALL_CHARS = 600
LEARNING_WINDOW_DAYS = 7

# Labels reused by the snapshot text so the coach reads the same words the UI uses.
EXAM_LABELS = {
    "GAOKAO": "高考",
    "CET4": "四级",
    "CET6": "六级",
    "POSTGRAD": "考研",
    "IELTS": "雅思",
    "TOEFL": "托福",
}
CHALLENGE_TYPE_LABELS = {
    "fill_blank": "填空",
    "reading": "阅读",
    "translation": "翻译",
    "writing": "作文",
}
DRILL_LABELS = {"flashcard": "翻卡", "choice": "选择", "spelling": "拼写"}
PRACTICE_LABELS = {
    "fill_blank": "填空",
    "reading": "阅读",
    "translation": "翻译",
    "writing": "作文",
    "mixed": "随机",
}

_LEGACY_PREFIXES = {
    "用户信息：": "fact",
    "习惯偏好：": "preference",
    "用户要求：": "constraint",
}
_WORD = re.compile(r"[A-Za-z0-9一-鿿]+")


def _normalise(value: str) -> str:
    return " ".join(value.split())[:500]


def _response(row: CoachMemory) -> CoachMemoryResponse:
    return CoachMemoryResponse(
        id=row.id,
        kind=row.kind,
        subject_key=row.subject_key,
        content=row.content,
        source=row.source,
        status=row.status,
        importance=row.importance,
        created_at=row.created_at,
        updated_at=row.updated_at,
        last_used_at=row.last_used_at,
    )


async def list_memories(
    session: AsyncSession, user: User, *, include_history: bool = False
) -> CoachMemoryListResponse:
    filters = [CoachMemory.user_id == user.id]
    if not include_history:
        filters.append(CoachMemory.status == "active")
    rows = list(
        (
            await session.scalars(
                select(CoachMemory)
                .where(*filters)
                .order_by(CoachMemory.importance.desc(), CoachMemory.updated_at.desc())
            )
        ).all()
    )
    return CoachMemoryListResponse(items=[_response(row) for row in rows])


async def _supersede_subject(
    session: AsyncSession, user_id: UUID, subject_key: str | None, keep_id: UUID | None = None
) -> None:
    if not subject_key:
        return
    filters = [
        CoachMemory.user_id == user_id,
        CoachMemory.subject_key == subject_key,
        CoachMemory.status == "active",
    ]
    if keep_id is not None:
        filters.append(CoachMemory.id != keep_id)
    await session.execute(update(CoachMemory).where(*filters).values(status="superseded"))


async def _trim_active(session: AsyncSession, user_id: UUID) -> None:
    """Keep the store bounded: archive the least important, least used rows."""
    count = int(
        await session.scalar(
            select(func.count(CoachMemory.id)).where(
                CoachMemory.user_id == user_id, CoachMemory.status == "active"
            )
        )
        or 0
    )
    overflow = count - MAX_ACTIVE
    if overflow <= 0:
        return
    stale = list(
        (
            await session.scalars(
                select(CoachMemory)
                .where(CoachMemory.user_id == user_id, CoachMemory.status == "active")
                .order_by(
                    CoachMemory.importance.asc(),
                    CoachMemory.last_used_at.asc().nullsfirst(),
                    CoachMemory.updated_at.asc(),
                )
                .limit(overflow)
            )
        ).all()
    )
    for row in stale:
        row.status = "archived"


async def create_memory(
    session: AsyncSession, user: User, payload: CoachMemoryCreate
) -> CoachMemoryResponse:
    content = _normalise(payload.content)
    if not content:
        raise AppError(
            status_code=422, code="COACH_MEMORY_EMPTY", message="The memory content is empty."
        )
    await _supersede_subject(session, user.id, payload.subject_key)
    row = CoachMemory(
        id=uuid4(),
        user_id=user.id,
        kind=payload.kind,
        subject_key=payload.subject_key,
        content=content,
        source=payload.source,
        importance=payload.importance,
    )
    session.add(row)
    await session.flush()
    await _trim_active(session, user.id)
    await session.commit()
    await session.refresh(row)
    return _response(row)


async def update_memory(
    session: AsyncSession, user: User, memory_id: UUID, payload: CoachMemoryUpdate
) -> CoachMemoryResponse:
    row = await session.scalar(
        select(CoachMemory).where(CoachMemory.id == memory_id, CoachMemory.user_id == user.id)
    )
    if row is None:
        raise AppError(status_code=404, code="COACH_MEMORY_NOT_FOUND", message="No such memory.")
    if payload.content is not None:
        content = _normalise(payload.content)
        if not content:
            raise AppError(
                status_code=422, code="COACH_MEMORY_EMPTY", message="The memory content is empty."
            )
        row.content = content
    if payload.kind is not None:
        row.kind = payload.kind
    if payload.importance is not None:
        row.importance = payload.importance
    if payload.subject_key is not None and payload.subject_key != row.subject_key:
        row.subject_key = payload.subject_key
        await _supersede_subject(session, user.id, payload.subject_key, keep_id=row.id)
    await session.commit()
    await session.refresh(row)
    return _response(row)


async def delete_memory(session: AsyncSession, user: User, memory_id: UUID) -> None:
    row = await session.scalar(
        select(CoachMemory).where(CoachMemory.id == memory_id, CoachMemory.user_id == user.id)
    )
    if row is None:
        raise AppError(status_code=404, code="COACH_MEMORY_NOT_FOUND", message="No such memory.")
    await session.delete(row)
    await session.commit()


async def recall_memories(
    session: AsyncSession, user_id: UUID, query: str, *, limit: int = RECALL_LIMIT
) -> list[str]:
    """Pick the memories worth putting in this turn's prompt, newest facts first."""
    rows = list(
        (
            await session.scalars(
                select(CoachMemory)
                .where(CoachMemory.user_id == user_id, CoachMemory.status == "active")
                .order_by(CoachMemory.importance.desc(), CoachMemory.updated_at.desc())
                .limit(MAX_ACTIVE)
            )
        ).all()
    )
    if not rows:
        return []
    tokens = {token.lower() for token in _WORD.findall(query) if len(token) > 1}
    scored: list[tuple[float, CoachMemory]] = []
    for row in rows:
        text = row.content.lower()
        overlap = sum(1 for token in tokens if token in text)
        # Importance dominates; a keyword hit only promotes within one level.
        scored.append((row.importance * 10 + min(overlap, 5) * 4, row))
    scored.sort(key=lambda item: item[0], reverse=True)

    picked: list[str] = []
    budget = RECALL_CHARS
    for _, row in scored[:limit]:
        line = f"[{row.kind}] {row.content}"
        if len(line) > budget:
            continue
        picked.append(line)
        budget -= len(line)
        row.last_used_at = datetime.now(tz=UTC)
    if picked:
        await session.flush()
    return picked


async def profile_snapshot(session: AsyncSession, user: User) -> str:
    """L0: current goals and settings, computed every turn and never stored."""
    parts: list[str] = []
    profile = await session.scalar(select(UserProfile).where(UserProfile.user_id == user.id))
    if profile is not None:
        exam = EXAM_LABELS.get(profile.target_exam or "", profile.target_exam or "未设置")
        parts.append(f"目标考试：{exam}")
        if profile.exam_date is not None:
            parts.append(f"考试日期：{profile.exam_date.isoformat()}")
        parts.append(
            f"每日新词 {profile.daily_new_words} 个、学习 {profile.daily_study_minutes} 分钟"
        )

    config = await session.scalar(select(MemoryConfig).where(MemoryConfig.user_id == user.id))
    if config is not None:
        challenge = (config.preferences or {}).get("challenge") or {}
        types = [
            CHALLENGE_TYPE_LABELS.get(item, item) for item in challenge.get("practiceTypes", [])
        ]
        drills = [DRILL_LABELS.get(item, item) for item in challenge.get("drillModes", [])]
        enabled = [
            DRILL_LABELS[item]
            for item in ("flashcard", "choice", "spelling")
            if getattr(config, f"{item}_enabled", False)
        ]
        if types:
            parts.append("偏好题型：" + "、".join(types))
        if drills:
            parts.append("关卡巩固：" + "、".join(drills))
        if enabled:
            parts.append("记忆方式：" + "、".join(enabled))

    wordbook = await session.scalar(
        select(Wordbook.name)
        .join(WordbookActivation, WordbookActivation.wordbook_id == Wordbook.id)
        .where(WordbookActivation.user_id == user.id)
    )
    if wordbook:
        parts.append(f"当前词书：{wordbook}")
    return "；".join(parts)


async def learning_snapshot(session: AsyncSession, user: User) -> str:
    """L3: a one-line summary of recent practice, aggregated at answer time."""
    since = func.now() - timedelta(days=LEARNING_WINDOW_DAYS)
    rows = list(
        (
            await session.scalars(
                select(PracticeSession)
                .where(
                    PracticeSession.user_id == user.id,
                    PracticeSession.status == "submitted",
                    PracticeSession.submitted_at.is_not(None),
                    PracticeSession.submitted_at >= since,
                )
                .order_by(PracticeSession.submitted_at.desc())
                .limit(30)
            )
        ).all()
    )
    if not rows:
        return ""
    scored = [row for row in rows if row.score is not None]
    average = round(sum(row.score or 0 for row in scored) / len(scored)) if scored else None
    wrong = sum(row.wrong_count or 0 for row in rows)
    weakest = max(
        rows,
        key=lambda row: (row.wrong_count or 0) / max(row.question_count or 1, 1),
    )
    parts = [f"近 {LEARNING_WINDOW_DAYS} 天提交 {len(rows)} 组练习"]
    if average is not None:
        parts.append(f"平均 {average} 分")
    if wrong:
        parts.append(f"累计错 {wrong} 题")
    if (weakest.wrong_count or 0) > 0:
        parts.append(f"最薄弱：{PRACTICE_LABELS.get(weakest.practice_type, weakest.practice_type)}")
    return "，".join(parts)


async def import_legacy_document(session: AsyncSession, user_id: UUID) -> int:
    """One-shot: turn the old document's lines into typed memories."""
    from app.models.ai_memory import AiMemory

    row = await session.scalar(
        select(AiMemory).where(
            AiMemory.user_id == user_id, AiMemory.memory_key == "memory_document"
        )
    )
    if row is None or not row.content.strip():
        return 0
    existing = int(
        await session.scalar(
            select(func.count(CoachMemory.id)).where(CoachMemory.user_id == user_id)
        )
        or 0
    )
    if existing:
        return 0
    imported = 0
    for line in row.content.splitlines():
        line = line.strip()
        kind = next(
            (value for prefix, value in _LEGACY_PREFIXES.items() if line.startswith(prefix)),
            None,
        )
        if kind is None:
            # Practice and chat lines are noise; the business tables hold the truth.
            continue
        content = _normalise(line.split("：", 1)[1])
        if not content:
            continue
        session.add(
            CoachMemory(
                id=uuid4(),
                user_id=user_id,
                kind=kind,
                content=content,
                source="imported",
                importance=4 if kind == "constraint" else 3,
            )
        )
        imported += 1
    if imported:
        await session.flush()
    return imported
