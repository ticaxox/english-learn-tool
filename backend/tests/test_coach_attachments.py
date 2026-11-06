from __future__ import annotations

from uuid import UUID

from app.models.coach import CoachMessage
from app.services.ai_jobs import process_ai_job
from tests.ai_support import create_provider, fake_provider_server, login

PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"0" * 64


async def _conversation(client, headers) -> str:
    created = await client.post(
        "/api/v1/coach/conversations",
        headers=headers,
        json={"title": "图片对话"},
    )
    assert created.status_code == 201, created.text
    return created.json()["id"]


async def test_upload_message_and_read_back_an_image(client, member_user):
    headers = await login(client, member_user.username)
    conversation_id = await _conversation(client, headers)

    uploaded = await client.post(
        f"/api/v1/coach/conversations/{conversation_id}/attachments",
        headers=headers,
        files={"file": ("cat.png", PNG_BYTES, "image/png")},
    )
    assert uploaded.status_code == 201, uploaded.text
    attachment = uploaded.json()
    assert attachment["content_type"] == "image/png"
    assert attachment["size_bytes"] == len(PNG_BYTES)

    with fake_provider_server() as server:
        await create_provider(client, headers, base_url=server.base_url)
        sent = await client.post(
            f"/api/v1/coach/conversations/{conversation_id}/messages",
            headers={**headers, "Idempotency-Key": "attachment-message"},
            json={"content": "这张图里的词怎么记？", "attachment_ids": [attachment["id"]]},
        )
        assert sent.status_code == 202, sent.text

    messages = await client.get(
        f"/api/v1/coach/conversations/{conversation_id}/messages", headers=headers
    )
    assert messages.status_code == 200, messages.text
    user_message = next(
        item for item in messages.json()["items"] if item["role"] == "user"
    )
    assert [item["id"] for item in user_message["attachments"]] == [attachment["id"]]

    fetched = await client.get(
        f"/api/v1/coach/attachments/{attachment['id']}", headers=headers
    )
    assert fetched.status_code == 200
    assert fetched.headers["content-type"] == "image/png"
    assert fetched.content == PNG_BYTES


async def test_rejects_unsupported_type_and_oversized_image(client, member_user):
    headers = await login(client, member_user.username)
    conversation_id = await _conversation(client, headers)

    text_file = await client.post(
        f"/api/v1/coach/conversations/{conversation_id}/attachments",
        headers=headers,
        files={"file": ("notes.txt", b"hello", "text/plain")},
    )
    assert text_file.status_code == 415
    assert text_file.json()["code"] == "COACH_ATTACHMENT_TYPE_UNSUPPORTED"

    big = b"\x89PNG\r\n\x1a\n" + b"0" * (5 * 1024 * 1024)
    too_big = await client.post(
        f"/api/v1/coach/conversations/{conversation_id}/attachments",
        headers=headers,
        files={"file": ("big.png", big, "image/png")},
    )
    assert too_big.status_code == 413
    assert too_big.json()["code"] == "COACH_ATTACHMENT_TOO_LARGE"


async def test_attachment_from_another_conversation_is_rejected(client, member_user):
    headers = await login(client, member_user.username)
    first = await _conversation(client, headers)
    second = await _conversation(client, headers)

    uploaded = await client.post(
        f"/api/v1/coach/conversations/{first}/attachments",
        headers=headers,
        files={"file": ("cat.png", PNG_BYTES, "image/png")},
    )
    attachment_id = uploaded.json()["id"]

    with fake_provider_server() as server:
        await create_provider(client, headers, base_url=server.base_url)
        rejected = await client.post(
            f"/api/v1/coach/conversations/{second}/messages",
            headers={**headers, "Idempotency-Key": "cross-conversation"},
            json={"content": "借用图片", "attachment_ids": [attachment_id]},
        )
    assert rejected.status_code == 422
    assert rejected.json()["code"] == "COACH_ATTACHMENT_INVALID"


async def test_image_payload_reaches_the_provider(client, app, member_user):
    headers = await login(client, member_user.username)
    conversation_id = await _conversation(client, headers)
    uploaded = await client.post(
        f"/api/v1/coach/conversations/{conversation_id}/attachments",
        headers=headers,
        files={"file": ("cat.png", PNG_BYTES, "image/png")},
    )
    attachment_id = UUID(uploaded.json()["id"])

    with fake_provider_server() as server:
        await create_provider(client, headers, base_url=server.base_url)
        server.queue_json(200, {"message": "看到了这张图。", "actions": []})
        sent = await client.post(
            f"/api/v1/coach/conversations/{conversation_id}/messages",
            headers={**headers, "Idempotency-Key": "image-provider"},
            json={"content": "看图", "attachment_ids": [str(attachment_id)]},
        )
        assert sent.status_code == 202, sent.text

        async with app.state.session_factory() as session:
            message = await session.get(CoachMessage, UUID(sent.json()["message_id"]))
            assert message is not None and message.ai_job_id is not None
            job_id = message.ai_job_id
        await process_ai_job(
            {
                "session_factory": app.state.session_factory,
                "settings": app.state.settings,
                "redis": app.state.arq,
            },
            str(job_id),
        )

        job = next(
            request
            for request in server.requests
            if request["method"] == "POST" and "/chat/completions" in request["path"]
        )
        user_content = job["body"]["messages"][1]["content"]
        assert isinstance(user_content, list)
        assert user_content[0]["type"] == "text"
        assert user_content[1]["type"] == "image_url"
        assert user_content[1]["image_url"]["url"].startswith("data:image/png;base64,")
