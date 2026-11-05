import logging
from typing import Any

from app.services.ai_jobs import process_ai_job
from app.services.practice_pool import ensure_pool_for_user_id
from app.services.wordbook_jobs import process_wordbook_job
from app.services.wordbook_queue import WORDBOOK_QUEUE_NAME
from app.workers.common import get_redis_settings
from app.workers.runtime import worker_runtime_shutdown, worker_runtime_startup

logger = logging.getLogger(__name__)


async def worker_heartbeat(ctx: dict[str, Any]) -> dict[str, str]:
    """Technical worker liveness job; it performs no business operation."""
    logger.info("worker.heartbeat", extra={"worker": "worker"})
    return {"status": "ok"}


async def replenish_practice_pool(ctx: dict[str, Any], user_id: str) -> dict[str, int]:
    """Refill the pre-generated practice stock after a set is claimed."""
    async with ctx["session_factory"]() as session:
        return await ensure_pool_for_user_id(session, ctx["redis"], ctx["settings"], user_id)


class WorkerSettings:
    functions = [worker_heartbeat, process_wordbook_job, process_ai_job, replenish_practice_pool]
    queue_name = WORDBOOK_QUEUE_NAME
    redis_settings = get_redis_settings()
    on_startup = worker_runtime_startup
    on_shutdown = worker_runtime_shutdown
    max_jobs = 4
    # The provider budget is timeout (up to 120 s) × (retry limit + 1) plus
    # backoff, so the worker must outlast that worst case and still write the
    # failure state instead of being killed mid-job.
    job_timeout = 600
    keep_result = 3600
    health_check_interval = 30
    health_check_key = "english-learn:worker-health"
