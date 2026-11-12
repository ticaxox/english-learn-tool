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
        "create_practice_questions",
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


async def test_tokens_support_default_delete_and_refresh(client, member_user):
    headers = await login(client, member_user.username)
    token_id, token = await _create_token(client, headers)
    auth = {"Authorization": f"Bearer {token}"}

    listed = await client.get("/api/v1/me/tokens", headers=headers)
    items = listed.json()["items"]
    default = next(item for item in items if item["is_default"])
    assert default["name"] == "网页默认令牌"
    assert {item["id"] for item in items} >= {token_id, default["id"]}

    protected = await client.delete(f"/api/v1/me/tokens/{default['id']}", headers=headers)
    assert protected.status_code == 409
    assert protected.json()["code"] == "PERSONAL_TOKEN_DEFAULT"

    allowed = await client.post("/api/v1/mcp", headers=auth, json=_rpc(2, "tools/list"))
    assert allowed.status_code == 200
    removed = await client.delete(f"/api/v1/me/tokens/{token_id}", headers=headers)
    assert removed.status_code == 204
    rejected = await client.post("/api/v1/mcp", headers=auth, json=_rpc(3, "tools/list"))
    assert rejected.status_code == 401

    rotated = await client.post(f"/api/v1/me/tokens/{default['id']}/refresh", headers=headers)
    assert rotated.status_code == 200, rotated.text
    fresh = {"Authorization": f"Bearer {rotated.json()['token']}"}
    refreshed = await client.post("/api/v1/mcp", headers=fresh, json=_rpc(4, "tools/list"))
    assert refreshed.status_code == 200

    second_id, second_token = await _create_token(client, headers)
    rotated = await client.post(f"/api/v1/me/tokens/{second_id}/refresh", headers=headers)
    assert rotated.status_code == 200
    assert (
        await client.post(
            "/api/v1/mcp",
            headers={"Authorization": f"Bearer {second_token}"},
            json=_rpc(5, "tools/list"),
        )
    ).status_code == 401
    assert (
        await client.post(
            "/api/v1/mcp",
            headers={"Authorization": f"Bearer {rotated.json()['token']}"},
            json=_rpc(6, "tools/list"),
        )
    ).status_code == 200


async def test_mcp_can_write_questions_without_ai(client, member_user):
    headers = await login(client, member_user.username)
    _, token = await _create_token(client, headers)
    auth = {"Authorization": f"Bearer {token}"}

    def option(option_id: str, text: str) -> dict:
        return {"id": option_id, "text": text, "text_zh": f"{text}的中文"}

    written = await client.post(
        "/api/v1/mcp",
        headers=auth,
        json=_rpc(
            1,
            "tools/call",
            {
                "name": "create_practice_questions",
                "arguments": {
                    "practice_type": "fill_blank",
                    "items": [
                        {
                            "id": "q1",
                            "sentence": "I have a ____ of tea.",
                            "sentence_zh": "我有一杯茶。",
                            "options": [
                                option("a", "cup"),
                                option("b", "cap"),
                                option("c", "cop"),
                                option("d", "cub"),
                            ],
                            "correct_option_id": "a",
                            "explanation": "cup 是杯子。",
                        }
                    ],
                },
            },
        ),
    )
    result = written.json()["result"]
    assert result["isError"] is False, result
    payload = json.loads(result["content"][0]["text"])
    assert payload["question_count"] == 1

    session = await client.get(
        f"/api/v1/practice/sessions/{payload['practice_session_id']}", headers=headers
    )
    assert session.status_code == 200, session.text
    body = session.json()
    assert body["status"] == "ready"
    assert [item["sentence"] for item in body["questions"]] == ["I have a ____ of tea."]
