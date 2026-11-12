from __future__ import annotations

from uuid import UUID, uuid4

from sqlalchemy import select

from app.models.ai import AiJob
from app.models.ai_memory import AiMemory
from app.models.coach import CoachMessage
from app.models.coach_memory import CoachMemory
from tests.ai_support import create_provider, fake_provider_server, login
from tests.learning_support import activate, seed_wordbook

MEMORIES_PATH = "/api/v1/me/memories"
PROFILE_PATH = "/api/v1/users/me/profile"
PRACTICE_PATH = "/api/v1/practice"


async def _memories(client, headers, **params) -> list[dict]:
    response = await client.get(MEMORIES_PATH, headers=headers, params=params or None)
    assert response.status_code == 200, response.text
    return response.json()["items"]


async def test_memories_are_typed_rows_that_can_be_edited_and_forgotten(
    client, member_user
) -> None:
    headers = await login(client, member_user.username)
    assert await _memories(client, headers) == []

    created = await client.post(
        MEMORIES_PATH,
        headers=headers,
        json={"kind": "preference", "content": "我习惯早上背单词", "subject_key": "study_time"},
    )
    assert created.status_code == 201, created.text
    memory = created.json()
    assert memory["kind"] == "preference"
    assert memory["source"] == "user_explicit"
    assert memory["status"] == "active"

    edited = await client.patch(
        f"{MEMORIES_PATH}/{memory['id']}",
        headers=headers,
        json={"content": "我习惯晚上背单词", "importance": 5},
    )
    assert edited.status_code == 200, edited.text
    assert edited.json()["content"] == "我习惯晚上背单词"
    assert edited.json()["importance"] == 5

    removed = await client.delete(f"{MEMORIES_PATH}/{memory['id']}", headers=headers)
    assert removed.status_code == 204
    assert await _memories(client, headers) == []


async def test_a_new_memory_with_the_same_subject_supersedes_the_old_one(
    client, member_user
) -> None:
    headers = await login(client, member_user.username)
    first = await client.post(
        MEMORIES_PATH,
        headers=headers,
        json={"kind": "goal", "content": "目标雅思 6.5", "subject_key": "exam_goal"},
    )
    second = await client.post(
        MEMORIES_PATH,
        headers=headers,
        json={"kind": "goal", "content": "目标雅思 7.0", "subject_key": "exam_goal"},
    )
    assert second.status_code == 201, second.text

    active = await _memories(client, headers)
    assert [item["content"] for item in active] == ["目标雅思 7.0"]

    history = await _memories(client, headers, include_history=True)
    statuses = {item["content"]: item["status"] for item in history}
    assert statuses["目标雅思 6.5"] == "superseded"
    assert statuses["目标雅思 7.0"] == "active"
    assert first.json()["id"] != second.json()["id"]


async def test_coach_context_uses_snapshots_and_recalled_memories(client, app, member_user) -> None:
    headers = await login(client, member_user.username)
    await client.patch(
        PROFILE_PATH,
        headers=headers,
        json={"target_exam": "IELTS", "daily_new_words": 12, "daily_study_minutes": 45},
    )
    await client.post(
        MEMORIES_PATH,
        headers=headers,
        json={"kind": "constraint", "content": "不要安排晚上 10 点后的任务"},
    )

    with fake_provider_server() as server:
        await create_provider(client, headers, base_url=server.base_url)
        conversation = await client.post(
            "/api/v1/coach/conversations", headers=headers, json={"title": "记忆"}
        )
        conversation_id = conversation.json()["id"]
        accepted = await client.post(
            f"/api/v1/coach/conversations/{conversation_id}/messages",
            headers={**headers, "Idempotency-Key": f"mem-{uuid4().hex}"},
            json={"content": "今晚 10 点后给我安排任务吧"},
        )
        assert accepted.status_code == 202, accepted.text

        async with app.state.session_factory() as session:
            message = await session.get(CoachMessage, UUID(accepted.json()["message_id"]))
            assert message is not None and message.ai_job_id is not None
            job = await session.get(AiJob, message.ai_job_id)

    context = job.input_context
    assert any("雅思" in line for line in [context["profile_snapshot"]])
    assert any("不要安排晚上" in line for line in context["recalled_memories"])
    # The single growing document is gone.
    assert context.get("memory_document") is None


async def test_submitting_practice_does_not_grow_memory(client, app, member_user) -> None:
    from tests.test_practice_api import _generate, _questions

    headers = await login(client, member_user.username)
    wordbook_id = await seed_wordbook(app, owner_id=member_user.id, entries=8)
    await activate(app, user_id=member_user.id, wordbook_id=wordbook_id)
    with fake_provider_server() as server:
        await create_provider(client, headers, base_url=server.base_url)
        fill = await _generate(app, client, headers, server, "fill_blank", 3)
        questions = await _questions(app, fill["id"])
        submitted = await client.post(
            f"{PRACTICE_PATH}/sessions/{fill['id']}/submit",
            headers={**headers, "Idempotency-Key": f"no-memory-{uuid4().hex}"},
            json={
                "answers": [
                    {"question_id": str(question.id), "answer": "a"} for question in questions
                ]
            },
        )
        assert submitted.status_code == 202, submitted.text

    assert await _memories(client, headers) == []


async def test_legacy_document_is_imported_without_practice_or_chat_noise(
    client, app, member_user
) -> None:
    headers = await login(client, member_user.username)
    async with app.state.session_factory() as session:
        session.add(
            AiMemory(
                user_id=member_user.id,
                kind="custom",
                memory_key="memory_document",
                source="user",
                content="\n".join(
                    [
                        "用户信息：demo_member · 目标考试：雅思，每日新词：12 个",
                        "习惯偏好：偏好题型：阅读；记忆方式：翻卡",
                        "做题：填空练习 · 3 题 · 正确 3 · 全部答对",
                        "对话：今天练什么？",
                        "用户要求：不要安排晚上的任务",
                    ]
                ),
            )
        )
        await session.commit()

    with fake_provider_server() as server:
        await create_provider(client, headers, base_url=server.base_url)
        conversation = await client.post(
            "/api/v1/coach/conversations", headers=headers, json={"title": "导入"}
        )
        accepted = await client.post(
            f"/api/v1/coach/conversations/{conversation.json()['id']}/messages",
            headers={**headers, "Idempotency-Key": f"legacy-{uuid4().hex}"},
            json={"content": "还记得我的目标吗"},
        )
        assert accepted.status_code == 202, accepted.text

    items = await _memories(client, headers)
    contents = [item["content"] for item in items]
    assert any("目标考试：雅思" in content for content in contents)
    assert any("不要安排晚上的任务" in content for content in contents)
    assert not any(content.startswith("填空练习") for content in contents)
    assert not any("今天练什么" in content for content in contents)
    assert all(item["source"] == "imported" for item in items)

    async with app.state.session_factory() as session:
        rows = list((await session.scalars(select(CoachMemory))).all())
    assert len([row for row in rows if row.user_id == member_user.id]) == len(items)
