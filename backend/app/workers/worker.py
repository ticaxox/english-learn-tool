import logging
from typing import Any

from app.workers.common import get_redis_settings

logger = logging.getLogger(__name__)


async def worker_heartbeat(ctx: dict[str, Any]) -> dict[str, str]:
    """Technical worker liveness job; it performs no business operation."""
    logger.info("worker.heartbeat", extra={"worker": "worker"})
    return {"status": "ok"}


class WorkerSettings:
    functions = [worker_heartbeat]
    redis_settings = get_redis_settings()
    max_jobs = 4
    job_timeout = 300
    keep_result = 3600
    health_check_interval = 30
    health_check_key = "english-learn:worker-health"
