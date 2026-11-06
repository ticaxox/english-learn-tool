from __future__ import annotations

import json

from tests.ai_support import login


def _rpc(identifier: int, method: str, params: dict | None = None) -> dict:
    message: dict = {"jsonrpc": "2.0", "id": identifier, "method": method}
    if params is not None:
        message["params"] = params
    return message


async def _create_token(client, headers) -> tuple[str, str]:
    created = await client.post("/api/v1/me/tokens", headers=headers, json={"name": "Claude"})
    assert created.status_code == 201, created.text
    return created.json()["id"], created.json()["token"]


async def test_mcp_initializes_lists_tools_and_applies_an_action(client, member_user):
    headers = await login(client, member_user.username)
    _, token = await _create_token(client, headers)
    auth = {"Authorization": f"Bearer {token}"}

    initialized = await client.post(
        "/api/v1/mcp",
        headers=auth,
        json=_rpc(
            1,
            "initialize",
            {
                "protocolVersion": "2025-06-18",
                "capabilities": {},
                "clientInfo": {"name": "pytest", "version": "1.0"},
            },
        ),
    )
    assert initialized.status_code == 200, initialized.text
    assert initialized.json()["result"]["serverInfo"]["name"] == "english-learn-tool"
    assert initialized.json()["result"]["protocolVersion"] == "2025-06-18"

    listed = await client.post("/api/v1/mcp", headers=auth, json=_rpc(2, "tools/list"))
    names = {tool["name"] for tool in listed.json()["result"]["tools"]}
    assert {
        "adjust_daily_plan",
        "start_practice",
        "activate_wordbook",
        "mark_review_focus",
    } <= names

    applied = await client.post(
        "/api/v1/mcp",
        headers=auth,
        json=_rpc(
            3,
            "tools/call",
            {"name": "adjust_daily_plan", "arguments": {"new_words": 12}},
        ),
    )
    result = applied.json()["result"]
    assert result["isError"] is False
    payload = json.loads(result["content"][0]["text"])
    assert payload["after"]["new_words"] == 12

    invalid = await client.post(
        "/api/v1/mcp",
        headers=auth,
        json=_rpc(
            4,
            "tools/call",
            {"name": "adjust_daily_plan", "arguments": {"new_words": 1}},
        ),
    )
    assert invalid.json()["result"]["isError"] is True


async def test_mcp_requires_a_valid_revocable_token(client, member_user):
    headers = await login(client, member_user.username)
    token_id, token = await _create_token(client, headers)
    auth = {"Authorization": f"Bearer {token}"}

    assert (await client.post("/api/v1/mcp", json=_rpc(1, "tools/list"))).status_code == 401
    assert (
        await client.post(
            "/api/v1/mcp",
            headers={"Authorization": "Bearer elt_not-a-real-token"},
            json=_rpc(1, "tools/list"),
        )
    ).status_code == 401
    allowed = await client.post("/api/v1/mcp", headers=auth, json=_rpc(2, "tools/list"))
    assert allowed.status_code == 200

    revoked = await client.delete(f"/api/v1/me/tokens/{token_id}", headers=headers)
    assert revoked.status_code == 204
    rejected = await client.post("/api/v1/mcp", headers=auth, json=_rpc(3, "tools/list"))
    assert rejected.status_code == 401
