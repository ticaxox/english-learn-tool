from __future__ import annotations

import pytest

from app.services.ai_jobs import process_ai_job
from app.services.ai_security import ProviderRequestError, validate_provider_url
from tests.ai_support import (
    JOBS_PATH,
    USAGE_PATH,
    create_provider,
    fake_provider_server,
    login,
    practice_context,
    practice_output,
)


def job_payload(context: dict, task_type: str = "practice_generation") -> dict:
    return {"task_type": task_type, "context": context}


async def _create_job(client, headers, context, key: str):
    return await client.post(
        JOBS_PATH,
        headers={**headers, "Idempotency-Key": key},
        json=job_payload(context),
    )


async def _run_job(app, job_id: str) -> dict:
    return await process_ai_job(
        {
            "session_factory": app.state.session_factory,
            "settings": app.state.settings,
            "redis": app.state.redis,
        },
        job_id,
    )


async def test_ai_job_idempotency_quota_concurrency_and_cancel(
    client, app, admin_user, member_user
):
    headers = await login(client, admin_user.username)
    member_headers = await login(client, member_user.username)
    context, entry_ids = practice_context()
    with fake_provider_server() as server:
        await create_provider(client, headers, base_url=server.base_url)

        first = await _create_job(client, member_headers, context, "job-key-1")
        assert first.status_code == 202, first.text
        first_body = first.json()
        assert first_body["status"] == "queued"
        assert first_body["replayed"] is False

        replay = await _create_job(client, member_headers, context, "job-key-1")
        assert replay.status_code == 202
        assert replay.json()["job_id"] == first_body["job_id"]
        assert replay.json()["replayed"] is True

        conflict_context, _ = practice_context()
        conflict = await _create_job(client, member_headers, conflict_context, "job-key-1")
        assert conflict.status_code == 409
        assert conflict.json()["code"] == "AI_IDEMPOTENCY_CONFLICT"

        second = await _create_job(client, member_headers, context, "job-key-2")
        assert second.status_code == 202, second.text
        third = await _create_job(client, member_headers, context, "job-key-3")
        assert third.status_code == 429
        assert third.json()["code"] == "AI_CONCURRENCY_LIMIT"

        usage = await client.get(USAGE_PATH, headers=member_headers)
        assert usage.status_code == 200
        assert usage.json()["concurrency"]["in_use"] == 2
        assert usage.json()["quotas"][1]["reserved"] == 2

        cancelled = await client.post(
            f"{JOBS_PATH}/{first_body['job_id']}/cancel",
            headers=member_headers,
        )
        assert cancelled.status_code == 200, cancelled.text
        assert cancelled.json()["status"] == "cancelled"

        third_retry = await _create_job(client, member_headers, context, "job-key-3")
        assert third_retry.status_code == 202, third_retry.text

        server.queue_json(200, practice_output(entry_ids))
        result = await _run_job(app, third_retry.json()["job_id"])
        assert result["status"] == "succeeded"

        status = await client.get(
            f"{JOBS_PATH}/{third_retry.json()['job_id']}", headers=member_headers
        )
        assert status.status_code == 200
        assert status.json()["status"] == "succeeded"
        assert status.json()["result_summary"]["item_count"] == 3
        assert "result" not in status.json()

        usage = await client.get(USAGE_PATH, headers=member_headers)
        assert usage.json()["quotas"][1]["used"] == 1
        assert usage.json()["concurrency"]["in_use"] == 1


async def test_ai_job_repair_and_failure_release_quota(client, app, admin_user, member_user):
    admin_headers = await login(client, admin_user.username)
    member_headers = await login(client, member_user.username)
    context, entry_ids = practice_context()
    with fake_provider_server() as server:
        await create_provider(client, admin_headers, base_url=server.base_url, name="Repair")

        repair_job = await _create_job(client, member_headers, context, "repair-key")
        assert repair_job.status_code == 202, repair_job.text
        server.queue_json(200, {"choices": [{"message": {"content": "not-json"}}]})
        server.queue_json(200, practice_output(entry_ids))
        result = await _run_job(app, repair_job.json()["job_id"])
        assert result["status"] == "succeeded"
        status = await client.get(
            f"{JOBS_PATH}/{repair_job.json()['job_id']}", headers=member_headers
        )
        assert status.json()["repair_count"] == 1

        failure_context, _ = practice_context()
        failure_job = await _create_job(client, member_headers, failure_context, "failure-key")
        assert failure_job.status_code == 202, failure_job.text
        for _ in range(3):
            server.queue_json(500, {"error": "temporary"})
        result = await _run_job(app, failure_job.json()["job_id"])
        assert result["status"] == "failed"
        status = await client.get(
            f"{JOBS_PATH}/{failure_job.json()['job_id']}", headers=member_headers
        )
        assert status.json()["status"] == "failed"
        assert status.json()["error"]["code"] == "AI_PROVIDER_UNAVAILABLE"
        assert status.json()["error"]["retryable"] is True

        usage = await client.get(USAGE_PATH, headers=member_headers)
        question_usage = next(
            item for item in usage.json()["quotas"] if item["quota_kind"] == "question_generation"
        )
        assert question_usage["used"] == 1
        assert question_usage["reserved"] == 0
        assert question_usage["remaining"] == 19


async def test_ai_job_fails_over_to_backup_provider(client, app, admin_user, member_user):
    admin_headers = await login(client, admin_user.username)
    member_headers = await login(client, member_user.username)
    context, entry_ids = practice_context()
    with fake_provider_server() as primary, fake_provider_server() as backup:
        await create_provider(
            client,
            admin_headers,
            base_url=primary.base_url,
            name="Primary failing",
            is_default=True,
            priority=1,
        )
        await create_provider(
            client,
            admin_headers,
            base_url=backup.base_url,
            name="Backup working",
            is_default=False,
            priority=2,
        )
        for _ in range(3):
            primary.queue_json(500, {"error": "temporary"})
        backup.queue_json(200, practice_output(entry_ids))

        job = await _create_job(client, member_headers, context, "failover-key")
        assert job.status_code == 202, job.text
        result = await _run_job(app, job.json()["job_id"])
        assert result["status"] == "succeeded"
        status = await client.get(f"{JOBS_PATH}/{job.json()['job_id']}", headers=member_headers)
        assert status.json()["provider_name"] == "Backup working"
        assert status.json()["attempt_count"] == 1


@pytest.mark.asyncio
async def test_provider_url_blocks_metadata_and_private_targets_by_default() -> None:
    from app.core.config import Settings

    settings = Settings(ai_allow_private_provider_urls=False)
    with pytest.raises(ProviderRequestError) as metadata:
        await validate_provider_url("http://169.254.169.254/latest/meta-data", settings)
    assert metadata.value.code == "AI_PROVIDER_URL_BLOCKED"

    with pytest.raises(ProviderRequestError) as loopback:
        await validate_provider_url("http://127.0.0.1:8080/v1", settings)
    assert loopback.value.code == "AI_PROVIDER_URL_BLOCKED"
