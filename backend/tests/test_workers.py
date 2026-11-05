from app.services.wordbook_queue import SCHEDULER_QUEUE_NAME, WORDBOOK_QUEUE_NAME
from app.workers.scheduler import (
    SchedulerSettings,
    challenge_schedule_tick,
    practice_pool_tick,
    scheduler_tick,
)
from app.workers.worker import (
    WorkerSettings,
    replenish_practice_pool,
    worker_heartbeat,
)


async def test_worker_and_scheduler_entries_are_runnable() -> None:
    heartbeat = await worker_heartbeat({})
    await scheduler_tick({})

    assert heartbeat == {"status": "ok"}
    assert worker_heartbeat in WorkerSettings.functions
    assert replenish_practice_pool in WorkerSettings.functions
    assert scheduler_tick in SchedulerSettings.functions
    cron_functions = {job.coroutine for job in SchedulerSettings.cron_jobs}
    assert scheduler_tick in cron_functions
    assert practice_pool_tick in cron_functions
    assert challenge_schedule_tick in cron_functions


def test_scheduler_and_business_worker_use_separate_queues() -> None:
    assert WorkerSettings.queue_name == WORDBOOK_QUEUE_NAME
    assert SchedulerSettings.queue_name == SCHEDULER_QUEUE_NAME
    assert WORDBOOK_QUEUE_NAME != SCHEDULER_QUEUE_NAME
    assert WorkerSettings.functions != SchedulerSettings.functions
