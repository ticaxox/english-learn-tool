from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from uuid import UUID

from arq.connections import ArqRedis
from arq.constants import (
    in_progress_key_prefix,
    job_key_prefix,
    result_key_prefix,
    retry_key_prefix,
)
from arq.jobs import Job, JobResult, JobStatus
from arq.worker import JobExecutionFailed

WORDBOOK_QUEUE_NAME = "english-learn:wordbooks"
SCHEDULER_QUEUE_NAME = "english-learn:scheduler"


class QueueDispatchKind(StrEnum):
    ENQUEUED = "enqueued"
    ACTIVE = "active"
    STALE = "stale"
    TERMINAL_SUCCESS = "terminal_success"
    TERMINAL_FAILURE = "terminal_failure"
    NOT_FOUND = "not_found"


@dataclass(frozen=True)
class WordbookQueueDispatch:
    kind: QueueDispatchKind
    error_code: str | None = None
    error_message: str | None = None


def arq_job_id(job_id: UUID) -> str:
    return f"wordbook:{job_id}"


def _result_dispatch(result: JobResult) -> WordbookQueueDispatch:
    if result.success:
        return WordbookQueueDispatch(QueueDispatchKind.TERMINAL_SUCCESS)
    if isinstance(result.result, JobExecutionFailed) and "not found" in str(result.result):
        return WordbookQueueDispatch(
            QueueDispatchKind.TERMINAL_FAILURE,
            error_code="WORDBOOK_WORKER_FUNCTION_MISSING",
            error_message="The background worker is not configured for wordbook jobs.",
        )
    return WordbookQueueDispatch(
        QueueDispatchKind.TERMINAL_FAILURE,
        error_code="WORDBOOK_ARQ_JOB_FAILED",
        error_message="The background worker could not execute the wordbook job.",
    )


def _is_stale(enqueue_time: datetime, stale_after_seconds: int) -> bool:
    if enqueue_time.tzinfo is None:
        enqueue_time = enqueue_time.replace(tzinfo=UTC)
    return enqueue_time <= datetime.now(UTC) - timedelta(seconds=stale_after_seconds)


async def dispatch_wordbook_job(
    pool: ArqRedis,
    job_id: UUID,
    *,
    stale_after_seconds: int,
) -> WordbookQueueDispatch:
    """Place a persisted job on the business queue or classify an existing ARQ entry."""

    queue_job_id = arq_job_id(job_id)
    created = await pool.enqueue_job(
        "process_wordbook_job",
        str(job_id),
        _job_id=queue_job_id,
        _queue_name=WORDBOOK_QUEUE_NAME,
    )
    if created is not None:
        return WordbookQueueDispatch(QueueDispatchKind.ENQUEUED)

    # A missing ARQ job can race with a terminal-result cleanup. Inspect and retry once.
    for _ in range(2):
        queue_job = Job(queue_job_id, redis=pool, _queue_name=WORDBOOK_QUEUE_NAME)
        status = await queue_job.status()
        if status in {JobStatus.queued, JobStatus.deferred, JobStatus.in_progress}:
            info = await queue_job.info()
            if info is not None and _is_stale(info.enqueue_time, stale_after_seconds):
                return WordbookQueueDispatch(QueueDispatchKind.STALE)
            return WordbookQueueDispatch(QueueDispatchKind.ACTIVE)
        if status is JobStatus.complete:
            result = await queue_job.result_info()
            if result is None:
                return WordbookQueueDispatch(
                    QueueDispatchKind.TERMINAL_FAILURE,
                    error_code="WORDBOOK_ARQ_RESULT_MISSING",
                    error_message="The background worker result is unavailable.",
                )
            return _result_dispatch(result)

        created = await pool.enqueue_job(
            "process_wordbook_job",
            str(job_id),
            _job_id=queue_job_id,
            _queue_name=WORDBOOK_QUEUE_NAME,
        )
        if created is not None:
            return WordbookQueueDispatch(QueueDispatchKind.ENQUEUED)

    return WordbookQueueDispatch(QueueDispatchKind.NOT_FOUND)


async def clear_wordbook_queue_entry(pool: ArqRedis, job_id: UUID) -> None:
    """Remove an exhausted or stale ARQ entry before placing the durable job again."""

    queue_job_id = arq_job_id(job_id)
    async with pool.pipeline(transaction=True) as pipeline:
        await pipeline.delete(
            f"{job_key_prefix}{queue_job_id}",
            f"{result_key_prefix}{queue_job_id}",
            f"{in_progress_key_prefix}{queue_job_id}",
            f"{retry_key_prefix}{queue_job_id}",
        )
        await pipeline.zrem(WORDBOOK_QUEUE_NAME, queue_job_id)
        await pipeline.execute()


async def force_requeue_wordbook_job(
    pool: ArqRedis,
    job_id: UUID,
    *,
    stale_after_seconds: int,
) -> WordbookQueueDispatch:
    await clear_wordbook_queue_entry(pool, job_id)
    return await dispatch_wordbook_job(
        pool,
        job_id,
        stale_after_seconds=stale_after_seconds,
    )
