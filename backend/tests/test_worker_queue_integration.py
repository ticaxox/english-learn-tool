from __future__ import annotations

import asyncio
import io
import pickle
import time
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import httpx
import pytest
from arq.connections import RedisSettings, create_pool
from arq.constants import job_key_prefix
from arq.worker import Worker, create_worker
from sqlalchemy import delete, func, select, update

from app.core.config import Settings
from app.core.security import hash_password
from app.main import create_app
from app.models.identity import AuditLog, User, UserProfile
from app.models.wordbooks import Wordbook, WordbookEntry, WordbookJob
from app.services.wordbook_queue import (
    SCHEDULER_QUEUE_NAME,
    WORDBOOK_QUEUE_NAME,
    arq_job_id,
    clear_wordbook_queue_entry,
)
from app.workers.common import get_redis_settings
from app.workers.scheduler import SchedulerSettings
from app.workers.worker import WorkerSettings, worker_heartbeat

LOGIN_PATH = "/api/v1/auth/login"
WORDBOOKS_PATH = "/api/v1/wordbooks"
PASSWORD = "Queue-Integration-Pass-123!"


async def _shutdown_burst_worker(worker: Worker) -> None:
    if worker._pool is None:
        return
    if worker.on_shutdown is not None:
        await worker.on_shutdown(worker.ctx)
    await worker.pool.aclose()


async def _run_burst(worker: Worker) -> None:
    try:
        await worker.async_run()
    finally:
        await _shutdown_burst_worker(worker)


async def _enqueue_scheduler_tick(settings: Settings) -> None:
    pool = await create_pool(
        RedisSettings.from_dsn(settings.redis_url),
        default_queue_name=SCHEDULER_QUEUE_NAME,
    )
    try:
        await pool.enqueue_job(
            "scheduler_tick",
            _job_id=f"test-scheduler:{uuid4().hex}",
            _queue_name=SCHEDULER_QUEUE_NAME,
        )
    finally:
        await pool.aclose()


def _csv_bytes(headword: str = "harbor") -> bytes:
    return (
        "headword,phonetic,part_of_speech,definition_en,definition_zh,example,example_translation\n"
        f"{headword},hahr-ber,n.,a place where ships stop,港口,"
        "The ship entered the harbor.,船驶入港口。\n"
    ).encode()


async def _create_private_preview(
    client: httpx.AsyncClient,
    headers: dict[str, str],
    *,
    name: str,
    headword: str,
) -> dict:
    response = await client.post(
        f"{WORDBOOKS_PATH}/import/preview",
        headers=headers,
        data={"visibility": "private", "name": name},
        files={"file": ("queue.csv", io.BytesIO(_csv_bytes(headword)), "text/csv")},
    )
    assert response.status_code == 201, response.text
    return response.json()


def _confirm_payload(preview: dict) -> dict[str, object]:
    return {
        "preview_id": preview["preview_id"],
        "preview_token": preview["preview_token"],
        "preview_hash": preview["preview_hash"],
        "name": preview["requested_name"],
        "visibility": "private",
    }


async def _make_arq_entry_stale(redis, job_id: str) -> None:
    queue_job_id = arq_job_id(UUID(job_id))
    key = f"{job_key_prefix}{queue_job_id}"
    serialized = await redis.get(key)
    assert serialized is not None
    deserialize = redis.job_deserializer or pickle.loads
    serialize = redis.job_serializer or pickle.dumps
    definition = deserialize(serialized)
    definition["et"] = int(time.time() * 1000) - 3_600_000
    await redis.set(key, serialize(definition), keepttl=True)
    await redis.zrem(WORDBOOK_QUEUE_NAME, queue_job_id)
    await redis.zadd(WORDBOOK_QUEUE_NAME, {queue_job_id: 1})


async def _process_with_business_worker() -> None:
    worker = create_worker(
        WorkerSettings,
        burst=True,
        handle_signals=False,
        poll_delay=0.01,
    )
    await _run_burst(worker)


@pytest.mark.asyncio
async def test_split_scheduler_and_business_queues_recover_all_nonterminal_states() -> None:
    integration_app = create_app(Settings())
    user_id = None
    workers: list[Worker] = []
    async with integration_app.router.lifespan_context(integration_app):
        settings = integration_app.state.settings
        username = f"queue_integration_{uuid4().hex[:12]}"
        try:
            async with integration_app.state.session_factory() as session:
                user = User(
                    username=username,
                    username_normalized=username.lower(),
                    display_name="Queue Integration Admin",
                    role="admin",
                    status="active",
                    password_hash=hash_password(PASSWORD),
                    must_change_password=False,
                    profile=UserProfile(department="Engineering", learning_group="Core"),
                )
                session.add(user)
                await session.commit()
                user_id = user.id

            transport = httpx.ASGITransport(app=integration_app)
            async with httpx.AsyncClient(
                transport=transport, base_url="http://testserver"
            ) as client:
                login = await client.post(
                    LOGIN_PATH,
                    json={"username": username, "password": PASSWORD},
                )
                assert login.status_code == 200, login.text
                headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

                preview = await _create_private_preview(
                    client,
                    headers,
                    name="Queue recovery book",
                    headword="harbor",
                )
                payload = _confirm_payload(preview)
                first_key = f"queue-import:{uuid4().hex}"
                redis_pool = integration_app.state.arq
                integration_app.state.arq = None
                try:
                    unavailable_response = await client.post(
                        f"{WORDBOOKS_PATH}/import",
                        headers={**headers, "Idempotency-Key": first_key},
                        json=payload,
                    )
                finally:
                    integration_app.state.arq = redis_pool
                assert unavailable_response.status_code == 503, unavailable_response.text
                assert unavailable_response.json()["code"] == "WORDBOOK_QUEUE_UNAVAILABLE"

                async with integration_app.state.session_factory() as session:
                    failed_job = await session.scalar(
                        select(WordbookJob).where(
                            WordbookJob.owner_id == user_id,
                            WordbookJob.idempotency_key == first_key,
                        )
                    )
                    initial_queue_audits = await session.scalar(
                        select(func.count(AuditLog.id)).where(
                            AuditLog.actor_id == user_id,
                            AuditLog.action == "wordbook.import.queue_failed",
                        )
                    )
                assert failed_job is not None
                assert failed_job.status == "queued"
                assert failed_job.attempts == 1
                assert failed_job.error_code == "WORDBOOK_QUEUE_UNAVAILABLE"
                assert initial_queue_audits == 1
                assert await integration_app.state.redis.zcard(WORDBOOK_QUEUE_NAME) == 0

                retry_response = await client.post(
                    f"{WORDBOOKS_PATH}/import",
                    headers={**headers, "Idempotency-Key": first_key},
                    json=payload,
                )
                assert retry_response.status_code == 202, retry_response.text
                first_job_id = retry_response.json()["job_id"]
                assert UUID(first_job_id) == failed_job.id
                assert await integration_app.state.redis.zcard(WORDBOOK_QUEUE_NAME) == 1

            bad_worker = Worker(
                [worker_heartbeat],
                queue_name=WORDBOOK_QUEUE_NAME,
                redis_settings=get_redis_settings(),
                burst=True,
                handle_signals=False,
                keep_result=60,
                poll_delay=0.01,
            )
            workers.append(bad_worker)
            await _run_burst(bad_worker)

            async with integration_app.state.session_factory() as session:
                terminal_job = await session.get(WordbookJob, UUID(first_job_id))
            assert terminal_job is not None
            assert terminal_job.status == "queued"
            assert terminal_job.attempts == 1
            assert await integration_app.state.redis.zcard(WORDBOOK_QUEUE_NAME) == 0

            await _enqueue_scheduler_tick(settings)
            scheduler_recovery = create_worker(
                SchedulerSettings,
                burst=True,
                handle_signals=False,
                poll_delay=0.01,
            )
            workers.append(scheduler_recovery)
            await _run_burst(scheduler_recovery)

            async with integration_app.state.session_factory() as session:
                recovered_job = await session.get(WordbookJob, UUID(first_job_id))
            assert recovered_job is not None
            assert recovered_job.status == "queued"
            assert recovered_job.attempts == 2
            assert recovered_job.error_code == "WORDBOOK_WORKER_FUNCTION_MISSING"
            assert await integration_app.state.redis.zcard(WORDBOOK_QUEUE_NAME) == 1

            await _enqueue_scheduler_tick(settings)
            business_worker = create_worker(
                WorkerSettings,
                burst=True,
                handle_signals=False,
                poll_delay=0.01,
            )
            scheduler_worker = create_worker(
                SchedulerSettings,
                burst=True,
                handle_signals=False,
                poll_delay=0.01,
            )
            workers.extend((business_worker, scheduler_worker))
            await asyncio.gather(
                _run_burst(business_worker),
                _run_burst(scheduler_worker),
            )

            async with integration_app.state.session_factory() as session:
                completed_job = await session.get(WordbookJob, UUID(first_job_id))
                assert completed_job is not None
                book = await session.get(Wordbook, completed_job.wordbook_id)
                entry_count = await session.scalar(
                    select(func.count(WordbookEntry.id)).where(
                        WordbookEntry.wordbook_id == completed_job.wordbook_id
                    )
                )
                queue_failure_audit_count = await session.scalar(
                    select(func.count(AuditLog.id)).where(
                        AuditLog.actor_id == user_id,
                        AuditLog.action == "wordbook.import.queue_failed",
                    )
                )
            assert completed_job.status == "succeeded"
            assert completed_job.attempts == 3
            assert completed_job.error_code is None
            assert book is not None and book.status == "ready"
            assert entry_count == 1
            assert queue_failure_audit_count == 2
            assert await integration_app.state.redis.zcard(WORDBOOK_QUEUE_NAME) == 0
            assert await integration_app.state.redis.zcard(SCHEDULER_QUEUE_NAME) == 0

            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=integration_app),
                base_url="http://testserver",
            ) as client:
                login = await client.post(
                    LOGIN_PATH,
                    json={"username": username, "password": PASSWORD},
                )
                headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
                replay = await client.post(
                    f"{WORDBOOKS_PATH}/import",
                    headers={**headers, "Idempotency-Key": first_key},
                    json=payload,
                )
                assert replay.status_code == 202, replay.text
                assert replay.json()["job_id"] == first_job_id

                async with integration_app.state.session_factory() as session:
                    replayed_job = await session.get(WordbookJob, UUID(first_job_id))
                assert replayed_job is not None
                assert replayed_job.status == "succeeded"
                assert replayed_job.attempts == 3
                assert await integration_app.state.redis.zcard(WORDBOOK_QUEUE_NAME) == 0

                stale_preview = await _create_private_preview(
                    client,
                    headers,
                    name="Stale ARQ queue book",
                    headword="anchor",
                )
                stale_payload = _confirm_payload(stale_preview)
                stale_key = f"queue-stale:{uuid4().hex}"
                stale_confirm = await client.post(
                    f"{WORDBOOKS_PATH}/import",
                    headers={**headers, "Idempotency-Key": stale_key},
                    json=stale_payload,
                )
                assert stale_confirm.status_code == 202, stale_confirm.text
                stale_job_id = stale_confirm.json()["job_id"]
                await _make_arq_entry_stale(integration_app.state.arq, stale_job_id)

                await _enqueue_scheduler_tick(settings)
                stale_scheduler = create_worker(
                    SchedulerSettings,
                    burst=True,
                    handle_signals=False,
                    poll_delay=0.01,
                )
                workers.append(stale_scheduler)
                await _run_burst(stale_scheduler)

                async with integration_app.state.session_factory() as session:
                    stale_job = await session.get(WordbookJob, UUID(stale_job_id))
                assert stale_job is not None
                assert stale_job.status == "queued"
                assert stale_job.attempts == 1
                assert stale_job.error_code == "WORDBOOK_QUEUE_ENTRY_STALE"
                assert await integration_app.state.redis.zcard(WORDBOOK_QUEUE_NAME) == 1

                await _process_with_business_worker()

                async with integration_app.state.session_factory() as session:
                    stale_job = await session.get(WordbookJob, UUID(stale_job_id))
                    assert stale_job is not None
                    stale_entry_count = await session.scalar(
                        select(func.count(WordbookEntry.id)).where(
                            WordbookEntry.wordbook_id == stale_job.wordbook_id
                        )
                    )
                assert stale_job.status == "succeeded"
                assert stale_job.attempts == 2
                assert stale_entry_count == 1
                assert await integration_app.state.redis.zcard(WORDBOOK_QUEUE_NAME) == 0

                await _enqueue_scheduler_tick(settings)
                post_success_scheduler = create_worker(
                    SchedulerSettings,
                    burst=True,
                    handle_signals=False,
                    poll_delay=0.01,
                )
                workers.append(post_success_scheduler)
                await _run_burst(post_success_scheduler)
                async with integration_app.state.session_factory() as session:
                    stale_job = await session.get(WordbookJob, UUID(stale_job_id))
                assert stale_job is not None
                assert stale_job.attempts == 2
                assert await integration_app.state.redis.zcard(WORDBOOK_QUEUE_NAME) == 0

                interrupted_preview = await _create_private_preview(
                    client,
                    headers,
                    name="Interrupted worker book",
                    headword="buoy",
                )
                interrupted_payload = _confirm_payload(interrupted_preview)
                interrupted_key = f"queue-interrupted:{uuid4().hex}"
                interrupted_confirm = await client.post(
                    f"{WORDBOOKS_PATH}/import",
                    headers={**headers, "Idempotency-Key": interrupted_key},
                    json=interrupted_payload,
                )
                assert interrupted_confirm.status_code == 202, interrupted_confirm.text
                interrupted_job_id = interrupted_confirm.json()["job_id"]
                old_timestamp = datetime.now(UTC) - timedelta(
                    seconds=settings.wordbook_job_stale_seconds + 60
                )
                async with integration_app.state.session_factory() as session:
                    await session.execute(
                        update(WordbookJob)
                        .where(WordbookJob.id == UUID(interrupted_job_id))
                        .values(
                            status="running",
                            attempts=1,
                            started_at=old_timestamp,
                            updated_at=old_timestamp,
                        )
                    )
                    await session.commit()
                await clear_wordbook_queue_entry(
                    integration_app.state.redis,
                    UUID(interrupted_job_id),
                )

                await _enqueue_scheduler_tick(settings)
                interrupted_scheduler = create_worker(
                    SchedulerSettings,
                    burst=True,
                    handle_signals=False,
                    poll_delay=0.01,
                )
                workers.append(interrupted_scheduler)
                await _run_burst(interrupted_scheduler)

                async with integration_app.state.session_factory() as session:
                    interrupted_job = await session.get(
                        WordbookJob,
                        UUID(interrupted_job_id),
                    )
                    interrupted_audits = await session.scalar(
                        select(func.count(AuditLog.id)).where(
                            AuditLog.actor_id == user_id,
                            AuditLog.action == "wordbook.import.queue_failed",
                            AuditLog.reason_code == "WORDBOOK_WORKER_INTERRUPTED",
                        )
                    )
                assert interrupted_job is not None
                assert interrupted_job.status == "queued"
                assert interrupted_job.attempts == 1
                assert interrupted_job.error_code == "WORDBOOK_WORKER_INTERRUPTED"
                assert interrupted_audits == 1
                assert await integration_app.state.redis.zcard(WORDBOOK_QUEUE_NAME) == 1

                await _process_with_business_worker()

                async with integration_app.state.session_factory() as session:
                    interrupted_job = await session.get(
                        WordbookJob,
                        UUID(interrupted_job_id),
                    )
                    assert interrupted_job is not None
                    interrupted_entry_count = await session.scalar(
                        select(func.count(WordbookEntry.id)).where(
                            WordbookEntry.wordbook_id == interrupted_job.wordbook_id
                        )
                    )
                assert interrupted_job.status == "succeeded"
                assert interrupted_job.attempts == 2
                assert interrupted_entry_count == 1
                assert await integration_app.state.redis.zcard(WORDBOOK_QUEUE_NAME) == 0
                assert await integration_app.state.redis.zcard(SCHEDULER_QUEUE_NAME) == 0
        finally:
            for worker in workers:
                await _shutdown_burst_worker(worker)
            if user_id is not None:
                async with integration_app.state.session_factory() as session:
                    await session.execute(delete(AuditLog).where(AuditLog.actor_id == user_id))
                    await session.execute(delete(User).where(User.id == user_id))
                    await session.commit()
