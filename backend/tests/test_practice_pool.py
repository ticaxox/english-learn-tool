from __future__ import annotations

from uuid import UUID

from sqlalchemy import select

from app.models.ai import AiJob
from app.models.identity import User
from app.models.practice import PracticePoolItem, PracticeSession
from app.services.ai_jobs import process_ai_job
from app.services.practice_pool import ensure_pool
from tests.ai_support import (
    create_provider,
    fake_provider_server,
    login,
    practice_output,
)
from tests.learning_support import PROFILE_PATH, activate, seed_wordbook

PRACTICE_PATH = "/api/v1/practice"


async def _run_job(app, job_id: UUID) -> dict:
    return await process_ai_job(
        {
            "session_factory": app.state.session_factory,
            "settings": app.state.settings,
            "redis": app.state.redis,
        },
        str(job_id),
    )


async def test_ready_pool_set_is_claimed_and_replenished(app, client, member_user) -> None:
    headers = await login(client, member_user.username)
    wordbook_id = await seed_wordbook(app, owner_id=member_user.id, entries=8)
    await activate(app, user_id=member_user.id, wordbook_id=wordbook_id)
    profile = await client.patch(
        PROFILE_PATH,
        headers=headers,
        json={"practice_pool_targets": {"fill_blank": {"3": 1}}},
    )
    assert profile.status_code == 200, profile.text
    assert profile.json()["practice_pool_targets"] == {"fill_blank": {"3": 1}}

    with fake_provider_server() as server:
        await create_provider(client, headers, base_url=server.base_url)
        async with app.state.session_factory() as session:
            user = await session.get(User, member_user.id)
            assert user is not None
            counts = await ensure_pool(session, app.state.arq, user, app.state.settings)
        assert counts["created"] == 1

        async with app.state.session_factory() as session:
            item = await session.scalar(
                select(PracticePoolItem).where(PracticePoolItem.user_id == member_user.id)
            )
            assert item is not None
            pool_session = await session.get(PracticeSession, item.session_id)
            assert pool_session is not None
            assert pool_session.is_pool is True
            job_id = pool_session.ai_job_id
            assert job_id is not None
            job = await session.get(AiJob, job_id)
            entry_ids = job.input_context["target_entry_ids"]

        import json

        from app.services.ai_validation import validate_task_output

        payload = practice_output(entry_ids[:3])
        validate_task_output(
            task_type="practice_generation",
            context=job.input_context,
            raw_text=json.dumps(payload),
        )
        server.queue_json(200, payload)
        result = await _run_job(app, job_id)
        assert result["status"] == "succeeded", result

        created = await client.post(
            f"{PRACTICE_PATH}/sessions",
            headers={**headers, "Idempotency-Key": "pool-claim-1"},
            json={"practice_type": "fill_blank", "source": "whole_book", "count": 3},
        )
        assert created.status_code == 202, created.text
        assert created.json()["id"] == str(item.session_id)
        assert created.json()["status"] == "ready"

        async with app.state.session_factory() as session:
            remaining = await session.scalars(
                select(PracticePoolItem).where(PracticePoolItem.user_id == member_user.id)
            )
            assert list(remaining) == []
            claimed = await session.get(PracticeSession, item.session_id)
            assert claimed is not None
            assert claimed.is_pool is False
            assert claimed.idempotency_key == "pool-claim-1"


async def test_failed_pool_generation_is_retried(app, client, member_user) -> None:
    headers = await login(client, member_user.username)
    wordbook_id = await seed_wordbook(app, owner_id=member_user.id, entries=8)
    await activate(app, user_id=member_user.id, wordbook_id=wordbook_id)
    await client.patch(
        PROFILE_PATH,
        headers=headers,
        json={"practice_pool_targets": {"fill_blank": {"3": 1}}},
    )

    with fake_provider_server() as server:
        await create_provider(client, headers, base_url=server.base_url)
        async with app.state.session_factory() as session:
            user = await session.get(User, member_user.id)
            await ensure_pool(session, app.state.arq, user, app.state.settings)
        async with app.state.session_factory() as session:
            item = await session.scalar(
                select(PracticePoolItem).where(PracticePoolItem.user_id == member_user.id)
            )
            assert item is not None
            pool_session = await session.get(PracticeSession, item.session_id)
            assert pool_session and pool_session.ai_job_id
            failed_job_id = pool_session.ai_job_id

        server.queue_json(500, {"error": "provider failed"})
        result = await _run_job(app, failed_job_id)
        assert result["status"] == "failed"
        async with app.state.session_factory() as session:
            failed_session = await session.get(PracticeSession, item.session_id)
            assert failed_session is not None
            assert failed_session.status == "failed"

        async with app.state.session_factory() as session:
            user = await session.get(User, member_user.id)
            counts = await ensure_pool(session, app.state.arq, user, app.state.settings)
        assert counts["retried"] == 1

        async with app.state.session_factory() as session:
            refreshed = await session.get(PracticePoolItem, item.id)
            assert refreshed is not None
            assert refreshed.attempts == 2
            retried_session = await session.get(PracticeSession, item.session_id)
            assert retried_session is not None
            assert retried_session.status == "generating"
            retry_job_id = retried_session.ai_job_id
            job = await session.get(AiJob, retry_job_id)
            entry_ids = job.input_context["target_entry_ids"]

        server.queue_json(200, practice_output(entry_ids[:3]))
        assert (await _run_job(app, retry_job_id))["status"] == "succeeded"
