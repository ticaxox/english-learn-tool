import logging
from typing import Any

from arq import cron

from app.workers.common import get_redis_settings

logger = logging.getLogger(__name__)


async def scheduler_tick(ctx: dict[str, Any]) -> None:
    """Infrastructure heartbeat; domain schedules will be added by later tasks."""
    logger.info("scheduler.tick", extra={"worker": "scheduler"})


class SchedulerSettings:
    functions = [scheduler_tick]
    cron_jobs = [cron(scheduler_tick, minute=set(range(60)), unique=False)]
    redis_settings = get_redis_settings()
    max_jobs = 1
    job_timeout = 60
    keep_result = 300
    health_check_interval = 30
    health_check_key = "english-learn:scheduler-health"
