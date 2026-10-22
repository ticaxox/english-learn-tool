import logging
from typing import Any

from arq import cron
from sqlalchemy import select

from app.models.wordbooks import WordbookJob
from app.services.wordbook_jobs import arq_job_id
from app.services.wordbooks import cleanup_expired_wordbook_artifacts
from app.workers.common import get_redis_settings
from app.workers.runtime import worker_runtime_shutdown, worker_runtime_startup

logger = logging.getLogger(__name__)


async def scheduler_tick(ctx: dict[str, Any]) -> None:
    """Recover queued wordbook jobs and remove expired isolated artifacts."""
    factory = ctx.get("session_factory")
    if factory is None:
        logger.info("scheduler.tick", extra={"worker": "scheduler"})
        return
    queued: list[WordbookJob] = []
    async with factory() as session:
        cleanup = await cleanup_expired_wordbook_artifacts(
            session,
            ctx["wordbook_storage"],
        )
        queued = list(
            (
                await session.scalars(
                    select(WordbookJob)
                    .where(
                        WordbookJob.status == "queued",
                        WordbookJob.attempts < WordbookJob.max_attempts,
                    )
                    .order_by(WordbookJob.created_at.asc())
                    .limit(100)
                )
            ).all()
        )
    enqueued = 0
    for job in queued:
        result = await ctx["redis"].enqueue_job(
            "process_wordbook_job",
            str(job.id),
            _job_id=arq_job_id(job.id),
        )
        enqueued += int(result is not None)
    logger.info(
        "scheduler.wordbook_tick",
        extra={
            "queued_candidates": len(queued),
            "enqueued": enqueued,
            "expired_jobs": cleanup["jobs"],
            "expired_previews": cleanup["previews"],
        },
    )


class SchedulerSettings:
    functions = [scheduler_tick]
    cron_jobs = [cron(scheduler_tick, minute=set(range(60)), unique=False)]
    redis_settings = get_redis_settings()
    on_startup = worker_runtime_startup
    on_shutdown = worker_runtime_shutdown
    max_jobs = 1
    job_timeout = 60
    keep_result = 300
    health_check_interval = 30
    health_check_key = "english-learn:scheduler-health"
