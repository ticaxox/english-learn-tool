from __future__ import annotations

from uuid import UUID, uuid4

from app.models.ai import AiJob
from app.models.coach import CoachMessage
from tests.ai_support import create_provider, fake_provider_server, login
from tests.learning_support import activate, seed_wordbook

MEMORY_PATH = "/api/v1/me/ai/memories"
PROFILE_PATH = "/api/v1/users/me/profile"
PRACTICE_PATH = "/api/v1/practice"


async def _memories(client, headers, kind: str | None = None) -> list[dict]:
    params = {"kind": kind} if kind else None
    response = await client.get(MEMORY_PATH, headers=headers, params=params)
    assert response.status_code == 200, response.text
    return response.json()["items"]


async def test_manual_memory_crud_and_auto_clear(client, member_user) -> None:
    headers = await login(client, member_user.username)

    created = await client.post(
        MEMORY_PATH,
        headers=headers,
        json={"kind": "custom", "content": "我容易混淆 affect 和 effect，请多给我这类题。"},
    )
    assert created.status_code == 201, created.text
    memory = created.json()
    assert memory["source"] == "user"
    assert memory["kind"] == "custom"

    listed = await client.get(MEMORY_PATH, headers=headers)
    assert listed.status_code == 200
    assert listed.json()["counts"]["custom"] >= 1
    assert any(item["id"] == memory["id"] for item in listed.json()["items"])

    updated = await client.patch(
        f"{MEMORY_PATH}/{memory['id']}",
        headers=headers,
        json={"content": "我更想练 affect / effect 辨析。", "pinned": True},
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["content"] == "我更想练 affect / effect 辨析。"
    assert updated.json()["pinned"] is True

    cleared = await client.post(f"{MEMORY_PATH}/clear-auto", headers=headers)
    assert cleared.status_code == 200, cleared.text
    assert cleared.json()["deleted_count"] >= 0
    remaining = await _memories(client, headers)
    assert any(item["id"] == memory["id"] for item in remaining)

    deleted = await client.delete(f"{MEMORY_PATH}/{memory['id']}", headers=headers)
    assert deleted.status_code == 204
    assert all(item["id"] != memory["id"] for item in await _memories(client, headers))


async def test_profile_and_chat_memories_reach_the_coach_context(client, app, member_user) -> None:
    headers = await login(client, member_user.username)
    profile = await client.patch(
        PROFILE_PATH,
        headers=headers,
        json={"target_exam": "IELTS", "daily_new_words": 12, "daily_study_minutes": 45},
    )
    assert profile.status_code == 200, profile.text

    profile_memories = await _memories(client, headers, "profile")
    assert profile_memories
    assert "雅思" in profile_memories[0]["content"]
    assert "12" in profile_memories[0]["content"]

    with fake_provider_server() as server:
        await create_provider(client, headers, base_url=server.base_url)
        conversation = await client.post(
            "/api/v1/coach/conversations",
            headers=headers,
            json={"title": "记忆"},
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

    kinds = {item["kind"] for item in job.input_context["memories"]}
    assert "profile" in kinds
    assert "chat" in kinds
    assert "custom" in kinds
    custom = [item for item in job.input_context["memories"] if item["kind"] == "custom"]
    assert "早上背单词" in custom[0]["content"]

    stored = await _memories(client, headers)
    assert any(item["kind"] == "chat" and "早上背单词" in item["content"] for item in stored)
    custom_row = next(item for item in stored if item["kind"] == "custom")
    assert custom_row["source"] == "user"

    # Clearing automatic memories keeps what the learner explicitly asked for.
    cleared = await client.post(f"{MEMORY_PATH}/clear-auto", headers=headers)
    assert cleared.status_code == 200
    after = await _memories(client, headers)
    assert not any(item["kind"] == "practice" for item in after)
    assert not any(item["kind"] == "profile" for item in after)
    assert any(item["id"] == custom_row["id"] for item in after)


async def test_objective_submission_records_a_practice_memory(client, app, member_user) -> None:
    from tests.test_practice_api import _generate, _questions

    headers = await login(client, member_user.username)
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

    practice_memories = await _memories(client, headers, "practice")
    assert practice_memories
    content = practice_memories[0]["content"]
    assert "填空练习" in content
    assert "3 题" in content
    assert "全部答对" in content
