from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any
from uuid import UUID
from zoneinfo import ZoneInfo

from arq import cron
from sqlalchemy import or_, select

from app.models.challenge import DailyChallengePlan
from app.models.identity import User, UserProfile
from app.models.wordbooks import WordbookJob
from app.services.ai_jobs import reconcile_stale_ai_jobs
from app.services.auth import utcnow
from app.services.challenge import expire_and_cleanup_challenges, generate_today
from app.services.coach import cleanup_coach_data
from app.services.learning import local_date_for
from app.services.notifications import (
    cleanup_expired_notifications,
    enqueue_scheduled_notification_events,
    process_notification_outbox,
)
from app.services.practice_pool import ensure_pool_for_user_id, pool_users
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
        coach_cleaned = await cleanup_coach_data(
            session,
            settings,
            now=notification_now,
        )
        challenge_cleaned = await expire_and_cleanup_challenges(
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
            "expired_coach_messages": coach_cleaned["messages"],
            "expired_coach_contexts": coach_cleaned["contexts"],
            "expired_challenges": challenge_cleaned["expired"],
            "expired_challenge_contexts": challenge_cleaned["contexts"],
        },
    )


async def practice_pool_tick(ctx: dict[str, Any]) -> None:
    """Top up the pre-generated practice stock for every configured learner."""
    factory = ctx.get("session_factory")
    if factory is None:
        return
    settings = ctx["settings"]
    async with factory() as session:
        user_ids = await pool_users(session)
    results = {"created": 0, "retried": 0, "skipped": 0, "users": 0}
    for user_id in user_ids:
        try:
            async with factory() as session:
                outcome = await ensure_pool_for_user_id(session, ctx["redis"], settings, user_id)
        except Exception:  # noqa: BLE001 - one learner must not stop the tick
            logger.exception("scheduler.practice_pool_failed", extra={"user_id": str(user_id)})
            continue
        results["users"] += 1
        for key in ("created", "retried", "skipped"):
            results[key] += outcome[key]
    if results["users"]:
        logger.info("scheduler.practice_pool_tick", extra=results)


async def challenge_schedule_tick(ctx: dict[str, Any]) -> None:
    """Generate today's learning map for learners whose configured time matches."""
    factory = ctx.get("session_factory")
    if factory is None:
        return
    settings = ctx["settings"]
    now = utcnow()
    local_now = now.astimezone(ZoneInfo(settings.app_timezone))
    current = local_now.strftime("%H:%M")
    async with factory() as session:
        user_ids = list(
            (
                await session.scalars(
                    select(UserProfile.user_id).where(
                        UserProfile.challenge_generation_time == current
                    )
                )
            ).all()
        )
    generated = 0
    for user_id in user_ids:
        async with factory() as session:
            user = await session.get(User, user_id)
            if user is None:
                continue
            local_date = local_date_for(settings, user, now=now)
            existing = await session.scalar(
                select(DailyChallengePlan.id).where(
                    DailyChallengePlan.user_id == user_id,
                    DailyChallengePlan.local_date == local_date,
                )
            )
            if existing is not None:
                continue
            try:
                await generate_today(session, ctx["redis"], user, settings)
                generated += 1
            except Exception:  # noqa: BLE001 - retry on the next matching day
                logger.exception(
                    "scheduler.challenge_generation_failed",
                    extra={"user_id": str(user_id)},
                )
    if user_ids:
        logger.info(
            "scheduler.challenge_schedule_tick",
            extra={"matching_users": len(user_ids), "generated": generated, "at": current},
        )


class SchedulerSettings:
    functions = [scheduler_tick]
    queue_name = SCHEDULER_QUEUE_NAME
    cron_jobs = [
        cron(scheduler_tick, minute=set(range(60)), unique=False),
        cron(practice_pool_tick, minute=set(range(0, 60, 2)), unique=True),
        cron(challenge_schedule_tick, minute=set(range(60)), unique=True),
    ]
    redis_settings = get_redis_settings()
    on_startup = worker_runtime_startup
    on_shutdown = worker_runtime_shutdown
    max_jobs = 1
    job_timeout = 60
    keep_result = 300
    health_check_interval = 30
    health_check_key = "english-learn:scheduler-health"
