from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from arq.connections import ArqRedis
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.errors import AppError
from app.models.ai import AiJob, AiJobEvent, AiPrompt, AiProvider, AiUsageLedger
from app.models.coach import CoachAttachment
from app.models.identity import User
from app.schemas.ai import AiJobStatusResponse
from app.schemas.ai_tasks import AiJobCreateRequest
from app.services.ai_concurrency import acquire_concurrency_slot, release_concurrency_slot
from app.services.ai_secrets import ApiKeyCipher
from app.services.ai_security import ProviderHttpClient, ProviderRequestError
from app.services.ai_usage import resolved_quota_limits
from app.services.ai_validation import output_schema, repair_prompt, validate_task_output
from app.services.auth import utcnow
from app.services.coach_uploads import (
    attachment_text,
    is_image,
    read_attachment,
)
from app.services.learning import local_date_for
from app.services.wordbook_queue import WORDBOOK_QUEUE_NAME

logger = logging.getLogger(__name__)

TASK_QUOTA_KIND = {
    "practice_generation": "question_generation",
    "subjective_grading": "subjective_grading",
    "coach_reply": "coach_messages",
    "challenge_plan": None,
    "json_repair": None,
    # A dialogue turn is a coach answer: same shape, same cost.
    "conversation_turn": "coach_messages",
}


@dataclass(frozen=True)
class ProviderRuntime:
    id: UUID
    name: str
    base_url: str
    model_id: str
    api_key_ciphertext: str
    custom_headers: dict[str, str]
    timeout_seconds: int


@dataclass
class AiGenerationError(Exception):
    code: str
    message: str
    retryable: bool
    attempts: int = 0
    repair_count: int = 0
    provider_name: str | None = None
    model_id: str | None = None

    def __str__(self) -> str:
        return self.message


def _canonical_request(task_type: str, context: dict[str, Any]) -> tuple[str, str]:
    encoded = json.dumps(
        {"task_type": task_type, "context": context},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return encoded.decode("utf-8"), hashlib.sha256(encoded).hexdigest()


def _job_response(job: AiJob) -> AiJobStatusResponse:
    return AiJobStatusResponse(
        id=job.id,
        task_type=job.task_type,
        status=job.status,
        quota_kind=job.quota_kind,
        provider_id=job.provider_id,
        provider_name=job.provider_name,
        model_id=job.model_id,
        attempt_count=job.attempt_count,
        repair_count=job.repair_count,
        result_summary=job.result_summary,
        error=(
            {
                "code": job.error_code,
                "message": job.error_message or "The AI task failed.",
                "retryable": job.retryable,
            }
            if job.error_code
            else None
        ),
        created_at=job.created_at,
        started_at=job.started_at,
        finished_at=job.finished_at,
    )


def _ledger_response(job: AiJob) -> AiJobStatusResponse:
    return _job_response(job)


async def _providers_for_job(
    session: AsyncSession,
    settings: Settings,
    owner_id: UUID,
    preferred_id: UUID | None,
) -> list[ProviderRuntime]:
    providers = list(
        (
            await session.scalars(
                select(AiProvider)
                .where(
                    AiProvider.owner_id == owner_id,
                    AiProvider.enabled.is_(True),
                )
                .order_by(
                    # Priority decides the order; "default" only breaks ties.
                    AiProvider.priority.asc(),
                    AiProvider.is_default.desc(),
                    AiProvider.created_at.asc(),
                )
            )
        ).all()
    )
    if preferred_id is not None:
        providers.sort(key=lambda provider: 0 if provider.id == preferred_id else 1)
    runtime: list[ProviderRuntime] = []
    cipher = ApiKeyCipher(settings.secret_encryption_key.get_secret_value())
    for provider in providers:
        try:
            cipher.decrypt(provider.api_key_ciphertext)
        except ValueError:
            logger.warning("ai.provider_key_unreadable", extra={"provider_id": str(provider.id)})
            continue
        runtime.append(
            ProviderRuntime(
                id=provider.id,
                name=provider.name,
                base_url=provider.base_url,
                model_id=provider.model_id,
                api_key_ciphertext=provider.api_key_ciphertext,
                custom_headers=provider.custom_headers,
                timeout_seconds=provider.timeout_seconds,
            )
        )
    return runtime


async def _reserve_quota(
    session: AsyncSession,
    *,
    settings: Settings,
    user: User,
    job: AiJob,
    amount: int = 1,
    quota_items: list[str] | None = None,
) -> None:
    if job.quota_kind is None:
        return
    items = quota_items or ["job"]
    if len(set(items)) != len(items):
        raise AppError(
            status_code=422,
            code="AI_QUOTA_ITEM_DUPLICATE",
            message="AI quota items must be unique.",
        )
    unit_count = len(items)
    limits = await resolved_quota_limits(session, user.id, settings)
    limit = limits[job.quota_kind]
    local_date = local_date_for(settings, user)
    # Serialize reserve/consume operations for one user, day, and quota kind.
    lock_key = 7_100_000 + (user.id.int % 1_000_000)
    await session.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": lock_key})
    used = int(
        await session.scalar(
            select(func.coalesce(func.sum(AiUsageLedger.consumed), 0)).where(
                AiUsageLedger.user_id == user.id,
                AiUsageLedger.local_date == local_date,
                AiUsageLedger.quota_kind == job.quota_kind,
                AiUsageLedger.status == "consumed",
            )
        )
        or 0
    )
    reserved = int(
        await session.scalar(
            select(func.count(AiUsageLedger.id)).where(
                AiUsageLedger.user_id == user.id,
                AiUsageLedger.local_date == local_date,
                AiUsageLedger.quota_kind == job.quota_kind,
                AiUsageLedger.status == "reserved",
            )
        )
        or 0
    )
    if limit >= 0 and used + reserved + unit_count > limit:
        raise AppError(
            status_code=429,
            code="AI_QUOTA_EXHAUSTED",
            message="The daily AI quota has been exhausted.",
            details={"quota_kind": job.quota_kind, "limit": limit},
        )
    for item in items:
        session.add(
            AiUsageLedger(
                user_id=user.id,
                job_id=job.id,
                local_date=local_date,
                quota_kind=job.quota_kind,
                quota_item=item,
                reserved=1 if quota_items else amount,
                status="reserved",
            )
        )


async def _consume_quota(session: AsyncSession, job_id: UUID) -> None:
    ledgers = list(
        (
            await session.scalars(
                select(AiUsageLedger).where(AiUsageLedger.job_id == job_id).with_for_update()
            )
        ).all()
    )
    for ledger in ledgers:
        if ledger.status == "reserved":
            amount = ledger.reserved
            ledger.status = "consumed"
            ledger.reserved = 0
            ledger.consumed = amount
            ledger.released = 0


async def _release_quota(session: AsyncSession, job_id: UUID) -> None:
    ledgers = list(
        (
            await session.scalars(
                select(AiUsageLedger).where(AiUsageLedger.job_id == job_id).with_for_update()
            )
        ).all()
    )
    for ledger in ledgers:
        if ledger.status == "reserved":
            amount = ledger.reserved
            ledger.status = "released"
            ledger.reserved = 0
            ledger.consumed = 0
            ledger.released = amount


def _event(job: AiJob, event_type: str, *, metadata: dict[str, Any] | None = None) -> AiJobEvent:
    return AiJobEvent(
        job_id=job.id,
        event_type=event_type,
        status=job.status,
        metadata_json=metadata or {},
    )


async def create_ai_job(
    session: AsyncSession,
    pool: ArqRedis,
    user: User,
    settings: Settings,
    payload: AiJobCreateRequest,
    *,
    idempotency_key: str,
    quota_amount: int = 1,
    quota_items: list[str] | None = None,
    commit: bool = True,
    background: bool = False,
) -> tuple[AiJobStatusResponse, bool]:
    if not idempotency_key or len(idempotency_key) > 128:
        raise AppError(
            status_code=422,
            code="AI_IDEMPOTENCY_KEY_INVALID",
            message="The Idempotency-Key must be between 1 and 128 characters.",
        )
    if quota_items is not None and not 1 <= len(quota_items) <= 50:
        raise AppError(
            status_code=422,
            code="AI_QUOTA_AMOUNT_INVALID",
            message="The AI quota amount is invalid.",
        )
    if not 1 <= quota_amount <= 50:
        raise AppError(
            status_code=422,
            code="AI_QUOTA_AMOUNT_INVALID",
            message="The AI quota amount is invalid.",
        )
    task_type = payload.task_type
    context = payload.context.model_dump(mode="json")
    canonical, request_hash = _canonical_request(task_type, context)
    if len(canonical.encode("utf-8")) > settings.ai_job_max_context_bytes:
        raise AppError(
            status_code=413,
            code="AI_CONTEXT_TOO_LARGE",
            message="The AI task context is too large.",
        )
    existing = await session.scalar(
        select(AiJob).where(AiJob.user_id == user.id, AiJob.idempotency_key == idempotency_key)
    )
    if existing is not None:
        if existing.request_hash != request_hash:
            raise AppError(
                status_code=409,
                code="AI_IDEMPOTENCY_CONFLICT",
                message="The Idempotency-Key was used for a different AI task.",
            )
        return _job_response(existing), True

    prompt = await session.scalar(select(AiPrompt).where(AiPrompt.prompt_key == task_type))
    if prompt is None:
        raise AppError(
            status_code=503,
            code="AI_PROMPT_NOT_CONFIGURED",
            message="The AI prompt is not configured.",
        )
    providers = await _providers_for_job(session, settings, user.id, None)
    if not providers:
        raise AppError(
            status_code=503,
            code="AI_PROVIDER_UNAVAILABLE",
            message="No enabled AI provider is available.",
        )
    job_id = uuid4()
    # Background pre-generation must not hold the learner's interactive slots.
    acquired = True
    if not background:
        acquired = await acquire_concurrency_slot(
            pool,
            user_id=user.id,
            job_id=job_id,
            limit=settings.ai_concurrency_limit,
            stale_seconds=settings.ai_job_stale_seconds,
        )
    if not acquired:
        raise AppError(
            status_code=429,
            code="AI_CONCURRENCY_LIMIT",
            message="At most two AI tasks may run at the same time.",
            details={"limit": settings.ai_concurrency_limit},
        )
    job = AiJob(
        id=job_id,
        user_id=user.id,
        task_type=task_type,
        status="queued",
        quota_kind=TASK_QUOTA_KIND[task_type],
        provider_id=providers[0].id,
        provider_name=providers[0].name,
        model_id=providers[0].model_id,
        prompt_key=task_type,
        prompt_snapshot=prompt.template,
        input_context=context,
        idempotency_key=idempotency_key,
        request_hash=request_hash,
    )
    try:
        session.add(job)
        await session.flush()
        if not background:
            # Pre-generated practice is background prefetch: it must not spend
            # the learner's interactive daily quota.
            await _reserve_quota(
                session,
                settings=settings,
                user=user,
                job=job,
                amount=quota_amount,
                quota_items=quota_items,
            )
        session.add(_event(job, "ai.job.created", metadata={"task_type": task_type}))
        if commit:
            await session.commit()
    except IntegrityError:
        await release_concurrency_slot(pool, user_id=user.id, job_id=job_id)
        if not commit:
            raise AppError(
                status_code=409,
                code="AI_IDEMPOTENCY_CONFLICT",
                message="The AI task could not be created because its idempotency key is in use.",
            ) from None
        await session.rollback()
        existing = await session.scalar(
            select(AiJob).where(AiJob.user_id == user.id, AiJob.idempotency_key == idempotency_key)
        )
        if existing is not None and existing.request_hash == request_hash:
            return _job_response(existing), True
        raise AppError(
            status_code=409,
            code="AI_IDEMPOTENCY_CONFLICT",
            message="The AI task could not be created because its idempotency key is in use.",
        ) from None
    except AppError:
        await release_concurrency_slot(pool, user_id=user.id, job_id=job_id)
        if commit:
            await session.rollback()
        raise
    if not commit:
        return _job_response(job), False
    try:
        await pool.enqueue_job(
            "process_ai_job",
            str(job.id),
            _job_id=f"ai:{job.id}",
            _queue_name=WORDBOOK_QUEUE_NAME,
        )
    except Exception as exc:
        await session.rollback()
        async with session.begin():
            stored = await session.get(AiJob, job.id, with_for_update=True)
            if stored is not None and stored.status == "queued":
                stored.status = "failed"
                stored.error_code = "AI_QUEUE_UNAVAILABLE"
                stored.error_message = "The AI task queue is unavailable."
                stored.retryable = True
                stored.finished_at = utcnow()
                session.add(
                    _event(stored, "ai.job.failed", metadata={"error_code": stored.error_code})
                )
                await _apply_coach_failure(session, stored)
                await _apply_challenge_failure(session, stored)
                await _release_quota(session, stored.id)
        await release_concurrency_slot(pool, user_id=user.id, job_id=job.id)
        raise AppError(
            status_code=503,
            code="AI_QUEUE_UNAVAILABLE",
            message="The AI task queue is unavailable.",
            headers={"Retry-After": "5"},
        ) from exc
    return _job_response(job), False


async def get_user_job(session: AsyncSession, user: User, job_id: UUID) -> AiJobStatusResponse:
    job = await session.scalar(select(AiJob).where(AiJob.id == job_id, AiJob.user_id == user.id))
    if job is None:
        raise AppError(
            status_code=404, code="AI_JOB_NOT_FOUND", message="The AI task was not found."
        )
    return _job_response(job)


async def cancel_user_job(
    session: AsyncSession,
    pool: ArqRedis,
    user: User,
    job_id: UUID,
) -> AiJobStatusResponse:
    job = await session.scalar(
        select(AiJob).where(AiJob.id == job_id, AiJob.user_id == user.id).with_for_update()
    )
    if job is None:
        raise AppError(
            status_code=404, code="AI_JOB_NOT_FOUND", message="The AI task was not found."
        )
    if job.status == "cancelled":
        return _job_response(job)
    if job.status in {"succeeded", "failed", "stale"}:
        raise AppError(
            status_code=409,
            code="AI_JOB_ALREADY_TERMINAL",
            message="The AI task has already finished.",
        )
    job.status = "cancelled"
    job.finished_at = utcnow()
    job.error_code = "AI_JOB_CANCELLED"
    job.error_message = "The AI task was cancelled."
    job.retryable = False
    session.add(_event(job, "ai.job.cancelled"))
    await _apply_practice_failure(session, job)
    await _apply_coach_failure(session, job)
    await _apply_challenge_failure(session, job)
    await _release_quota(session, job.id)
    await session.commit()
    await release_concurrency_slot(pool, user_id=user.id, job_id=job.id)
    return _job_response(job)


async def _call_with_provider(
    client: ProviderHttpClient,
    settings: Settings,
    provider: ProviderRuntime,
    *,
    prompt: str,
    context: dict[str, Any],
    schema_name: str,
    schema: dict[str, Any],
    repair_text: str | None = None,
    deadline: float | None = None,
    images: list[tuple[str, bytes]] | None = None,
) -> str:
    cipher = ApiKeyCipher(settings.secret_encryption_key.get_secret_value())
    api_key = cipher.decrypt(provider.api_key_ciphertext)
    user_content = (
        json.dumps(context, ensure_ascii=False, sort_keys=True)
        if repair_text is None
        else repair_text
    )
    system_prompt = (
        f"{prompt}\n\nReturn only a JSON object matching this JSON Schema:\n"
        f"{json.dumps(schema, ensure_ascii=False, sort_keys=True)}"
    )
    last_error: ProviderRequestError | None = None
    for attempt in range(settings.ai_provider_retry_limit + 1):
        call_timeout = provider.timeout_seconds
        if deadline is not None:
            call_timeout = min(call_timeout, int(deadline - time.monotonic()))
            if call_timeout <= 2:
                raise ProviderRequestError(
                    code="AI_PROVIDER_TIMEOUT",
                    message="The AI provider timed out.",
                    retryable=True,
                )
        try:
            return await client.chat_json(
                base_url=provider.base_url,
                api_key=api_key,
                custom_headers=provider.custom_headers,
                model_id=provider.model_id,
                timeout_seconds=call_timeout,
                system_prompt=system_prompt,
                user_content=user_content,
                schema_name=schema_name,
                schema=schema,
                images=images,
            )
        except ProviderRequestError as exc:
            last_error = exc
            if not exc.retryable or attempt >= settings.ai_provider_retry_limit:
                raise
            await asyncio.sleep(settings.ai_provider_retry_backoff_seconds * (2**attempt))
    assert last_error is not None
    raise last_error


async def _coach_attachments(
    session: AsyncSession, settings: Settings, job: AiJob
) -> tuple[list[tuple[str, bytes]], list[dict[str, str]]]:
    """Images go to the model as image parts; documents as extracted text."""
    if job.task_type != "coach_reply":
        return [], []
    attachment_ids = job.input_context.get("attachment_ids") or []
    if not attachment_ids:
        return [], []
    rows = list(
        (
            await session.scalars(
                select(CoachAttachment)
                .where(
                    CoachAttachment.id.in_(attachment_ids),
                    CoachAttachment.user_id == job.user_id,
                )
                .order_by(CoachAttachment.created_at.asc())
            )
        ).all()
    )
    images: list[tuple[str, bytes]] = []
    texts: list[dict[str, str]] = []
    budget = 12_000
    for row in rows:
        try:
            if is_image(row.content_type):
                images.append((row.content_type, read_attachment(settings, row)))
                continue
            text = (attachment_text(settings, row) or "").strip()
        except AppError:
            continue
        if text and budget > 0:
            chunk = text[: min(6_000, budget)]
            budget -= len(chunk)
            texts.append({"filename": row.filename, "text": chunk})
    return images, texts


async def generate_structured(
    session: AsyncSession,
    settings: Settings,
    job: AiJob,
) -> tuple[dict[str, Any], dict[str, Any], ProviderRuntime, int, int]:
    providers = await _providers_for_job(session, settings, job.user_id, job.provider_id)
    if not providers:
        raise AiGenerationError(
            code="AI_PROVIDER_UNAVAILABLE",
            message="No enabled AI provider is available.",
            retryable=True,
        )
    schema = output_schema(job.task_type, job.input_context)
    client = ProviderHttpClient(settings)
    attempts = 0
    repairs = 0
    last_error: AiGenerationError | None = None
    deadline = time.monotonic() + settings.ai_generation_budget_seconds
    images, attachment_texts = await _coach_attachments(session, settings, job)
    call_context: dict[str, Any] = dict(job.input_context)
    if attachment_texts:
        call_context["attachment_texts"] = attachment_texts

    def remaining() -> int:
        return int(deadline - time.monotonic())

    for logical_attempt in range(1, 4):
        attempts = logical_attempt
        raw_text: str | None = None
        chosen: ProviderRuntime | None = None
        for provider in providers:
            budget = remaining()
            if budget <= 5:
                raise AiGenerationError(
                    code="AI_GENERATION_TIMEOUT",
                    message="The AI task ran out of time before the provider answered.",
                    retryable=True,
                    attempts=attempts,
                    repair_count=repairs,
                    provider_name=provider.name,
                    model_id=provider.model_id,
                )
            try:
                raw_text = await _call_with_provider(
                    client,
                    settings,
                    provider,
                    prompt=job.prompt_snapshot,
                    context=call_context,
                    schema_name=job.task_type,
                    schema=schema,
                    deadline=deadline,
                    images=images,
                )
                chosen = provider
                break
            except ProviderRequestError as exc:
                last_error = AiGenerationError(
                    code=exc.code,
                    message=exc.message,
                    retryable=exc.retryable,
                    attempts=attempts,
                    repair_count=repairs,
                    provider_name=provider.name,
                    model_id=provider.model_id,
                )
                if not exc.retryable:
                    raise last_error from exc
        if raw_text is None or chosen is None:
            continue
        try:
            result, summary = validate_task_output(
                task_type=job.task_type,
                context=job.input_context,
                raw_text=raw_text,
            )
            return result, summary, chosen, attempts, repairs
        except ValueError as exc:
            last_error = AiGenerationError(
                code="AI_OUTPUT_INVALID",
                message="The AI response did not satisfy the structured schema.",
                retryable=True,
                attempts=attempts,
                repair_count=repairs,
                provider_name=chosen.name,
                model_id=chosen.model_id,
            )
            if repairs >= 1:
                continue
            repairs += 1
            try:
                repaired = await _call_with_provider(
                    client,
                    settings,
                    chosen,
                    prompt=job.prompt_snapshot,
                    context=job.input_context,
                    schema_name=job.task_type,
                    schema=schema,
                    repair_text=repair_prompt(raw_text, str(exc)),
                    deadline=deadline,
                )
                result, summary = validate_task_output(
                    task_type=job.task_type,
                    context=job.input_context,
                    raw_text=repaired,
                )
                return result, summary, chosen, attempts, repairs
            except (ProviderRequestError, ValueError) as repair_error:
                last_error = AiGenerationError(
                    code="AI_OUTPUT_INVALID",
                    message="The AI response could not be repaired.",
                    retryable=True,
                    attempts=attempts,
                    repair_count=repairs,
                    provider_name=chosen.name,
                    model_id=chosen.model_id,
                )
                if isinstance(repair_error, ProviderRequestError) and not repair_error.retryable:
                    raise AiGenerationError(
                        code=repair_error.code,
                        message=repair_error.message,
                        retryable=False,
                        attempts=attempts,
                        repair_count=repairs,
                        provider_name=chosen.name,
                        model_id=chosen.model_id,
                    ) from repair_error
    raise last_error or AiGenerationError(
        code="AI_GENERATION_FAILED",
        message="The AI task failed after the allowed attempts.",
        retryable=True,
        attempts=attempts,
        repair_count=repairs,
    )


async def _apply_practice_success(session: AsyncSession, job: AiJob) -> None:
    from app.services.conversation import materialize_conversation_turn
    from app.services.practice import (
        materialize_practice_generation,
        materialize_practice_grading,
    )

    if job.task_type == "practice_generation":
        await materialize_practice_generation(session, job)
    elif job.task_type == "subjective_grading" and job.input_context.get("practice_submission_id"):
        await materialize_practice_grading(session, job)
    elif job.task_type == "conversation_turn":
        await materialize_conversation_turn(session, job)


async def _apply_practice_failure(session: AsyncSession, job: AiJob) -> None:
    from app.services.conversation import mark_conversation_turn_failed
    from app.services.practice import (
        mark_practice_generation_failed,
        mark_practice_grading_failed,
    )

    if job.task_type == "practice_generation":
        await mark_practice_generation_failed(session, job)
    elif job.task_type == "subjective_grading" and job.input_context.get("practice_submission_id"):
        await mark_practice_grading_failed(session, job)
    elif job.task_type == "conversation_turn":
        await mark_conversation_turn_failed(session, job)


async def _apply_coach_success(
    session: AsyncSession,
    job: AiJob,
    settings: Settings,
    redis: ArqRedis,
) -> list[tuple[UUID, UUID]]:
    from app.services.coach import materialize_coach_success

    return await materialize_coach_success(session, job, settings, redis)


async def _finalize_coach_success(session: AsyncSession, job: AiJob, settings: Settings) -> None:
    from app.services.coach import finalize_coach_success

    await finalize_coach_success(session, job, settings)


async def _apply_coach_failure(session: AsyncSession, job: AiJob) -> None:
    if job.task_type != "coach_reply":
        return
    from app.services.coach import mark_coach_failed

    await mark_coach_failed(session, job)


async def _enqueue_deferred_coach_jobs(
    redis: ArqRedis,
    session_factory,
    deferred: list[tuple[UUID, UUID]],
    *,
    user_id: UUID,
) -> None:
    from app.models.coach import CoachActionReceipt
    from app.models.practice import PracticeGeneration, PracticeSession

    for job_id, receipt_id in deferred:
        try:
            await redis.enqueue_job(
                "process_ai_job",
                str(job_id),
                _job_id=f"ai:{job_id}",
                _queue_name=WORDBOOK_QUEUE_NAME,
            )
        except Exception:
            logger.exception("ai.job.deferred_enqueue_failed", extra={"job_id": str(job_id)})
            async with session_factory() as session:
                job = await session.scalar(
                    select(AiJob).where(AiJob.id == job_id).with_for_update()
                )
                if job is not None and job.status == "queued":
                    job.status = "failed"
                    job.error_code = "AI_QUEUE_UNAVAILABLE"
                    job.error_message = "The AI task queue is unavailable."
                    job.retryable = True
                    job.finished_at = utcnow()
                    session.add(
                        _event(job, "ai.job.failed", metadata={"error_code": job.error_code})
                    )
                    await _release_quota(session, job.id)
                practice = await session.scalar(
                    select(PracticeSession).where(PracticeSession.ai_job_id == job_id)
                )
                if practice is not None:
                    practice.status = "failed"
                    practice.error_code = "AI_QUEUE_UNAVAILABLE"
                    practice.error_message = "The practice queue is unavailable."
                    generation = await session.scalar(
                        select(PracticeGeneration).where(PracticeGeneration.ai_job_id == job_id)
                    )
                    if generation is not None:
                        generation.status = "failed"
                        generation.error_code = "AI_QUEUE_UNAVAILABLE"
                        generation.error_message = "The practice queue is unavailable."
                receipt = await session.get(CoachActionReceipt, receipt_id, with_for_update=True)
                if receipt is not None:
                    receipt.status = "conflict"
                    receipt.conflict_code = "COACH_ACTION_QUEUE_UNAVAILABLE"
                    receipt.conflict_message = "The requested practice could not be queued."
                await session.commit()
            await release_concurrency_slot(redis, user_id=user_id, job_id=job_id)


async def _apply_challenge_success(session: AsyncSession, job: AiJob, settings: Settings) -> None:
    from app.services.challenge import materialize_challenge_plan

    await materialize_challenge_plan(session, job, settings)


async def _apply_challenge_failure(session: AsyncSession, job: AiJob) -> None:
    if job.task_type != "challenge_plan":
        return
    from app.services.challenge import mark_challenge_failed

    await mark_challenge_failed(session, job)


async def _notify_ai_terminal(session: AsyncSession, job: AiJob, *, succeeded: bool) -> None:
    from app.services.notifications import notify_ai_job

    try:
        await notify_ai_job(session, job, succeeded=succeeded)
    except Exception:
        logger.exception(
            "ai.job.notification_outbox_failed",
            extra={"job_id": str(job.id), "succeeded": succeeded},
        )


async def process_ai_job(ctx: dict[str, Any], job_id: str) -> dict[str, Any]:
    factory = ctx["session_factory"]
    settings: Settings = ctx["settings"]
    redis = ctx["redis"]
    job_uuid = UUID(job_id)
    async with factory() as session:
        job = await session.scalar(select(AiJob).where(AiJob.id == job_uuid).with_for_update())
        if job is None or job.status in {"succeeded", "failed", "cancelled", "stale"}:
            await session.rollback()
            return {"status": "skipped"}
        job.status = "running"
        job.started_at = utcnow()
        job.attempt_count = max(job.attempt_count, 1)
        session.add(_event(job, "ai.job.started"))
        await session.commit()
        user = await session.get(User, job.user_id)
        if user is None:
            user = User(id=job.user_id, username="deleted", username_normalized="deleted")
    try:
        async with factory() as session:
            job = await session.get(AiJob, job_uuid)
            assert job is not None
            result, summary, provider, attempts, repairs = await generate_structured(
                session, settings, job
            )
    except AiGenerationError as exc:
        async with factory() as session:
            job = await session.scalar(select(AiJob).where(AiJob.id == job_uuid).with_for_update())
            if job is not None and job.status == "running":
                job.status = "failed"
                job.attempt_count = max(job.attempt_count, exc.attempts)
                job.repair_count = exc.repair_count
                job.error_code = exc.code
                job.error_message = exc.message[:500]
                job.retryable = exc.retryable
                job.provider_name = exc.provider_name or job.provider_name
                job.model_id = exc.model_id or job.model_id
                job.finished_at = utcnow()
                session.add(_event(job, "ai.job.failed", metadata={"error_code": exc.code}))
                await _apply_practice_failure(session, job)
                await _apply_coach_failure(session, job)
                await _apply_challenge_failure(session, job)
                await _notify_ai_terminal(session, job, succeeded=False)
                await _release_quota(session, job.id)
                await session.commit()
            else:
                await session.rollback()
        await release_concurrency_slot(redis, user_id=job.user_id, job_id=job_uuid)
        return {"status": "failed", "error_code": exc.code}
    except Exception:
        logger.exception("ai.job.unexpected_failure", extra={"job_id": job_id})
        async with factory() as session:
            job = await session.scalar(select(AiJob).where(AiJob.id == job_uuid).with_for_update())
            if job is not None and job.status == "running":
                job.status = "failed"
                job.error_code = "AI_INTERNAL_ERROR"
                job.error_message = "The AI task failed unexpectedly."
                job.retryable = True
                job.finished_at = utcnow()
                session.add(_event(job, "ai.job.failed", metadata={"error_code": job.error_code}))
                await _apply_practice_failure(session, job)
                await _apply_coach_failure(session, job)
                await _apply_challenge_failure(session, job)
                await _notify_ai_terminal(session, job, succeeded=False)
                await _release_quota(session, job.id)
                await session.commit()
            else:
                await session.rollback()
        await release_concurrency_slot(redis, user_id=user.id, job_id=job_uuid)
        return {"status": "failed", "error_code": "AI_INTERNAL_ERROR"}
    except asyncio.CancelledError:
        # ARQ cancels the coroutine on its job timeout. Without this branch the
        # job would stay "running" until the stale sweep, leaving the learner on
        # a spinner; record a real failure the poller can surface right away.
        logger.warning("ai.job.worker_timeout", extra={"job_id": job_id})
        try:
            async with factory() as session:
                job = await session.scalar(
                    select(AiJob).where(AiJob.id == job_uuid).with_for_update()
                )
                if job is not None and job.status == "running":
                    job.status = "failed"
                    job.error_code = "AI_JOB_TIMEOUT"
                    job.error_message = "The AI task timed out before the provider answered."
                    job.retryable = True
                    job.finished_at = utcnow()
                    session.add(
                        _event(job, "ai.job.failed", metadata={"error_code": job.error_code})
                    )
                    await _apply_practice_failure(session, job)
                    await _apply_coach_failure(session, job)
                    await _apply_challenge_failure(session, job)
                    await _notify_ai_terminal(session, job, succeeded=False)
                    await _release_quota(session, job.id)
                    await session.commit()
                else:
                    await session.rollback()
        except Exception:  # noqa: BLE001 - never mask the original cancellation
            logger.exception("ai.job.timeout_cleanup_failed", extra={"job_id": job_id})
        try:
            await release_concurrency_slot(redis, user_id=job.user_id, job_id=job_uuid)
        except BaseException:  # noqa: BLE001 - keep the cancellation as the outcome
            logger.exception("ai.job.timeout_release_failed", extra={"job_id": job_id})
        raise

    async with factory() as session:
        job = await session.scalar(select(AiJob).where(AiJob.id == job_uuid).with_for_update())
        if job is None or job.status != "running":
            await session.rollback()
            await release_concurrency_slot(redis, user_id=user.id, job_id=job_uuid)
            return {"status": "discarded"}
        job.status = "succeeded"
        job.result = result
        job.result_summary = summary
        job.provider_id = provider.id
        job.provider_name = provider.name
        job.model_id = provider.model_id
        job.attempt_count = attempts
        job.repair_count = repairs
        job.error_code = None
        job.error_message = None
        job.retryable = False
        job.finished_at = utcnow()
        session.add(_event(job, "ai.job.succeeded"))
        deferred_coach_jobs: list[tuple[UUID, UUID]] = []
        try:
            await _apply_practice_success(session, job)
            await _consume_quota(session, job.id)
            if job.task_type == "coach_reply":
                deferred_coach_jobs = await _apply_coach_success(session, job, settings, redis)
                await _finalize_coach_success(session, job, settings)
            elif job.task_type == "challenge_plan":
                await _apply_challenge_success(session, job, settings)
            await _notify_ai_terminal(session, job, succeeded=True)
        except Exception:
            logger.exception("ai.job.result_hook_failed", extra={"job_id": job_id})
            await session.rollback()
            failed: AiJob | None = None
            async with factory() as failure_session:
                failed = await failure_session.scalar(
                    select(AiJob).where(AiJob.id == job_uuid).with_for_update()
                )
                if failed is not None and failed.status == "running":
                    failed.status = "failed"
                    failed.error_code = (
                        "AI_COACH_HOOK_FAILED"
                        if failed.task_type == "coach_reply"
                        else "AI_PRACTICE_HOOK_FAILED"
                    )
                    failed.error_message = (
                        "The generated coach result could not be persisted."
                        if failed.task_type == "coach_reply"
                        else "The generated practice result could not be persisted."
                    )
                    failed.retryable = True
                    failed.finished_at = utcnow()
                    failure_session.add(
                        _event(
                            failed,
                            "ai.job.failed",
                            metadata={"error_code": failed.error_code},
                        )
                    )
                    await _apply_practice_failure(failure_session, failed)
                    await _apply_coach_failure(failure_session, failed)
                    await _apply_challenge_failure(failure_session, failed)
                    await _release_quota(failure_session, failed.id)
                    await failure_session.commit()
                else:
                    await failure_session.rollback()
            await release_concurrency_slot(redis, user_id=user.id, job_id=job_uuid)
            return {
                "status": "failed",
                "error_code": failed.error_code
                if failed is not None
                else "AI_PRACTICE_HOOK_FAILED",
            }
        await session.commit()
    if deferred_coach_jobs:
        await _enqueue_deferred_coach_jobs(redis, factory, deferred_coach_jobs, user_id=user.id)
    await release_concurrency_slot(redis, user_id=user.id, job_id=job_uuid)
    return {"status": "succeeded"}


async def reconcile_stale_ai_jobs(
    session: AsyncSession,
    redis: Any,
    settings: Settings,
    *,
    stale_before: datetime,
) -> int:
    jobs = list(
        (
            await session.scalars(
                select(AiJob)
                .where(
                    AiJob.status.in_(("queued", "running")),
                    AiJob.updated_at < stale_before,
                )
                .order_by(AiJob.created_at.asc())
                .limit(100)
                .with_for_update(skip_locked=True)
            )
        ).all()
    )
    for job in jobs:
        job.status = "stale"
        job.error_code = "AI_JOB_STALE"
        job.error_message = "The AI task did not finish before its stale deadline."
        job.retryable = True
        job.finished_at = utcnow()
        session.add(_event(job, "ai.job.stale"))
        await _apply_practice_failure(session, job)
        await _apply_coach_failure(session, job)
        await _apply_challenge_failure(session, job)
        await _notify_ai_terminal(session, job, succeeded=False)
        await _release_quota(session, job.id)
        await release_concurrency_slot(redis, user_id=job.user_id, job_id=job.id)
    if jobs:
        await session.commit()
    return len(jobs)
