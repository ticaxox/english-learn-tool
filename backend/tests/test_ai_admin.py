from __future__ import annotations

from datetime import UTC, date, datetime
from uuid import uuid4

from sqlalchemy import select

from app.models.ai import AiJob, AiPrompt, AiProvider, AiUsageLedger
from app.models.identity import AuditLog
from app.services import ai_usage as ai_usage_service
from tests.ai_support import (
    ADMIN_PROVIDERS_PATH,
    PROMPTS_PATH,
    PROVIDERS_PATH,
    create_provider,
    fake_provider_server,
    login,
)


async def _seed_usage_job(app, user_id, *, created_at: datetime, local_date: date) -> None:
    key = f"admin-usage-{uuid4()}"
    async with app.state.session_factory() as session:
        job = AiJob(
            user_id=user_id,
            task_type="coach_reply",
            status="succeeded",
            quota_kind="coach_messages",
            provider_name="Usage Provider",
            model_id="usage-model",
            prompt_key="coach_reply",
            prompt_snapshot="safe prompt",
            input_context={},
            idempotency_key=key,
            request_hash="a" * 64,
            created_at=created_at,
        )
        session.add(job)
        await session.flush()
        session.add(
            AiUsageLedger(
                user_id=user_id,
                job_id=job.id,
                local_date=local_date,
                quota_kind="coach_messages",
                quota_item="job",
                reserved=0,
                consumed=1,
                released=0,
                status="consumed",
            )
        )
        await session.commit()


async def test_personal_provider_crud_masks_keys_and_checks_real_http(
    client, app, member_user, caplog
) -> None:
    headers = await login(client, member_user.username)
    forbidden = await client.get(ADMIN_PROVIDERS_PATH, headers=headers)
    assert forbidden.status_code == 403
    assert forbidden.json()["code"] == "FORBIDDEN"
    with fake_provider_server() as server:
        primary = await create_provider(client, headers, base_url=server.base_url)
        assert primary["api_key_masked"] == "sk-****1234"
        assert "sk-test-secret-1234" not in str(primary)

        async with app.state.session_factory() as session:
            stored = await session.scalar(select(AiProvider).where(AiProvider.id == primary["id"]))
            assert stored is not None
            assert stored.api_key_ciphertext != "sk-test-secret-1234"
            assert "sk-test-secret-1234" not in stored.api_key_ciphertext

        listed = await client.get(PROVIDERS_PATH, headers=headers)
        assert listed.status_code == 200
        assert listed.json()["items"][0]["api_key_masked"] == "sk-****1234"
        assert "sk-test-secret-1234" not in listed.text

        detail = await client.get(f"{PROVIDERS_PATH}/{primary['id']}", headers=headers)
        assert detail.status_code == 200
        assert detail.json()["api_key_masked"] == "sk-****1234"

        revealed = await client.get(f"{PROVIDERS_PATH}/{primary['id']}/api-key", headers=headers)
        assert revealed.status_code == 404
        assert "sk-test-secret-1234" not in revealed.text

        key_preserved = await client.patch(
            f"{PROVIDERS_PATH}/{primary['id']}",
            headers=headers,
            json={"api_key": ""},
        )
        assert key_preserved.status_code == 200, key_preserved.text
        assert key_preserved.json()["api_key_masked"] == "sk-****1234"

        short_key = await client.patch(
            f"{PROVIDERS_PATH}/{primary['id']}",
            headers=headers,
            json={"api_key": "short"},
        )
        assert short_key.status_code == 422

        tested = await client.post(f"{PROVIDERS_PATH}/{primary['id']}/test", headers=headers)
        assert tested.status_code == 200
        assert tested.json()["success"] is True
        assert tested.json()["models"] == ["fake-model", "fake-model-2"]

        models = await client.post(f"{PROVIDERS_PATH}/{primary['id']}/models", headers=headers)
        assert models.status_code == 200
        assert models.json()["success"] is True
        assert models.json()["models"] == ["fake-model", "fake-model-2"]

        # The create dialog can probe before saving, using the typed key only.
        drafted = await client.post(
            f"{PROVIDERS_PATH}/probe",
            headers=headers,
            json={
                "base_url": server.base_url,
                "api_key": "sk-draft-secret-5555",
                "timeout_seconds": 10,
                "custom_headers": {},
            },
        )
        assert drafted.status_code == 200, drafted.text
        assert drafted.json()["success"] is True
        assert drafted.json()["models"] == ["fake-model", "fake-model-2"]
        assert "sk-draft-secret-5555" not in drafted.text

        drafted_models = await client.post(
            f"{PROVIDERS_PATH}/probe/models",
            headers=headers,
            json={
                "base_url": server.base_url,
                "api_key": "sk-draft-secret-5555",
                "timeout_seconds": 10,
                "custom_headers": {},
            },
        )
        assert drafted_models.status_code == 200, drafted_models.text
        assert drafted_models.json()["models"] == ["fake-model", "fake-model-2"]

        missing_key = await client.post(
            f"{PROVIDERS_PATH}/probe",
            headers=headers,
            json={"base_url": server.base_url, "timeout_seconds": 10, "custom_headers": {}},
        )
        assert missing_key.status_code == 422
        assert missing_key.json()["code"] == "AI_PROVIDER_API_KEY_REQUIRED"

        # An existing provider can be probed with its stored key and a new URL.
        stored_probe = await client.post(
            f"{PROVIDERS_PATH}/probe",
            headers=headers,
            json={
                "base_url": server.base_url,
                "provider_id": primary["id"],
                "timeout_seconds": 10,
                "custom_headers": {},
            },
        )
        assert stored_probe.status_code == 200, stored_probe.text
        assert stored_probe.json()["success"] is True

        backup = await create_provider(
            client,
            headers,
            base_url=server.base_url,
            name="Backup",
            priority=20,
            is_default=False,
            api_key="sk-backup-secret-9876",
        )
        assert backup["is_default"] is False
        promoted = await client.patch(
            f"{PROVIDERS_PATH}/{backup['id']}",
            headers=headers,
            json={"is_default": True},
        )
        assert promoted.status_code == 200, promoted.text
        assert promoted.json()["is_default"] is True

        listed = await client.get(PROVIDERS_PATH, headers=headers)
        assert sum(item["is_default"] for item in listed.json()["items"]) == 1

        disabled = await client.patch(
            f"{PROVIDERS_PATH}/{backup['id']}",
            headers=headers,
            json={"enabled": False},
        )
        assert disabled.status_code == 200, disabled.text
        assert disabled.json()["is_default"] is False
        listed = await client.get(PROVIDERS_PATH, headers=headers)
        assert (
            next(item for item in listed.json()["items"] if item["id"] == primary["id"])[
                "is_default"
            ]
            is True
        )

        restored_default = await client.patch(
            f"{PROVIDERS_PATH}/{backup['id']}",
            headers=headers,
            json={"enabled": True, "is_default": True},
        )
        assert restored_default.status_code == 200, restored_default.text
        assert restored_default.json()["is_default"] is True

        deleted = await client.delete(f"{PROVIDERS_PATH}/{backup['id']}", headers=headers)
        assert deleted.status_code == 204
        listed = await client.get(PROVIDERS_PATH, headers=headers)
        assert listed.json()["items"][0]["id"] == primary["id"]
        assert listed.json()["items"][0]["is_default"] is True

    async with app.state.session_factory() as session:
        audit_rows = list((await session.scalars(select(AuditLog))).all())
    actions = {row.action for row in audit_rows}
    assert "ai.provider.created" in actions
    assert "ai.provider.tested" in actions
    assert "ai.provider.updated" in actions
    assert "ai.provider.deleted" in actions
    assert "sk-test-secret-1234" not in str([row.context for row in audit_rows])
    assert "sk-test-secret-1234" not in caplog.text


async def test_personal_provider_ownership_is_isolated(
    client, app, admin_user, member_user, user_factory
) -> None:
    owner_headers = await login(client, member_user.username)
    other_user = await user_factory(role="member")
    other_headers = await login(client, other_user.username)
    admin_headers = await login(client, admin_user.username)

    with fake_provider_server() as server:
        owner_provider = await create_provider(
            client, owner_headers, base_url=server.base_url, name="Primary"
        )
        duplicate = await client.post(
            PROVIDERS_PATH,
            headers=owner_headers,
            json={
                "name": "primary",
                "base_url": server.base_url,
                "api_key": "sk-test-secret-1234",
                "model_id": "fake-model",
            },
        )
        assert duplicate.status_code == 409
        assert duplicate.json()["code"] == "AI_PROVIDER_NAME_TAKEN"

        other_provider = await create_provider(
            client,
            other_headers,
            base_url=server.base_url,
            name="Primary",
            is_default=False,
        )
        foreign_key = await client.get(
            f"{PROVIDERS_PATH}/{owner_provider['id']}/api-key", headers=other_headers
        )
        assert foreign_key.status_code == 404

        assert other_provider["is_default"] is True

        owner_list = await client.get(PROVIDERS_PATH, headers=owner_headers)
        other_list = await client.get(PROVIDERS_PATH, headers=other_headers)
        admin_list = await client.get(PROVIDERS_PATH, headers=admin_headers)
        admin_legacy_list = await client.get(ADMIN_PROVIDERS_PATH, headers=admin_headers)
        assert [item["id"] for item in owner_list.json()["items"]] == [owner_provider["id"]]
        assert [item["id"] for item in other_list.json()["items"]] == [other_provider["id"]]
        assert admin_list.json()["items"] == []
        assert admin_legacy_list.json()["items"] == []

        provider_path = f"{PROVIDERS_PATH}/{owner_provider['id']}"
        admin_legacy_detail = await client.patch(
            f"{ADMIN_PROVIDERS_PATH}/{owner_provider['id']}",
            headers=admin_headers,
            json={"name": "Stolen"},
        )
        assert admin_legacy_detail.status_code == 404
        assert admin_legacy_detail.json()["code"] == "AI_PROVIDER_NOT_FOUND"
        forbidden_requests = [
            await client.get(provider_path, headers=other_headers),
            await client.get(provider_path, headers=admin_headers),
            await client.patch(provider_path, headers=other_headers, json={"name": "Stolen"}),
            await client.patch(provider_path, headers=admin_headers, json={"name": "Stolen"}),
            await client.delete(provider_path, headers=other_headers),
            await client.delete(provider_path, headers=admin_headers),
            await client.post(f"{provider_path}/test", headers=other_headers),
            await client.post(f"{provider_path}/test", headers=admin_headers),
            await client.post(f"{provider_path}/models", headers=other_headers),
            await client.post(f"{provider_path}/models", headers=admin_headers),
        ]
        for response in forbidden_requests:
            assert response.status_code == 404
            assert response.json()["code"] == "AI_PROVIDER_NOT_FOUND"
        assert server.requests == []

        owner_detail = await client.get(provider_path, headers=owner_headers)
        assert owner_detail.status_code == 200
        assert owner_detail.json()["id"] == owner_provider["id"]


async def test_ai_prompts_are_seeded_and_overwrite_affects_future_jobs(
    client, app, admin_user
) -> None:
    headers = await login(client, admin_user.username)
    listed = await client.get(PROMPTS_PATH, headers=headers)
    assert listed.status_code == 200
    assert {item["key"] for item in listed.json()["items"]} == {
        "practice_generation",
        "subjective_grading",
        "coach_reply",
        "challenge_plan",
        "json_repair",
        "conversation_turn",
    }

    detail = await client.get(f"{PROMPTS_PATH}/practice_generation", headers=headers)
    assert detail.status_code == 200
    assert detail.json()["template"]

    updated = await client.put(
        f"{PROMPTS_PATH}/practice_generation",
        headers=headers,
        json={
            "name": "Practice generator v2",
            "summary": "Updated prompt",
            "template": "Use only the supplied IDs and return strict JSON.",
        },
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["name"] == "Practice generator v2"

    async with app.state.session_factory() as session:
        prompt = await session.scalar(
            select(AiPrompt).where(AiPrompt.prompt_key == "practice_generation")
        )
        assert prompt is not None
        assert prompt.template == "Use only the supplied IDs and return strict JSON."


async def test_ai_prompt_put_cors_preflight_allows_method(client) -> None:
    response = await client.options(
        f"{PROMPTS_PATH}/practice_generation",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "PUT",
            "Access-Control-Request-Headers": "authorization,content-type",
        },
    )
    assert response.status_code == 200
    assert "PUT" in response.headers["access-control-allow-methods"]


async def test_admin_usage_uses_app_timezone_for_default_and_explicit_dates(
    client, app, admin_user, monkeypatch
) -> None:
    await _seed_usage_job(
        app,
        admin_user.id,
        created_at=datetime(2026, 10, 23, 15, 30, tzinfo=UTC),
        local_date=date(2026, 10, 23),
    )
    await _seed_usage_job(
        app,
        admin_user.id,
        created_at=datetime(2026, 10, 23, 16, 30, tzinfo=UTC),
        local_date=date(2026, 10, 24),
    )
    monkeypatch.setattr(
        ai_usage_service,
        "utcnow",
        lambda: datetime(2026, 10, 23, 17, 0, tzinfo=UTC),
    )
    headers = await login(client, admin_user.username)

    default = await client.get("/api/v1/admin/ai/usage", headers=headers)
    assert default.status_code == 200, default.text
    default_body = default.json()
    assert default_body["date_from"] == "2026-10-18"
    assert default_body["date_to"] == "2026-10-24"
    assert default_body["total_jobs"] == 2
    coach_quota = next(
        item for item in default_body["quotas"] if item["quota_kind"] == "coach_messages"
    )
    assert coach_quota["users_with_usage"] == 1
    assert coach_quota["consumed"] == 2

    shanghai_23rd = await client.get(
        "/api/v1/admin/ai/usage?date_from=2026-10-23&date_to=2026-10-23",
        headers=headers,
    )
    assert shanghai_23rd.status_code == 200, shanghai_23rd.text
    body_23 = shanghai_23rd.json()
    assert body_23["date_from"] == "2026-10-23"
    assert body_23["date_to"] == "2026-10-23"
    assert body_23["total_jobs"] == 1
    assert (
        next(item for item in body_23["quotas"] if item["quota_kind"] == "coach_messages")[
            "consumed"
        ]
        == 1
    )

    shanghai_24th = await client.get(
        "/api/v1/admin/ai/usage?date_from=2026-10-24&date_to=2026-10-24",
        headers=headers,
    )
    assert shanghai_24th.status_code == 200, shanghai_24th.text
    body_24 = shanghai_24th.json()
    assert body_24["total_jobs"] == 1
    assert (
        next(item for item in body_24["quotas"] if item["quota_kind"] == "coach_messages")[
            "consumed"
        ]
        == 1
    )

    invalid = await client.get(
        "/api/v1/admin/ai/usage?date_from=2026-10-24&date_to=2026-10-23",
        headers=headers,
    )
    assert invalid.status_code == 422
    assert invalid.json()["code"] == "AI_USAGE_DATE_RANGE_INVALID"


async def test_admin_usage_is_aggregate_only(client, admin_user) -> None:
    headers = await login(client, admin_user.username)
    response = await client.get("/api/v1/admin/ai/usage", headers=headers)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["total_jobs"] == 0
    assert len(body["quotas"]) == 3
    assert "users" not in body


async def test_ai_provider_url_block_is_a_safe_422(client, admin_user) -> None:
    headers = await login(client, admin_user.username)
    response = await client.post(
        PROVIDERS_PATH,
        headers=headers,
        json={
            "name": "Blocked",
            "base_url": "http://169.254.169.254/v1",
            "api_key": "sk-blocked-secret-1234",
            "model_id": "blocked-model",
        },
    )
    assert response.status_code == 422
    assert response.json()["code"] == "AI_PROVIDER_URL_BLOCKED"
    assert "169.254.169.254" not in response.json()["message"]
