from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any
from uuid import UUID

from arq import cron
from sqlalchemy import or_, select

from app.models.wordbooks import WordbookJob
from app.services.ai_jobs import reconcile_stale_ai_jobs
from app.services.auth import utcnow
from app.services.notifications import (
    cleanup_expired_notifications,
    enqueue_scheduled_notification_events,
    process_notification_outbox,
)
from app.services.wordbook_queue import (
    SCHEDULER_QUEUE_NAME,
    QueueDispatchKind,
    WordbookQueueDispatch,
    clear_wordbook_queue_entry,
    dispatch_wordbook_job,
    force_requeue_wordbook_job,
)
from app.services.wordbooks import (
    cleanup_expired_wordbook_artifacts,
    record_wordbook_queue_failure,
)
from app.workers.common import get_redis_settings
from app.workers.runtime import worker_runtime_shutdown, worker_runtime_startup

logger = logging.getLogger(__name__)


def _dispatch_failure(dispatch: WordbookQueueDispatch) -> tuple[str, str]:
    if dispatch.kind is QueueDispatchKind.STALE:
        return (
            "WORDBOOK_QUEUE_ENTRY_STALE",
            "The background queue entry expired before a worker completed it.",
        )
    if dispatch.kind is QueueDispatchKind.TERMINAL_SUCCESS:
        return (
            "WORDBOOK_QUEUE_RESULT_INCONSISTENT",
            "The background queue result did not match the persisted job state.",
        )
    if dispatch.kind is QueueDispatchKind.TERMINAL_FAILURE:
        return (
            dispatch.error_code or "WORDBOOK_ARQ_JOB_FAILED",
            dispatch.error_message or "The background worker could not execute the job.",
        )
    return (
        "WORDBOOK_QUEUE_ENTRY_MISSING",
        "The background queue entry disappeared before execution.",
    )


async def _recover_wordbook_job(
    ctx: dict[str, Any],
    job_id: UUID,
    *,
    stale_before,
) -> str:
    factory = ctx["session_factory"]
    settings = ctx["settings"]
    pool = ctx["redis"]
    async with factory() as session:
        job = await session.scalar(
            select(WordbookJob).where(WordbookJob.id == job_id).with_for_update()
        )
        if job is None or job.status in {"succeeded", "failed", "cancelled"}:
            await session.rollback()
            return "terminal"

        recovered_running = False
        if job.status == "running":
            if job.updated_at > stale_before:
                await session.rollback()
                return "running"
            job = await record_wordbook_queue_failure(
                session,
                job_id=job.id,
                reason_code="WORDBOOK_WORKER_INTERRUPTED",
                reason_message="The wordbook worker was interrupted before completion.",
                increment_attempts=False,
            )
            recovered_running = True
            if job.status == "failed":
                await clear_wordbook_queue_entry(pool, job.id)
                return "interrupted_failed"
        elif job.status != "queued":
            await session.rollback()
            return "skipped"

        try:
            dispatch = await dispatch_wordbook_job(
                pool,
                job.id,
                stale_after_seconds=settings.wordbook_job_stale_seconds,
            )
        except Exception:
            logger.exception(
                "scheduler.wordbook_enqueue_failed",
                extra={"job_id": str(job.id)},
            )
            failed_job = await record_wordbook_queue_failure(
                session,
                job_id=job.id,
                reason_code="WORDBOOK_QUEUE_UNAVAILABLE",
                reason_message="The background queue is unavailable.",
                increment_attempts=True,
            )
            return "enqueue_failed" if failed_job.status == "failed" else "enqueue_retry"

        if dispatch.kind in {QueueDispatchKind.ENQUEUED, QueueDispatchKind.ACTIVE}:
            await session.rollback()
            return dispatch.kind.value

        reason_code, reason_message = _dispatch_failure(dispatch)
        failed_job = await record_wordbook_queue_failure(
            session,
            job_id=job.id,
            reason_code=reason_code,
            reason_message=reason_message,
            increment_attempts=not recovered_running,
        )
        if failed_job.status == "failed":
            await clear_wordbook_queue_entry(pool, job.id)
            return "failed"
        try:
            await force_requeue_wordbook_job(
                pool,
                job.id,
                stale_after_seconds=settings.wordbook_job_stale_seconds,
            )
        except Exception:
            logger.exception(
                "scheduler.wordbook_requeue_failed",
                extra={"job_id": str(job.id), "reason_code": reason_code},
            )
            return "requeue_failed"
        return "recovered"


async def scheduler_tick(ctx: dict[str, Any]) -> None:
    """Recover stale durable jobs and remove expired wordbook artifacts."""

    factory = ctx.get("session_factory")
    if factory is None:
        logger.info("scheduler.tick", extra={"worker": "scheduler"})
        return
    settings = ctx["settings"]
    stale_before = utcnow() - timedelta(seconds=settings.wordbook_job_stale_seconds)
    ai_stale_before = utcnow() - timedelta(seconds=settings.ai_job_stale_seconds)
    async with factory() as session:
        ai_stale_count = await reconcile_stale_ai_jobs(
            session,
            ctx["redis"],
            settings,
            stale_before=ai_stale_before,
        )
        cleanup = await cleanup_expired_wordbook_artifacts(
            session,
            ctx["wordbook_storage"],
        )
        notification_now = utcnow()
        notification_created = await enqueue_scheduled_notification_events(
            session,
            settings,
            now=notification_now,
        )
        notification_processed = await process_notification_outbox(
            session,
            settings,
            now=notification_now,
        )
        notification_cleaned = await cleanup_expired_notifications(
            session,
            settings,
            now=notification_now,
        )
        candidate_ids = list(
            (
                await session.scalars(
                    select(WordbookJob.id)
                    .where(
                        or_(
                            WordbookJob.status == "queued",
                            (WordbookJob.status == "running")
                            & (WordbookJob.updated_at < stale_before),
                        )
                    )
                    .order_by(WordbookJob.created_at.asc())
                    .limit(100)
                )
            ).all()
        )

    results: dict[str, int] = {}
    for job_id in candidate_ids:
        outcome = await _recover_wordbook_job(
            ctx,
            job_id,
            stale_before=stale_before,
        )
        results[outcome] = results.get(outcome, 0) + 1
    logger.info(
        "scheduler.wordbook_tick",
        extra={
            "queued_candidates": len(candidate_ids),
            "outcomes": results,
            "expired_jobs": cleanup["jobs"],
            "expired_previews": cleanup["previews"],
            "stale_ai_jobs": ai_stale_count,
            "notification_events_created": notification_created,
            "notification_events_processed": notification_processed,
            "expired_notifications": notification_cleaned,
        },
    )


class SchedulerSettings:
    functions = [scheduler_tick]
    queue_name = SCHEDULER_QUEUE_NAME
    cron_jobs = [cron(scheduler_tick, minute=set(range(60)), unique=False)]
    redis_settings = get_redis_settings()
    on_startup = worker_runtime_startup
    on_shutdown = worker_runtime_shutdown
    max_jobs = 1
    job_timeout = 60
    keep_result = 300
    health_check_interval = 30
    health_check_key = "english-learn:scheduler-health"
