from __future__ import annotations

from sqlalchemy import select

from app.models.ai import AiPrompt, AiProvider
from app.models.identity import AuditLog
from tests.ai_support import (
    PROMPTS_PATH,
    PROVIDERS_PATH,
    create_provider,
    fake_provider_server,
    login,
)


async def test_ai_admin_provider_crud_masks_keys_and_checks_real_http(
    client, app, admin_user, member_user
) -> None:
    member_headers = await login(client, member_user.username)
    forbidden = await client.get(PROVIDERS_PATH, headers=member_headers)
    assert forbidden.status_code == 403
    assert forbidden.json()["code"] == "FORBIDDEN"

    headers = await login(client, admin_user.username)
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

        tested = await client.post(f"{PROVIDERS_PATH}/{primary['id']}/test", headers=headers)
        assert tested.status_code == 200
        assert tested.json()["success"] is True
        assert tested.json()["models"] == ["fake-model", "fake-model-2"]

        models = await client.post(f"{PROVIDERS_PATH}/{primary['id']}/models", headers=headers)
        assert models.status_code == 200
        assert models.json()["success"] is True
        assert models.json()["models"] == ["fake-model", "fake-model-2"]

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

        deleted = await client.delete(f"{PROVIDERS_PATH}/{backup['id']}", headers=headers)
        assert deleted.status_code == 204
        listed = await client.get(PROVIDERS_PATH, headers=headers)
        assert listed.json()["items"][0]["id"] == primary["id"]
        assert listed.json()["items"][0]["is_default"] is True

    async with app.state.session_factory() as session:
        actions = set((await session.scalars(select(AuditLog.action))).all())
        assert "ai.provider.created" in actions
        assert "ai.provider.tested" in actions
        assert "ai.provider.updated" in actions
        assert "ai.provider.deleted" in actions


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
