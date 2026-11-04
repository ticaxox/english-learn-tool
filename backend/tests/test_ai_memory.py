from __future__ import annotations

from uuid import UUID, uuid4

from app.models.ai import AiJob
from app.models.coach import CoachMessage
from tests.ai_support import create_provider, fake_provider_server, login
from tests.learning_support import activate, seed_wordbook

MEMORY_PATH = "/api/v1/me/ai/memory"
PROFILE_PATH = "/api/v1/users/me/profile"
PRACTICE_PATH = "/api/v1/practice"


async def _document(client, headers) -> dict:
    response = await client.get(MEMORY_PATH, headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


async def test_memory_is_one_editable_document(client, member_user) -> None:
    headers = await login(client, member_user.username)

    empty = await _document(client, headers)
    assert empty == {"content": "", "updated_at": None}

    saved = await client.put(
        MEMORY_PATH,
        headers=headers,
        json={"content": "我习惯早上背单词。\n请多练 affect / effect 的辨析。"},
    )
    assert saved.status_code == 200, saved.text
    assert saved.json()["content"] == "我习惯早上背单词。\n请多练 affect / effect 的辨析。"
    assert saved.json()["updated_at"]

    loaded = await _document(client, headers)
    assert loaded["content"] == saved.json()["content"]

    cleared = await client.put(MEMORY_PATH, headers=headers, json={"content": ""})
    assert cleared.status_code == 200
    assert cleared.json()["content"] == ""


async def test_profile_practice_and_chat_notes_join_the_same_document(
    client, app, member_user
) -> None:
    from tests.test_practice_api import _generate, _questions

    headers = await login(client, member_user.username)
    profile = await client.patch(
        PROFILE_PATH,
        headers=headers,
        json={"target_exam": "IELTS", "daily_new_words": 12, "daily_study_minutes": 45},
    )
    assert profile.status_code == 200, profile.text

    document = await _document(client, headers)
    assert "用户信息：" in document["content"]
    assert "雅思" in document["content"]
    assert "12" in document["content"]

    wordbook_id = await seed_wordbook(app, owner_id=member_user.id, entries=8)
    await activate(app, user_id=member_user.id, wordbook_id=wordbook_id)
    with fake_provider_server() as server:
        await create_provider(client, headers, base_url=server.base_url)
        fill = await _generate(app, client, headers, server, "fill_blank", 3)
        questions = await _questions(app, fill["id"])
        answers = [
            {
                "question_id": str(question.id),
                "answer": question.private_payload["correct_option_id"],
            }
            for question in questions
        ]
        submitted = await client.post(
            f"{PRACTICE_PATH}/sessions/{fill['id']}/submit",
            headers={**headers, "Idempotency-Key": f"memory-submit-{uuid4().hex}"},
            json={"answers": answers},
        )
        assert submitted.status_code == 202, submitted.text

        conversation = await client.post(
            "/api/v1/coach/conversations", headers=headers, json={"title": "记忆"}
        )
        conversation_id = conversation.json()["id"]
        accepted = await client.post(
            f"/api/v1/coach/conversations/{conversation_id}/messages",
            headers={**headers, "Idempotency-Key": f"memory-{uuid4().hex}"},
            json={"content": "请记住我习惯早上背单词，晚上做题。"},
        )
        assert accepted.status_code == 202, accepted.text

        async with app.state.session_factory() as session:
            message = await session.get(CoachMessage, UUID(accepted.json()["message_id"]))
            assert message is not None and message.ai_job_id is not None
            job = await session.get(AiJob, message.ai_job_id)

    content = (await _document(client, headers))["content"]
    assert "用户信息：" in content
    assert "做题：填空练习" in content
    assert "全部答对" in content
    assert "对话：请记住我习惯早上背单词，晚上做题。" in content
    assert "用户要求：请记住我习惯早上背单词，晚上做题。" in content

    assert job.input_context["memory_document"] == content


async def test_manual_notes_survive_later_automatic_updates(client, app, member_user) -> None:
    headers = await login(client, member_user.username)
    await client.put(
        MEMORY_PATH,
        headers=headers,
        json={"content": "手动笔记：我在准备雅思，请用英式表达。"},
    )
    with fake_provider_server() as server:
        await create_provider(client, headers, base_url=server.base_url)
        conversation = await client.post(
            "/api/v1/coach/conversations", headers=headers, json={"title": "继续"}
        )
        conversation_id = conversation.json()["id"]
        accepted = await client.post(
            f"/api/v1/coach/conversations/{conversation_id}/messages",
            headers={**headers, "Idempotency-Key": f"keep-{uuid4().hex}"},
            json={"content": "今天练什么？"},
        )
        assert accepted.status_code == 202, accepted.text

    content = (await _document(client, headers))["content"]
    assert "手动笔记：我在准备雅思，请用英式表达。" in content
    assert "对话：今天练什么？" in content
    assert "用户信息：" in content
