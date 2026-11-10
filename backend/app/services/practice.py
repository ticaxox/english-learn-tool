from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

from arq.connections import ArqRedis
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.errors import AppError
from app.models.ai import AiJob
from app.models.identity import User
from app.models.learning import DailyPlan, DailyPlanWord, MistakeFlag
from app.models.practice import (
    PracticeDeletion,
    PracticeEvent,
    PracticeGeneration,
    PracticePoolItem,
    PracticeQuestion,
    PracticeSession,
    PracticeSubmission,
)
from app.models.wordbooks import Wordbook, WordbookActivation, WordbookEntry
from app.schemas.ai_tasks import (
    BatchGradingItemContext,
    FillBlankItem,
    PracticeGenerationContext,
    PracticeGenerationOutput,
    PracticeGenerationRequest,
    PracticeGradingBatchOutput,
    PracticeItem,
    ReadingPassage,
    SubjectiveGradingContext,
    SubjectiveGradingRequest,
    TranslationItem,
    WritingItem,
)
from app.schemas.practice import (
    PracticeCreateRequest,
    PracticeDeleteRequest,
    PracticeDeleteResponse,
    PracticeDraftRequest,
    PracticeDraftResponse,
    PracticeEventListResponse,
    PracticeEventResponse,
    PracticeGradingDimension,
    PracticeQuestionPublic,
    PracticeQuestionResult,
    PracticeRecordDetail,
    PracticeRecordListResponse,
    PracticeRecordSummary,
    PracticeResultResponse,
    PracticeSessionListResponse,
    PracticeSessionResponse,
    PracticeSessionSummary,
    PracticeSubmitRequest,
    PracticeSubmitResponse,
)
from app.services.ai_jobs import cancel_user_job, create_ai_job
from app.services.audit import add_audit_event
from app.services.auth import utcnow
from app.services.gamification import award
from app.services.learning import local_date_for
from app.services.wordbook_queue import WORDBOOK_QUEUE_NAME

logger = logging.getLogger(__name__)


def _hash_request(payload: Any) -> str:
    encoded = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode()
    return hashlib.sha256(encoded).hexdigest()


def _event(
    session: PracticeSession,
    event_type: str,
    *,
    metadata: dict[str, Any] | None = None,
) -> PracticeEvent:
    return PracticeEvent(
        user_id=session.user_id,
        session_id=session.id,
        event_type=event_type,
        metadata_json=metadata or {},
    )


async def _entry_headwords(session: AsyncSession, entry_ids: list[UUID]) -> list[str]:
    """Headwords in the same order as the ids, for the generation prompt."""
    if not entry_ids:
        return []
    rows = (
        await session.execute(
            select(WordbookEntry.id, WordbookEntry.headword).where(
                WordbookEntry.id.in_(entry_ids)
            )
        )
    ).all()
    by_id = {entry_id: headword for entry_id, headword in rows}
    return [by_id[entry_id] for entry_id in entry_ids if entry_id in by_id]


def _article_range(
    settings: Settings, practice_type: str, count: int
) -> tuple[int | None, int | None]:
    """Reading generates a single passage, so its length follows the question count."""
    if practice_type != "reading":
        return None, None
    low, high = settings.article_word_range(count)
    return low, high


def _question_public(question: PracticeQuestion) -> PracticeQuestionPublic:
    payload = question.public_payload
    return PracticeQuestionPublic(
        id=question.id,
        position=question.position,
        question_type=question.question_type,
        prompt=payload.get("prompt"),
        sentence=payload.get("sentence"),
        sentence_zh=payload.get("sentence_zh"),
        article=payload.get("article"),
        article_zh=payload.get("article_zh"),
        options=payload.get("options", []),
        source_text=payload.get("source_text"),
        source_language=payload.get("source_language"),
        target_language=payload.get("target_language"),
        requirements=payload.get("requirements", []),
        target_entry_ids=question.target_entry_ids,
        target_words=payload.get("target_words", []),
    )


async def _current_questions(
    session: AsyncSession, practice: PracticeSession
) -> list[PracticeQuestion]:
    if practice.current_generation_id is None:
        return []
    return list(
        (
            await session.scalars(
                select(PracticeQuestion)
                .where(PracticeQuestion.generation_id == practice.current_generation_id)
                .order_by(PracticeQuestion.position.asc())
            )
        ).all()
    )


async def _session_response(
    session: AsyncSession, practice: PracticeSession
) -> PracticeSessionResponse:
    questions = await _current_questions(session, practice)
    job_status = None
    if practice.ai_job_id is not None:
        job = await session.get(AiJob, practice.ai_job_id)
        job_status = job.status if job is not None else None
    return PracticeSessionResponse(
        id=practice.id,
        practice_type=practice.practice_type,
        source=practice.source,
        difficulty=practice.difficulty,
        wordbook_id=practice.wordbook_id,
        translation_direction=practice.source_context.get("translation_direction"),
        writing_target_words=practice.source_context.get("writing_target_words"),
        status=practice.status,
        question_count=practice.question_count,
        generation_number=practice.generation_number,
        draft_version=practice.draft_version,
        draft_answers=practice.draft_answers,
        questions=[_question_public(question) for question in questions],
        job_status=job_status,
        error_code=practice.error_code,
        error_message=practice.error_message,
        created_at=practice.created_at,
        updated_at=practice.updated_at,
    )


async def _load_owned_session(
    session: AsyncSession, user: User, session_id: UUID, *, lock: bool = False
) -> PracticeSession:
    statement = select(PracticeSession).where(
        PracticeSession.id == session_id,
        PracticeSession.user_id == user.id,
    )
    if lock:
        statement = statement.with_for_update()
    practice = await session.scalar(statement)
    if practice is None:
        raise AppError(
            status_code=404,
            code="PRACTICE_SESSION_NOT_FOUND",
            message="The practice session was not found.",
        )
    return practice


async def _resolve_wordbook(
    session: AsyncSession, user: User, wordbook_id: UUID | None
) -> Wordbook:
    if wordbook_id is None:
        activation = await session.get(WordbookActivation, user.id)
        if activation is None:
            raise AppError(
                status_code=409,
                code="PRACTICE_WORDBOOK_REQUIRED",
                message="An active wordbook is required for this practice source.",
            )
        wordbook_id = activation.wordbook_id
    wordbook = await session.scalar(
        select(Wordbook).where(
            Wordbook.id == wordbook_id,
            Wordbook.status == "ready",
            Wordbook.owner_id == user.id,
        )
    )
    if wordbook is None:
        raise AppError(
            status_code=404,
            code="PRACTICE_WORDBOOK_NOT_FOUND",
            message="The practice wordbook was not found.",
        )
    return wordbook


async def _resolve_target_entries(
    session: AsyncSession,
    user: User,
    settings: Settings,
    payload: PracticeCreateRequest,
) -> tuple[UUID | None, list[UUID]]:
    if payload.source == "difficulty":
        return None, []
    wordbook = await _resolve_wordbook(session, user, payload.wordbook_id)
    entries: list[UUID] = []
    if payload.source in {"today_new", "today_review"}:
        plan = await session.scalar(
            select(DailyPlan).where(
                DailyPlan.user_id == user.id,
                DailyPlan.local_date == local_date_for(settings, user),
            )
        )
        if plan is not None:
            reason = "new" if payload.source == "today_new" else "due"
            entries = list(
                (
                    await session.scalars(
                        select(DailyPlanWord.entry_id)
                        .where(DailyPlanWord.plan_id == plan.id, DailyPlanWord.reason == reason)
                        .order_by(DailyPlanWord.position.asc())
                    )
                ).all()
            )
    elif payload.source == "memory_mistakes":
        entries = list(
            (
                await session.scalars(
                    select(MistakeFlag.entry_id)
                    .where(MistakeFlag.user_id == user.id, MistakeFlag.wordbook_id == wordbook.id)
                    .order_by(MistakeFlag.last_again_at.desc())
                )
            ).all()
        )
    if not entries:
        entries = list(
            (
                await session.scalars(
                    select(WordbookEntry.id)
                    .where(WordbookEntry.wordbook_id == wordbook.id)
                    .order_by(WordbookEntry.sequence.asc(), WordbookEntry.created_at.asc())
                    .limit(30)
                )
            ).all()
        )
    if not entries:
        raise AppError(
            status_code=409,
            code="PRACTICE_SOURCE_EMPTY",
            message="The selected practice source has no available words.",
        )
    return wordbook.id, entries


def _exam_type(user: User, difficulty: str | None) -> str:
    if difficulty:
        return difficulty
    profile = user.profile
    return profile.target_exam if profile and profile.target_exam else "CET4"


async def claim_pool_session(
    session: AsyncSession,
    user: User,
    payload: PracticeCreateRequest,
    *,
    idempotency_key: str,
    request_hash: str,
) -> PracticeSession | None:
    """Take one ready pre-generated set for this request, if one exists."""
    row = (
        await session.execute(
            select(PracticePoolItem, PracticeSession)
            .join(PracticeSession, PracticeSession.id == PracticePoolItem.session_id)
            .where(
                PracticePoolItem.user_id == user.id,
                PracticePoolItem.practice_type == payload.practice_type,
                PracticePoolItem.question_count == payload.count,
                PracticeSession.status == "ready",
            )
            .order_by(PracticePoolItem.created_at.asc())
            .with_for_update(skip_locked=True)
            .limit(1)
        )
    ).first()
    if row is None:
        return None
    item, practice = row
    practice.is_pool = False
    practice.source = payload.source
    practice.difficulty = payload.difficulty
    practice.idempotency_key = idempotency_key
    practice.request_hash = request_hash
    practice.source_context = {
        **practice.source_context,
        "source": payload.source,
        "difficulty": payload.difficulty,
        "claimed_from_pool": True,
    }
    await session.delete(item)
    await session.commit()
    await session.refresh(practice)
    return practice


async def create_practice_session(
    session: AsyncSession,
    pool: ArqRedis,
    user: User,
    settings: Settings,
    payload: PracticeCreateRequest,
    *,
    idempotency_key: str,
) -> PracticeSessionResponse:
    if not idempotency_key or len(idempotency_key) > 128:
        raise AppError(
            status_code=422,
            code="PRACTICE_IDEMPOTENCY_KEY_INVALID",
            message="The Idempotency-Key must be between 1 and 128 characters.",
        )
    request_hash = _hash_request(payload.model_dump(mode="json"))
    existing = await session.scalar(
        select(PracticeSession).where(
            PracticeSession.user_id == user.id,
            PracticeSession.idempotency_key == idempotency_key,
        )
    )
    if existing is not None:
        if existing.request_hash != request_hash:
            raise AppError(
                status_code=409,
                code="PRACTICE_IDEMPOTENCY_CONFLICT",
                message="The Idempotency-Key was used for a different practice request.",
            )
        return await _session_response(session, existing)

    claimed = await claim_pool_session(
        session, user, payload, idempotency_key=idempotency_key, request_hash=request_hash
    )
    if claimed is not None:
        # Refill the pool in the background; claiming must not wait for it.
        try:
            await pool.enqueue_job(
                "replenish_practice_pool",
                str(user.id),
                _job_id=f"pool-replenish:{user.id}:{uuid4().hex}",
                _queue_name=WORDBOOK_QUEUE_NAME,
            )
        except Exception:  # noqa: BLE001 - the scheduler also tops up pools
            logger.warning("practice_pool.replenish_enqueue_failed", exc_info=True)
        return await _session_response(session, claimed)

    wordbook_id, target_entry_ids = await _resolve_target_entries(session, user, settings, payload)
    session_id = uuid4()
    generation_id = uuid4()
    source_context = {
        "practice_type": payload.practice_type,
        "source": payload.source,
        "count": payload.count,
        "difficulty": payload.difficulty,
        "wordbook_id": str(wordbook_id) if wordbook_id else None,
        "target_entry_ids": [str(entry_id) for entry_id in target_entry_ids],
        "translation_direction": payload.translation_direction,
        "writing_target_words": payload.writing_target_words,
    }
    practice = PracticeSession(
        id=session_id,
        user_id=user.id,
        practice_type=payload.practice_type,
        source=payload.source,
        difficulty=payload.difficulty,
        wordbook_id=wordbook_id,
        question_count=payload.count,
        status="generating",
        generation_number=1,
        current_generation_id=generation_id,
        source_context=source_context,
        idempotency_key=idempotency_key,
        request_hash=request_hash,
    )
    generation = PracticeGeneration(
        id=generation_id,
        session_id=session_id,
        generation_number=1,
        status="generating",
    )
    session.add(practice)
    await session.flush()
    session.add(generation)
    await session.flush()
    session.add(
        _event(practice, "practice.created", metadata={"practice_type": payload.practice_type})
    )
    await session.flush()

    article_min_words, article_max_words = _article_range(
        settings, payload.practice_type, payload.count
    )
    target_words = await _entry_headwords(session, target_entry_ids)
    generation_request = PracticeGenerationRequest(
        task_type="practice_generation",
        context=PracticeGenerationContext(
            practice_type=payload.practice_type,
            count=payload.count,
            source=payload.source,
            difficulty=payload.difficulty,
            wordbook_id=wordbook_id,
            target_entry_ids=target_entry_ids,
            target_words=target_words,
            practice_session_id=session_id,
            article_min_words=article_min_words,
            article_max_words=article_max_words,
            translation_direction=payload.translation_direction,
            writing_target_words=payload.writing_target_words,
        ),
    )
    job, _ = await create_ai_job(
        session,
        pool,
        user,
        settings,
        generation_request,
        idempotency_key=f"practice-gen:{session_id}:1",
    )
    generation = await session.get(PracticeGeneration, generation_id)
    if generation is not None:
        generation.ai_job_id = job.id
    practice = await session.get(PracticeSession, session_id)
    if practice is not None:
        practice.ai_job_id = job.id
    await session.commit()
    practice = await _load_owned_session(session, user, session_id)
    return await _session_response(session, practice)


async def create_pool_practice_session(
    session: AsyncSession,
    pool: ArqRedis,
    user: User,
    settings: Settings,
    *,
    practice_type: str,
    count: int,
) -> PracticeSession:
    """Generate one ready-to-use practice set ahead of time.

    The session is marked ``is_pool`` and stays out of the learner's records
    until they claim it. Whole-book words keep the content valid even when the
    daily plan rotates.
    """
    payload = PracticeCreateRequest(
        practice_type=practice_type,  # type: ignore[arg-type]
        source="whole_book",
        count=count,
    )
    wordbook_id, target_entry_ids = await _resolve_target_entries(session, user, settings, payload)
    session_id = uuid4()
    generation_id = uuid4()
    practice = PracticeSession(
        id=session_id,
        user_id=user.id,
        practice_type=practice_type,
        source="whole_book",
        difficulty=None,
        wordbook_id=wordbook_id,
        question_count=count,
        status="generating",
        generation_number=1,
        current_generation_id=generation_id,
        source_context={
            "practice_type": practice_type,
            "source": "whole_book",
            "count": count,
            "difficulty": None,
            "wordbook_id": str(wordbook_id) if wordbook_id else None,
            "target_entry_ids": [str(entry_id) for entry_id in target_entry_ids],
            "pre_generated": True,
        },
        idempotency_key=f"pool:{session_id}",
        request_hash="0" * 64,
        is_pool=True,
    )
    generation = PracticeGeneration(
        id=generation_id,
        session_id=session_id,
        generation_number=1,
        status="generating",
    )
    session.add(practice)
    await session.flush()
    session.add(generation)
    await session.flush()
    session.add(
        _event(practice, "practice.pool_created", metadata={"practice_type": practice_type})
    )
    article_min_words, article_max_words = _article_range(settings, practice_type, count)
    target_words = await _entry_headwords(session, target_entry_ids)
    generation_request = PracticeGenerationRequest(
        task_type="practice_generation",
        context=PracticeGenerationContext(
            practice_type=practice_type,  # type: ignore[arg-type]
            count=count,
            source="whole_book",
            difficulty=None,
            wordbook_id=wordbook_id,
            target_entry_ids=target_entry_ids,
            target_words=target_words,
            practice_session_id=session_id,
            article_min_words=article_min_words,
            article_max_words=article_max_words,
        ),
    )
    job, _ = await create_ai_job(
        session,
        pool,
        user,
        settings,
        generation_request,
        idempotency_key=f"practice-pool:{session_id}",
        background=True,
    )
    generation_row = await session.get(PracticeGeneration, generation_id)
    if generation_row is not None:
        generation_row.ai_job_id = job.id
    practice_row = await session.get(PracticeSession, session_id)
    if practice_row is not None:
        practice_row.ai_job_id = job.id
    await session.commit()
    return await _load_owned_session(session, user, session_id)


STALE_GENERATION_SECONDS = 900


def reconcile_generation_status(
    practice: PracticeSession, job: AiJob | None, *, now: datetime
) -> bool:
    """Bring a stuck generating session in line with its AI job.

    A worker can die between marking the job failed and updating the practice
    session; a queued/running job can also outlive the worker timeout. Either
    way the learner must see a retryable failure instead of an endless
    "generating" row.
    """

    if practice.status != "generating" or job is None:
        return False
    if job.status in {"failed", "cancelled"}:
        practice.status = "failed"
        practice.error_code = job.error_code or "AI_JOB_FAILED"
        practice.error_message = job.error_message or "生成任务失败，请重试。"
        return True
    if job.status in {"queued", "running"}:
        reference = job.started_at or job.created_at
        if now - reference <= timedelta(seconds=STALE_GENERATION_SECONDS):
            return False
        practice.status = "failed"
        practice.error_code = "AI_JOB_TIMEOUT"
        practice.error_message = "生成任务超时，请重试。"
        job.status = "failed"
        job.error_code = "AI_JOB_TIMEOUT"
        job.error_message = "生成任务超时，请重试。"
        job.finished_at = now
        job.retryable = True
        return True
    return False


async def list_recent_sessions(
    session: AsyncSession, user: User, *, limit: int = 20
) -> PracticeSessionListResponse:
    rows = (
        await session.execute(
            select(PracticeSession, AiJob)
            .outerjoin(AiJob, AiJob.id == PracticeSession.ai_job_id)
            .where(PracticeSession.user_id == user.id, PracticeSession.is_pool.is_(False))
            .order_by(PracticeSession.created_at.desc())
            .limit(limit)
        )
    ).all()
    now = utcnow()
    changed = False
    for practice, job in rows:
        changed = reconcile_generation_status(practice, job, now=now) or changed
    if changed:
        await session.commit()
    return PracticeSessionListResponse(
        items=[
            PracticeSessionSummary(
                id=practice.id,
                practice_type=practice.practice_type,
                source=practice.source,
                status=practice.status,
                question_count=practice.question_count,
                score=practice.score,
                created_at=practice.created_at,
                submitted_at=practice.submitted_at,
                error_code=practice.error_code,
                error_message=practice.error_message,
            )
            for practice, _job in rows
        ]
    )


async def delete_session(
    session: AsyncSession, pool: ArqRedis, user: User, session_id: UUID
) -> None:
    practice = await _load_owned_session(session, user, session_id, lock=True)
    if practice.status == "generating" and practice.ai_job_id is not None:
        job = await session.get(AiJob, practice.ai_job_id)
        if job is not None and job.status in {"queued", "running"}:
            try:
                await cancel_user_job(session, pool, user, job.id)
            except AppError:
                pass
    await session.delete(practice)
    await session.commit()


async def get_practice_session(
    session: AsyncSession, user: User, session_id: UUID
) -> PracticeSessionResponse:
    practice = await _load_owned_session(session, user, session_id)
    return await _session_response(session, practice)


async def start_practice_session(
    session: AsyncSession, user: User, session_id: UUID
) -> PracticeSessionResponse:
    practice = await _load_owned_session(session, user, session_id, lock=True)
    if practice.status == "submitted":
        raise AppError(
            status_code=409,
            code="PRACTICE_ALREADY_SUBMITTED",
            message="The practice session has already been submitted.",
        )
    session.add(_event(practice, "practice.started"))
    await session.commit()
    return await _session_response(session, practice)


async def save_practice_draft(
    session: AsyncSession,
    user: User,
    session_id: UUID,
    payload: PracticeDraftRequest,
) -> PracticeDraftResponse:
    practice = await _load_owned_session(session, user, session_id, lock=True)
    if practice.status in {"submitted", "cancelled"}:
        raise AppError(
            status_code=409,
            code="PRACTICE_DRAFT_NOT_EDITABLE",
            message="The practice session is no longer editable.",
        )
    if payload.version != practice.draft_version:
        raise AppError(
            status_code=409,
            code="PRACTICE_DRAFT_VERSION_CONFLICT",
            message="The draft was changed by another request.",
            details={"current_version": practice.draft_version},
        )
    questions = await _current_questions(session, practice)
    valid_ids = {str(question.id) for question in questions}
    if not set(payload.answers).issubset(valid_ids):
        raise AppError(
            status_code=422,
            code="PRACTICE_DRAFT_QUESTION_INVALID",
            message="The draft contains a question outside this practice session.",
        )
    practice.draft_answers = payload.answers
    practice.draft_version += 1
    session.add(
        _event(
            practice,
            "practice.draft_saved",
            metadata={"version": practice.draft_version, "answer_count": len(payload.answers)},
        )
    )
    await session.commit()
    await session.refresh(practice)
    return PracticeDraftResponse(
        session_id=practice.id,
        draft_version=practice.draft_version,
        answers=practice.draft_answers,
        saved_at=practice.updated_at,
    )


async def regenerate_practice_session(
    session: AsyncSession,
    pool: ArqRedis,
    user: User,
    settings: Settings,
    session_id: UUID,
    *,
    idempotency_key: str,
    background: bool = False,
) -> PracticeSessionResponse:
    practice = await _load_owned_session(session, user, session_id, lock=True)
    if practice.status == "submitted":
        raise AppError(
            status_code=409,
            code="PRACTICE_ALREADY_SUBMITTED",
            message="A submitted practice session cannot be regenerated.",
        )
    if practice.status == "generating":
        raise AppError(
            status_code=409,
            code="PRACTICE_GENERATION_IN_PROGRESS",
            message="The current practice generation is still in progress.",
        )
    if practice.draft_answers:
        raise AppError(
            status_code=409,
            code="PRACTICE_REGENERATION_NOT_ALLOWED",
            message="Regeneration is only allowed before answering.",
        )
    if practice.current_generation_id is not None:
        old_generation = await session.get(PracticeGeneration, practice.current_generation_id)
        if old_generation is not None:
            old_generation.status = "superseded"
    practice.generation_number += 1
    generation_id = uuid4()
    practice.current_generation_id = generation_id
    practice.status = "generating"
    practice.error_code = None
    practice.error_message = None
    generation = PracticeGeneration(
        id=generation_id,
        session_id=practice.id,
        generation_number=practice.generation_number,
        status="generating",
    )
    session.add(generation)
    session.add(
        _event(
            practice,
            "practice.regenerated",
            metadata={"generation_number": practice.generation_number},
        )
    )
    await session.flush()
    context = practice.source_context
    generation_request = PracticeGenerationRequest(
        task_type="practice_generation",
        context=PracticeGenerationContext(
            practice_type=practice.practice_type,
            count=practice.question_count,
            source=practice.source,
            difficulty=practice.difficulty,
            wordbook_id=practice.wordbook_id,
            target_entry_ids=[UUID(value) for value in context.get("target_entry_ids", [])],
            target_words=context.get("target_words", []),
            translation_direction=context.get("translation_direction"),
            writing_target_words=context.get("writing_target_words"),
            practice_session_id=practice.id,
        ),
    )
    job, _ = await create_ai_job(
        session,
        pool,
        user,
        settings,
        generation_request,
        idempotency_key=f"practice-gen:{practice.id}:{practice.generation_number}",
        background=background,
    )
    generation = await session.get(PracticeGeneration, generation_id)
    if generation is not None:
        generation.ai_job_id = job.id
    practice = await session.get(PracticeSession, session_id)
    if practice is not None:
        practice.ai_job_id = job.id
    await session.commit()
    practice = await _load_owned_session(session, user, session_id)
    return await _session_response(session, practice)


def _answer_matches(answer: str, correct_option_id: str, options: list[dict[str, Any]]) -> bool:
    normalized = answer.strip().casefold()
    if normalized == correct_option_id.casefold():
        return True
    for option in options:
        if option.get("id") == correct_option_id:
            return normalized == str(option.get("text", "")).strip().casefold()
    return False


def _objective_results(
    questions: list[PracticeQuestion], answers: dict[str, str]
) -> tuple[list[PracticeQuestionResult], int]:
    """Grade choice-style questions locally; returns the rows and correct count."""
    question_results: list[PracticeQuestionResult] = []
    correct_count = 0
    for question in questions:
        public = question.public_payload
        private = question.private_payload
        options = public.get("options", [])
        user_answer = answers[str(question.id)]
        correct_option_id = str(private.get("correct_option_id", ""))
        is_correct = _answer_matches(user_answer, correct_option_id, options)
        correct_count += int(is_correct)
        correct_text = next(
            (option.get("text") for option in options if option.get("id") == correct_option_id),
            None,
        )
        question_results.append(
            PracticeQuestionResult(
                question_id=str(question.id),
                question_type=question.question_type,
                user_answer=user_answer,
                is_correct=is_correct,
                is_mistake=not is_correct,
                score=100.0 if is_correct else 0.0,
                correct_option_id=correct_option_id,
                correct_option_text=correct_text,
                explanation=private.get("explanation"),
            )
        )
    return question_results, correct_count


async def _grade_objective(
    session: AsyncSession,
    practice: PracticeSession,
    submission: PracticeSubmission,
    questions: list[PracticeQuestion],
    answers: dict[str, str],
) -> PracticeResultResponse:
    question_results, correct_count = _objective_results(questions, answers)
    total = len(questions)
    wrong_count = total - correct_count
    score = round(correct_count / total * 100, 2) if total else 0.0
    submitted_at = utcnow()
    result = PracticeResultResponse(
        session_id=practice.id,
        submission_id=submission.id,
        status="completed",
        score=score,
        correct_count=correct_count,
        total_questions=total,
        wrong_count=wrong_count,
        questions=question_results,
        mistakes=[item for item in question_results if item.is_mistake],
        submitted_at=submitted_at,
    )
    submission.status = "completed"
    submission.result = result.model_dump(mode="json")
    submission.score = score
    submission.correct_count = correct_count
    submission.wrong_count = wrong_count
    submission.completed_at = submitted_at
    practice.status = "submitted"
    practice.score = score
    practice.correct_count = correct_count
    practice.wrong_count = wrong_count
    practice.submitted_at = submitted_at
    session.add(_event(practice, "practice.objective_graded", metadata={"score": score}))
    session.add(_event(practice, "practice.submitted", metadata={"wrong_count": wrong_count}))
    return result


async def _create_subjective_grading_job(
    session: AsyncSession,
    pool: ArqRedis,
    user: User,
    settings: Settings,
    practice: PracticeSession,
    submission: PracticeSubmission,
    questions: list[PracticeQuestion],
    answers: dict[str, str],
) -> None:
    exam_type = _exam_type(user, practice.difficulty)
    items = [
        BatchGradingItemContext(
            question_id=str(question.id),
            source_text=question.public_payload.get("source_text")
            or question.public_payload.get("prompt")
            or "",
            user_answer=answers[str(question.id)],
            exam_type=exam_type,
            target_entry_ids=[UUID(value) for value in question.target_entry_ids],
        )
        for question in questions
    ]
    context = SubjectiveGradingContext(
        practice_type=practice.practice_type,
        source_text="batch grading",
        user_answer="batch grading",
        exam_type=exam_type,
        target_entry_ids=[],
        practice_submission_id=submission.id,
        items=items,
    )
    job, _ = await create_ai_job(
        session,
        pool,
        user,
        settings,
        SubjectiveGradingRequest(task_type="subjective_grading", context=context),
        idempotency_key=f"practice-grade:{submission.id}",
        quota_items=[item.question_id for item in items],
    )
    submission.ai_job_id = job.id
    session.add(
        _event(practice, "practice.subjective_scoring_started", metadata={"job_id": str(job.id)})
    )


async def submit_practice_session(
    session: AsyncSession,
    pool: ArqRedis,
    user: User,
    settings: Settings,
    session_id: UUID,
    payload: PracticeSubmitRequest,
    *,
    idempotency_key: str,
) -> PracticeSubmitResponse:
    if not idempotency_key or len(idempotency_key) > 128:
        raise AppError(
            status_code=422,
            code="PRACTICE_IDEMPOTENCY_KEY_INVALID",
            message="The Idempotency-Key must be between 1 and 128 characters.",
        )
    request_hash = _hash_request(payload.model_dump(mode="json"))
    existing = await session.scalar(
        select(PracticeSubmission).where(
            PracticeSubmission.user_id == user.id,
            PracticeSubmission.idempotency_key == idempotency_key,
        )
    )
    if existing is not None:
        if existing.request_hash != request_hash:
            raise AppError(
                status_code=409,
                code="PRACTICE_IDEMPOTENCY_CONFLICT",
                message="The Idempotency-Key was used for a different submission.",
            )
        practice = await _load_owned_session(session, user, existing.session_id)
        return PracticeSubmitResponse(
            session_id=practice.id,
            submission_id=existing.id,
            status=existing.status,
            result=_result_from_submission(practice, existing),
            error_code=existing.error_code,
            error_message=existing.error_message,
        )
    practice = await _load_owned_session(session, user, session_id, lock=True)
    if practice.status == "submitted":
        raise AppError(
            status_code=409,
            code="PRACTICE_ALREADY_SUBMITTED",
            message="The practice session has already been submitted.",
        )
    if practice.status != "ready":
        raise AppError(
            status_code=409,
            code="PRACTICE_NOT_READY",
            message="The practice session is not ready for submission.",
        )
    questions = await _current_questions(session, practice)
    answers = {item.question_id: item.answer for item in payload.answers}
    if set(answers) != {str(question.id) for question in questions}:
        raise AppError(
            status_code=422,
            code="PRACTICE_ANSWERS_INCOMPLETE",
            message="Submit exactly one answer for every question.",
        )
    submission = PracticeSubmission(
        session_id=practice.id,
        user_id=user.id,
        status="scoring",
        answers=answers,
        total_questions=len(questions),
        idempotency_key=idempotency_key,
        request_hash=request_hash,
    )
    session.add(submission)
    await session.flush()
    session.add(
        _event(practice, "practice.submitted", metadata={"submission_id": str(submission.id)})
    )
    subjective_questions = [
        question for question in questions if question.question_type in {"translation", "writing"}
    ]
    graded_locally = practice.practice_type in {"fill_blank", "reading"} or (
        practice.practice_type == "mixed" and not subjective_questions
    )
    if graded_locally:
        result = await _grade_objective(session, practice, submission, questions, answers)
        await award(
            session,
            settings,
            user,
            source_type="practice",
            source_id=str(practice.id),
            units=len(questions),
        )
        await session.commit()
        return PracticeSubmitResponse(
            session_id=practice.id,
            submission_id=submission.id,
            status="completed",
            result=result,
        )
    await _create_subjective_grading_job(
        session,
        pool,
        user,
        settings,
        practice,
        submission,
        subjective_questions or questions,
        answers,
    )
    await session.commit()
    return PracticeSubmitResponse(
        session_id=practice.id,
        submission_id=submission.id,
        status="scoring",
    )


def _result_from_submission(
    practice: PracticeSession, submission: PracticeSubmission
) -> PracticeResultResponse:
    if submission.result:
        return PracticeResultResponse.model_validate(submission.result)
    return PracticeResultResponse(
        session_id=practice.id,
        submission_id=submission.id,
        status=submission.status,
        score=submission.score,
        correct_count=submission.correct_count,
        total_questions=submission.total_questions,
        wrong_count=submission.wrong_count,
        error_code=submission.error_code,
        error_message=submission.error_message,
        submitted_at=submission.completed_at,
    )


async def get_practice_result(
    session: AsyncSession, user: User, session_id: UUID
) -> PracticeResultResponse:
    practice = await _load_owned_session(session, user, session_id)
    submission = await session.scalar(
        select(PracticeSubmission)
        .where(PracticeSubmission.session_id == practice.id)
        .order_by(PracticeSubmission.created_at.desc())
        .limit(1)
    )
    if submission is None:
        raise AppError(
            status_code=404,
            code="PRACTICE_RESULT_NOT_FOUND",
            message="The practice result was not found.",
        )
    return _result_from_submission(practice, submission)


async def _latest_submission(session: AsyncSession, session_id: UUID) -> PracticeSubmission | None:
    return await session.scalar(
        select(PracticeSubmission)
        .where(PracticeSubmission.session_id == session_id)
        .order_by(PracticeSubmission.created_at.desc())
        .limit(1)
    )


def _record_summary(practice: PracticeSession) -> PracticeRecordSummary:
    return PracticeRecordSummary(
        id=practice.id,
        practice_type=practice.practice_type,
        source=practice.source,
        difficulty=practice.difficulty,
        score=practice.score,
        correct_count=practice.correct_count,
        total_questions=practice.question_count,
        wrong_count=practice.wrong_count,
        submitted_at=practice.submitted_at,
        status=practice.status,
    )


async def list_practice_records(
    session: AsyncSession,
    user: User,
    *,
    practice_type: str | None = None,
    source: str | None = None,
    only_mistakes: bool = False,
    offset: int = 0,
    limit: int = 20,
) -> PracticeRecordListResponse:
    filters = [PracticeSession.user_id == user.id, PracticeSession.status == "submitted"]
    if practice_type:
        filters.append(PracticeSession.practice_type == practice_type)
    if source:
        filters.append(PracticeSession.source == source)
    if only_mistakes:
        filters.append(PracticeSession.wrong_count > 0)
    total = int(await session.scalar(select(func.count(PracticeSession.id)).where(*filters)) or 0)
    practices = list(
        (
            await session.scalars(
                select(PracticeSession)
                .where(*filters)
                .order_by(PracticeSession.submitted_at.desc(), PracticeSession.id.desc())
                .offset(offset)
                .limit(limit)
            )
        ).all()
    )
    return PracticeRecordListResponse(
        items=[_record_summary(practice) for practice in practices],
        total=total,
        offset=offset,
        limit=limit,
    )


async def get_practice_record(
    session: AsyncSession, user: User, session_id: UUID
) -> PracticeRecordDetail:
    practice = await _load_owned_session(session, user, session_id)
    if practice.status != "submitted":
        raise AppError(
            status_code=404,
            code="PRACTICE_RECORD_NOT_FOUND",
            message="The practice record was not found.",
        )
    submission = await _latest_submission(session, practice.id)
    summary = _record_summary(practice)
    return PracticeRecordDetail(
        **summary.model_dump(),
        result=_result_from_submission(practice, submission) if submission else None,
    )


async def delete_practice_records(
    session: AsyncSession,
    user: User,
    payload: PracticeDeleteRequest,
    *,
    idempotency_key: str,
) -> PracticeDeleteResponse:
    request_hash = _hash_request(payload.model_dump(mode="json"))
    existing = await session.scalar(
        select(PracticeDeletion).where(
            PracticeDeletion.user_id == user.id,
            PracticeDeletion.idempotency_key == idempotency_key,
        )
    )
    if existing is not None:
        if existing.request_hash != request_hash:
            raise AppError(
                status_code=409,
                code="PRACTICE_IDEMPOTENCY_CONFLICT",
                message="The Idempotency-Key was used for a different deletion.",
            )
        return PracticeDeleteResponse(
            deleted_count=int(existing.result.get("deleted_count", 0)),
            deleted_ids=[UUID(value) for value in existing.result.get("deleted_ids", [])],
        )
    practices = list(
        (
            await session.scalars(
                select(PracticeSession).where(
                    PracticeSession.user_id == user.id,
                    PracticeSession.id.in_(payload.ids),
                )
            )
        ).all()
    )
    deleted_ids = [practice.id for practice in practices]
    for practice in practices:
        await session.delete(practice)
    result = {
        "deleted_count": len(deleted_ids),
        "deleted_ids": [str(value) for value in deleted_ids],
    }
    session.add(
        PracticeDeletion(
            user_id=user.id,
            idempotency_key=idempotency_key,
            request_hash=request_hash,
            result=result,
        )
    )
    add_audit_event(
        session,
        action="practice.records.deleted",
        target_type="practice_records",
        outcome="success",
        actor=user,
        context={"deleted_count": len(deleted_ids)},
    )
    await session.commit()
    return PracticeDeleteResponse(deleted_count=len(deleted_ids), deleted_ids=deleted_ids)


async def list_practice_events(
    session: AsyncSession, user: User, *, offset: int = 0, limit: int = 50
) -> PracticeEventListResponse:
    filters = [PracticeEvent.user_id == user.id]
    total = int(await session.scalar(select(func.count(PracticeEvent.id)).where(*filters)) or 0)
    events = list(
        (
            await session.scalars(
                select(PracticeEvent)
                .where(*filters)
                .order_by(PracticeEvent.created_at.desc())
                .offset(offset)
                .limit(limit)
            )
        ).all()
    )
    return PracticeEventListResponse(
        items=[
            PracticeEventResponse(
                id=event.id,
                session_id=event.session_id,
                event_type=event.event_type,
                metadata=event.metadata_json,
                created_at=event.created_at,
            )
            for event in events
        ],
        total=total,
        offset=offset,
        limit=limit,
    )


def question_rows(
    items: list[PracticeItem], generation: PracticeGeneration
) -> list[PracticeQuestion]:
    questions: list[PracticeQuestion] = []
    position = 0
    for item in items:
        if isinstance(item, FillBlankItem):
            public = {
                "sentence": item.sentence,
                "sentence_zh": item.sentence_zh,
                "options": [option.model_dump(mode="json") for option in item.options],
            }
            private = {"correct_option_id": item.correct_option_id, "explanation": item.explanation}
            questions.append(
                PracticeQuestion(
                    generation_id=generation.id,
                    position=position,
                    question_type="fill_blank",
                    public_payload=public,
                    private_payload=private,
                    target_entry_ids=[str(value) for value in item.target_entry_ids],
                )
            )
            position += 1
        elif isinstance(item, ReadingPassage):
            for reading_question in item.questions:
                public = {
                    "article": item.article,
                    "article_zh": item.article_zh,
                    "prompt": reading_question.prompt,
                    "options": [
                        option.model_dump(mode="json") for option in reading_question.options
                    ],
                }
                private = {
                    "correct_option_id": reading_question.correct_option_id,
                    "explanation": reading_question.explanation,
                }
                questions.append(
                    PracticeQuestion(
                        generation_id=generation.id,
                        position=position,
                        question_type="reading",
                        public_payload=public,
                        private_payload=private,
                        target_entry_ids=[str(value) for value in item.target_entry_ids],
                    )
                )
                position += 1
        elif isinstance(item, TranslationItem):
            public = {
                "source_text": item.source_text,
                "source_language": item.source_language,
                "target_language": item.target_language,
            }
            private = {"reference_translation": item.reference_translation}
            questions.append(
                PracticeQuestion(
                    generation_id=generation.id,
                    position=position,
                    question_type="translation",
                    public_payload=public,
                    private_payload=private,
                    target_entry_ids=[str(value) for value in item.target_entry_ids],
                )
            )
            position += 1
        elif isinstance(item, WritingItem):
            public = {"prompt": item.prompt, "requirements": item.requirements}
            private = {"reference_essay": item.reference_essay}
            questions.append(
                PracticeQuestion(
                    generation_id=generation.id,
                    position=position,
                    question_type="writing",
                    public_payload=public,
                    private_payload=private,
                    target_entry_ids=[str(value) for value in item.target_entry_ids],
                )
            )
            position += 1
    return questions


async def _attach_target_words(
    session: AsyncSession, questions: list[PracticeQuestion]
) -> None:
    """Copy the headwords behind each question's target entries into its public payload."""
    wanted = {entry for question in questions for entry in question.target_entry_ids}
    if not wanted:
        return
    rows = (
        await session.execute(
            select(WordbookEntry.id, WordbookEntry.headword).where(
                WordbookEntry.id.in_([UUID(entry) for entry in wanted])
            )
        )
    ).all()
    headwords = {str(entry_id): headword for entry_id, headword in rows}
    for question in questions:
        question.public_payload = {
            **question.public_payload,
            "target_words": [
                headwords[entry] for entry in question.target_entry_ids if entry in headwords
            ],
        }


async def materialize_practice_generation(session: AsyncSession, job: AiJob) -> None:
    session_id = job.input_context.get("practice_session_id")
    if not session_id or job.result is None:
        return
    try:
        practice_id = UUID(str(session_id))
    except ValueError:
        return
    practice = await session.scalar(
        select(PracticeSession).where(PracticeSession.id == practice_id).with_for_update()
    )
    if practice is None or practice.status != "generating":
        return
    generation = await session.get(PracticeGeneration, practice.current_generation_id)
    if generation is None or generation.status != "generating":
        return
    output = PracticeGenerationOutput.model_validate(job.result)
    questions = question_rows(output.items, generation)
    await _attach_target_words(session, questions)
    session.add_all(questions)
    generation.status = "ready"
    generation.question_count = len(questions)
    generation.ready_at = utcnow()
    practice.status = "ready"
    practice.question_count = len(questions)
    practice.ai_job_id = job.id
    practice.error_code = None
    practice.error_message = None
    session.add(_event(practice, "practice.generated", metadata={"question_count": len(questions)}))
    await session.flush()


async def mark_practice_generation_failed(session: AsyncSession, job: AiJob) -> None:
    session_id = job.input_context.get("practice_session_id")
    if not session_id:
        return
    try:
        practice_id = UUID(str(session_id))
    except ValueError:
        return
    practice = await session.scalar(
        select(PracticeSession).where(PracticeSession.id == practice_id).with_for_update()
    )
    if practice is None or practice.status != "generating":
        return
    generation = await session.get(PracticeGeneration, practice.current_generation_id)
    if generation is not None and generation.status == "generating":
        generation.status = "failed"
        generation.error_code = job.error_code
        generation.error_message = job.error_message
    practice.status = "failed"
    practice.error_code = job.error_code or "PRACTICE_GENERATION_FAILED"
    practice.error_message = job.error_message or "The practice generation failed."
    session.add(
        _event(practice, "practice.generation_failed", metadata={"error_code": practice.error_code})
    )
    await session.flush()


async def materialize_practice_grading(session: AsyncSession, job: AiJob) -> None:
    submission_id = job.input_context.get("practice_submission_id")
    if not submission_id or job.result is None:
        return
    try:
        submission_uuid = UUID(str(submission_id))
    except ValueError:
        return
    submission = await session.scalar(
        select(PracticeSubmission).where(PracticeSubmission.id == submission_uuid).with_for_update()
    )
    if submission is None or submission.status != "scoring":
        return
    practice = await session.get(PracticeSession, submission.session_id)
    if practice is None:
        return
    output = PracticeGradingBatchOutput.model_validate(job.result)
    questions = list(
        (
            await session.scalars(
                select(PracticeQuestion).where(
                    PracticeQuestion.generation_id == practice.current_generation_id
                )
            )
        ).all()
    )
    question_map = {str(question.id): question for question in questions}
    question_results: list[PracticeQuestionResult] = []
    for item in output.items:
        question = question_map.get(item.question_id)
        if question is None:
            continue
        question_results.append(
            PracticeQuestionResult(
                question_id=item.question_id,
                question_type=question.question_type,
                user_answer=submission.answers.get(item.question_id, ""),
                is_mistake=item.total_score < 60,
                score=item.total_score,
                reference_content=item.reference_content,
                dimensions=[
                    PracticeGradingDimension(
                        name=dimension.name,
                        score=dimension.score,
                        max_score=dimension.max_score,
                    )
                    for dimension in item.dimensions
                ],
                errors=item.errors,
                suggestions=item.suggestions,
            )
        )
    # Purely written practice has no locally graded questions, but the column is
    # not null, so start from zero rather than leaving it unset.
    correct_count = 0
    if practice.practice_type == "mixed":
        # Mixed sets grade choice questions locally and only send the written
        # ones to the AI; merge both halves back into question order.
        objective = [
            question
            for question in questions
            if question.question_type in {"fill_blank", "reading"}
        ]
        objective_rows, correct_count = _objective_results(objective, submission.answers)
        merged = {row.question_id: row for row in [*objective_rows, *question_results]}
        question_results = [
            merged[str(question.id)] for question in questions if str(question.id) in merged
        ]
    score = (
        round(sum(item.score or 0 for item in question_results) / len(question_results), 2)
        if question_results
        else 0.0
    )
    wrong_count = sum(1 for item in question_results if item.is_mistake)
    submitted_at = utcnow()
    result = PracticeResultResponse(
        session_id=practice.id,
        submission_id=submission.id,
        status="completed",
        score=score,
        correct_count=correct_count,
        total_questions=submission.total_questions,
        wrong_count=wrong_count,
        questions=question_results,
        mistakes=[item for item in question_results if item.is_mistake],
        submitted_at=submitted_at,
    )
    submission.status = "completed"
    submission.result = result.model_dump(mode="json")
    submission.score = score
    submission.correct_count = correct_count
    submission.wrong_count = wrong_count
    submission.completed_at = submitted_at
    practice.status = "submitted"
    practice.score = score
    practice.wrong_count = wrong_count
    practice.submitted_at = submitted_at
    session.add(_event(practice, "practice.subjective_graded", metadata={"score": score}))
    await session.flush()


async def mark_practice_grading_failed(session: AsyncSession, job: AiJob) -> None:
    submission_id = job.input_context.get("practice_submission_id")
    if not submission_id:
        return
    try:
        submission_uuid = UUID(str(submission_id))
    except ValueError:
        return
    submission = await session.scalar(
        select(PracticeSubmission).where(PracticeSubmission.id == submission_uuid).with_for_update()
    )
    if submission is None or submission.status != "scoring":
        return
    submission.status = "failed"
    submission.error_code = job.error_code or "PRACTICE_GRADING_FAILED"
    submission.error_message = job.error_message or "The subjective grading failed."
    practice = await session.get(PracticeSession, submission.session_id)
    if practice is not None:
        practice.error_code = submission.error_code
        practice.error_message = submission.error_message
        session.add(
            _event(
                practice,
                "practice.subjective_grading_failed",
                metadata={"error_code": submission.error_code},
            )
        )
    await session.flush()


async def create_practice_for_challenge(
    session: AsyncSession,
    pool: ArqRedis,
    user: User,
    settings: Settings,
    payload: PracticeCreateRequest,
    *,
    idempotency_key: str,
    target_entry_ids: list[UUID] | None = None,
) -> tuple[PracticeSession, UUID | None]:
    """Create a practice session without committing or enqueueing its generation job.

    Challenge starts own the surrounding transaction so the node progress and practice
    resource become visible atomically. The caller commits, then enqueues the returned job.
    """
    if not idempotency_key or len(idempotency_key) > 128:
        raise AppError(
            status_code=422,
            code="PRACTICE_IDEMPOTENCY_KEY_INVALID",
            message="The practice idempotency key is invalid.",
        )
    request_hash = _hash_request(payload.model_dump(mode="json"))
    existing = await session.scalar(
        select(PracticeSession).where(
            PracticeSession.user_id == user.id,
            PracticeSession.idempotency_key == idempotency_key,
        )
    )
    if existing is not None:
        if existing.request_hash != request_hash:
            raise AppError(
                status_code=409,
                code="PRACTICE_IDEMPOTENCY_CONFLICT",
                message="The practice idempotency key was used for a different request.",
            )
        return existing, None

    if target_entry_ids is None:
        wordbook_id, resolved_entry_ids = await _resolve_target_entries(
            session, user, settings, payload
        )
    else:
        wordbook_id = payload.wordbook_id
        if wordbook_id is None:
            raise AppError(
                status_code=422,
                code="PRACTICE_WORDBOOK_REQUIRED",
                message="A wordbook is required for challenge practice.",
            )
        book = await session.scalar(
            select(Wordbook).where(
                Wordbook.id == wordbook_id,
                Wordbook.status == "ready",
                Wordbook.owner_id == user.id,
            )
        )
        resolved_entry_ids = list(
            (
                await session.scalars(
                    select(WordbookEntry.id).where(
                        WordbookEntry.wordbook_id == wordbook_id,
                        WordbookEntry.id.in_(target_entry_ids),
                    )
                )
            ).all()
        )
        if book is None or len(resolved_entry_ids) != len(set(target_entry_ids)):
            raise AppError(
                status_code=404,
                code="PRACTICE_WORDBOOK_NOT_FOUND",
                message="The practice wordbook entries were not found.",
            )
    target_entry_ids = resolved_entry_ids
    session_id = uuid4()
    generation_id = uuid4()
    practice = PracticeSession(
        id=session_id,
        user_id=user.id,
        practice_type=payload.practice_type,
        source=payload.source,
        difficulty=payload.difficulty,
        wordbook_id=wordbook_id,
        question_count=payload.count,
        status="generating",
        generation_number=1,
        current_generation_id=generation_id,
        source_context={
            "practice_type": payload.practice_type,
            "source": payload.source,
            "count": payload.count,
            "difficulty": payload.difficulty,
            "wordbook_id": str(wordbook_id) if wordbook_id else None,
            "target_entry_ids": [str(entry_id) for entry_id in target_entry_ids],
        },
        idempotency_key=idempotency_key,
        request_hash=request_hash,
    )
    generation = PracticeGeneration(
        id=generation_id,
        session_id=session_id,
        generation_number=1,
        status="generating",
    )
    session.add(practice)
    await session.flush()
    session.add(generation)
    await session.flush()
    session.add(_event(practice, "practice.created", metadata={"source": "challenge"}))
    request = PracticeGenerationRequest(
        task_type="practice_generation",
        context=PracticeGenerationContext(
            practice_type=payload.practice_type,
            count=payload.count,
            source=payload.source,
            difficulty=payload.difficulty,
            wordbook_id=wordbook_id,
            target_entry_ids=target_entry_ids,
            translation_direction=payload.translation_direction,
            writing_target_words=payload.writing_target_words,
            practice_session_id=session_id,
        ),
    )
    job, _ = await create_ai_job(
        session,
        pool,
        user,
        settings,
        request,
        idempotency_key=f"challenge-practice:{idempotency_key}",
        commit=False,
    )
    practice.ai_job_id = job.id
    generation.ai_job_id = job.id
    return practice, job.id
