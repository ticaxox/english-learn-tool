from app.workers.scheduler import SchedulerSettings, scheduler_tick
from app.workers.worker import WorkerSettings, worker_heartbeat


async def test_worker_and_scheduler_entries_are_runnable() -> None:
    heartbeat = await worker_heartbeat({})
    await scheduler_tick({})

    assert heartbeat == {"status": "ok"}
    assert worker_heartbeat in WorkerSettings.functions
    assert scheduler_tick in SchedulerSettings.functions
    assert len(SchedulerSettings.cron_jobs) == 1
