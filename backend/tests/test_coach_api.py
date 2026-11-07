from __future__ import annotations

from datetime import timedelta
from uuid import UUID

from sqlalchemy import select

from app.models.ai import AiJob
from app.models.coach import CoachConversation, CoachMessage
from app.models.identity import UserProfile
from app.services.ai_jobs import process_ai_job
from app.services.auth import utcnow
from app.services.coach import cleanup_coach_data
from tests.ai_support import create_provider, fake_provider_server, login


def coach_output(*, actions: list[dict] | None = None) -> dict:
    return {
        "message": "先复习今天的到期单词，再完成一组短文阅读。",
        "actions": actions or [],
    }


async def _run_job(app, job_id: UUID) -> dict:
    return await process_ai_job(
        {
            "session_factory": app.state.session_factory,
            "settings": app.state.settings,
            "redis": app.state.arq,
        },
        str(job_id),
    )


async def _create_message(
    client, headers, conversation_id: str, key: str, content: str = "请根据我的进度安排学习。"
) -> dict:
    response = await client.post(
        f"/api/v1/coach/conversations/{conversation_id}/messages",
        headers={**headers, "Idempotency-Key": key},
        json={"content": content, "page_context": {"page_route": "/today"}},
    )
    assert response.status_code == 202, response.text
    return response.json()


async def test_coach_context_drops_history_older_than_expiry(client, app, member_user):
    headers = await login(client, member_user.username)
    with fake_provider_server() as server:
        await create_provider(client, headers, base_url=server.base_url)
        created = await client.post(
            "/api/v1/coach/conversations",
            headers=headers,
            json={"title": "上下文窗口"},
        )
        conversation_id = UUID(created.json()["id"])

        now = utcnow()
        async with app.state.session_factory() as session:
            conversation = await session.get(CoachConversation, conversation_id)
            assert conversation is not None
            session.add_all(
                [
                    CoachMessage(
                        conversation_id=conversation_id,
                        user_id=member_user.id,
                        role="user",
                        content="已经过期的旧问题",
                        status="completed",
                        sequence=1,
                        created_at=now - timedelta(days=2),
                        completed_at=now - timedelta(days=2),
                    ),
                    CoachMessage(
                        conversation_id=conversation_id,
                        user_id=member_user.id,
                        role="assistant",
                        content="仍然有效的最近回答",
                        status="completed",
                        sequence=2,
                        created_at=now - timedelta(hours=1),
                        completed_at=now - timedelta(hours=1),
                    ),
                ]
            )
            conversation.message_count += 2
            await session.commit()

        accepted = await _create_message(
            client, headers, str(conversation_id), "ctx-key-1", "新的问题"
        )
        async with app.state.session_factory() as session:
            message = await session.get(CoachMessage, UUID(accepted["message_id"]))
            assert message is not None and message.ai_job_id is not None
            job = await session.get(AiJob, message.ai_job_id)

        history = job.input_context["history"]
        joined = " ".join(turn["content"] for turn in history)
        assert "仍然有效的最近回答" in joined
        assert "已经过期的旧问题" not in joined


async def test_coach_message_sse_actions_undo_and_idempotency(client, app, member_user):
    headers = await login(client, member_user.username)
    with fake_provider_server() as server:
        await create_provider(client, headers, base_url=server.base_url)
        created = await client.post(
            "/api/v1/coach/conversations",
            headers=headers,
            json={"title": "学习计划"},
        )
        assert created.status_code == 201, created.text
        conversation_id = created.json()["id"]

        accepted = await _create_message(client, headers, conversation_id, "coach-key-1")
        message_id = UUID(accepted["message_id"])
        async with app.state.session_factory() as session:
            message = await session.get(CoachMessage, message_id)
            assert message is not None and message.ai_job_id is not None
            job_id = message.ai_job_id

        replay = await _create_message(client, headers, conversation_id, "coach-key-1")
        assert replay["message_id"] == accepted["message_id"]
        conflict = await client.post(
            f"/api/v1/coach/conversations/{conversation_id}/messages",
            headers={**headers, "Idempotency-Key": "coach-key-1"},
            json={"content": "不同的消息", "page_context": {"page_route": "/today"}},
        )
        assert conflict.status_code == 409
        assert conflict.json()["code"] == "COACH_IDEMPOTENCY_CONFLICT"

        server.queue_json(
            200,
            coach_output(
                actions=[
                    {
                        "action_type": "adjust_daily_plan",
                        "parameters": {"new_words": 25, "study_minutes": 45},
                        "summary": "把今日新词目标调整为 25，学习时长调整为 45 分钟。",
                    }
                ]
            ),
        )
        result = await _run_job(app, job_id)
        assert result["status"] == "succeeded"

        final = await client.get(f"/api/v1/coach/messages/{message_id}", headers=headers)
        assert final.status_code == 200, final.text
        body = final.json()
        assert body["status"] == "completed"
        assert "到期单词" in body["content"]
        assert len(body["actions"]) == 1
        receipt = body["actions"][0]
        assert receipt["status"] == "applied"
        assert receipt["action_type"] == "adjust_daily_plan"

        stream = await client.get(
            f"/api/v1/coach/streams/{message_id}",
            headers=headers,
        )
        assert stream.status_code == 200, stream.text
        assert "event: message.delta" in stream.text
        assert "event: action.applied" in stream.text
        assert "event: usage" in stream.text
        assert "event: done" in stream.text

        reconnect = await client.get(
            f"/api/v1/coach/streams/{message_id}",
            headers={**headers, "Last-Event-ID": "1"},
        )
        assert reconnect.status_code == 200
        assert "event: action.applied" in reconnect.text
        assert "event: done" in reconnect.text

        replay_stream = await client.get(
            f"/api/v1/coach/streams/{message_id}?after=9999", headers=headers
        )
        assert replay_stream.status_code == 200
        assert "event: done" not in replay_stream.text

        undone = await client.post(
            f"/api/v1/coach/action-receipts/{receipt['id']}/undo", headers=headers
        )
        assert undone.status_code == 200, undone.text
        assert undone.json()["receipt"]["status"] == "undone"
        async with app.state.session_factory() as session:
            profile = await session.scalar(
                select(UserProfile).where(UserProfile.user_id == member_user.id)
            )
            assert profile is not None
            assert profile.daily_new_words == 20
            assert profile.daily_study_minutes == 30

        repeated = await client.post(
            f"/api/v1/coach/action-receipts/{receipt['id']}/undo", headers=headers
        )
        assert repeated.status_code == 200
        assert repeated.json()["receipt"]["status"] == "undone"


async def test_coach_message_failure_is_safe_and_recoverable(client, app, member_user):
    headers = await login(client, member_user.username)
    with fake_provider_server() as server:
        await create_provider(client, headers, base_url=server.base_url)
        created = await client.post("/api/v1/coach/conversations", headers=headers, json={})
        conversation_id = created.json()["id"]
        accepted = await _create_message(client, headers, conversation_id, "coach-fail-1")
        message_id = UUID(accepted["message_id"])
        async with app.state.session_factory() as session:
            message = await session.get(CoachMessage, message_id)
            assert message is not None and message.ai_job_id is not None
            job_id = message.ai_job_id
        for _ in range(3):
            server.queue_json(500, {"error": "provider down"})
        result = await _run_job(app, job_id)
        assert result["status"] == "failed"

        final = await client.get(f"/api/v1/coach/messages/{message_id}", headers=headers)
        assert final.status_code == 200
        assert final.json()["status"] == "failed"
        assert final.json()["error_code"]
        assert final.json()["content"] is None

        stream = await client.get(f"/api/v1/coach/streams/{message_id}", headers=headers)
        assert stream.status_code == 200
        assert "event: error" in stream.text
        assert "provider down" not in stream.text


async def test_coach_action_conflict_and_user_isolation(client, app, member_user, user_factory):
    headers = await login(client, member_user.username)
    other = await user_factory(role="member")
    other_headers = await login(client, other.username)
    with fake_provider_server() as server:
        await create_provider(client, headers, base_url=server.base_url)
        created = await client.post("/api/v1/coach/conversations", headers=headers, json={})
        conversation_id = created.json()["id"]
        accepted = await _create_message(client, headers, conversation_id, "coach-conflict-1")
        message_id = UUID(accepted["message_id"])
        async with app.state.session_factory() as session:
            message = await session.get(CoachMessage, message_id)
            assert message is not None and message.ai_job_id is not None
            job_id = message.ai_job_id
        server.queue_json(
            200,
            coach_output(
                actions=[
                    {
                        "action_type": "adjust_daily_plan",
                        "parameters": {"new_words": 40},
                        "summary": "提高新词目标。",
                    }
                ]
            ),
        )
        assert (await _run_job(app, job_id))["status"] == "succeeded"
        final = await client.get(f"/api/v1/coach/messages/{message_id}", headers=headers)
        receipt_id = final.json()["actions"][0]["id"]

        assert (
            await client.get(f"/api/v1/coach/messages/{message_id}", headers=other_headers)
        ).status_code == 404
        assert (
            await client.post(
                f"/api/v1/coach/action-receipts/{receipt_id}/undo",
                headers=other_headers,
            )
        ).status_code == 404

        async with app.state.session_factory() as session:
            profile = await session.scalar(
                select(UserProfile).where(UserProfile.user_id == member_user.id)
            )
            assert profile is not None
            profile.daily_new_words = 99
            await session.commit()

        conflict = await client.post(
            f"/api/v1/coach/action-receipts/{receipt_id}/undo", headers=headers
        )
        assert conflict.status_code == 409
        assert conflict.json()["code"] == "COACH_ACTION_STATE_CHANGED"


async def test_coach_retention_cleanup_removes_old_messages_and_context(client, app, member_user):
    headers = await login(client, member_user.username)
    with fake_provider_server() as server:
        await create_provider(client, headers, base_url=server.base_url)
        created = await client.post("/api/v1/coach/conversations", headers=headers, json={})
        conversation_id = created.json()["id"]
        accepted = await _create_message(client, headers, conversation_id, "coach-retention-1")
        message_id = UUID(accepted["message_id"])
    async with app.state.session_factory() as session:
        message = await session.get(CoachMessage, message_id)
        assert message is not None
        message.status = "completed"
        message.completed_at = message.created_at
        await session.commit()
    async with app.state.session_factory() as session:
        result = await cleanup_coach_data(
            session,
            app.state.settings,
            now=message.created_at + timedelta(days=8),
        )
    assert result["messages"] >= 1
    assert (
        await client.get(f"/api/v1/coach/messages/{message_id}", headers=headers)
    ).status_code == 404


async def test_coach_start_practice_action_creates_scoped_practice(client, app, member_user):
    from app.models.practice import PracticeSession
    from app.models.wordbooks import Wordbook, WordbookEntry

    headers = await login(client, member_user.username)
    async with app.state.session_factory() as session:
        book = Wordbook(
            visibility="private",
            status="ready",
            name="Coach practice book",
            owner_id=member_user.id,
            created_by=member_user.id,
        )
        session.add(book)
        await session.flush()
        session.add(
            WordbookEntry(
                wordbook_id=book.id,
                headword="focus",
                normalized_headword="focus",
                sequence=0,
            )
        )
        await session.commit()
        wordbook_id = str(book.id)

    with fake_provider_server() as server:
        await create_provider(client, headers, base_url=server.base_url)
        created = await client.post("/api/v1/coach/conversations", headers=headers, json={})
        conversation_id = created.json()["id"]
        accepted = await _create_message(client, headers, conversation_id, "coach-practice-1")
        message_id = UUID(accepted["message_id"])
        async with app.state.session_factory() as session:
            message = await session.get(CoachMessage, message_id)
            assert message is not None and message.ai_job_id is not None
            job_id = message.ai_job_id
        server.queue_json(
            200,
            coach_output(
                actions=[
                    {
                        "action_type": "start_practice",
                        "parameters": {
                            "practice_type": "fill_blank",
                            "source": "whole_book",
                            "count": 3,
                            "wordbook_id": wordbook_id,
                        },
                        "summary": "开始一组填空题。",
                    }
                ]
            ),
        )
        result = await _run_job(app, job_id)
        assert result["status"] == "succeeded"
        final = await client.get(f"/api/v1/coach/messages/{message_id}", headers=headers)
        assert final.status_code == 200
        receipt = final.json()["actions"][0]
        assert receipt["status"] == "applied"
        assert receipt["action_type"] == "start_practice"
        practice_id = receipt["after_state"]["practice_session_id"]
        async with app.state.session_factory() as session:
            practice = await session.get(PracticeSession, UUID(practice_id))
            assert practice is not None
            assert practice.user_id == member_user.id
            assert practice.status == "generating"
        undone = await client.post(
            f"/api/v1/coach/action-receipts/{receipt['id']}/undo", headers=headers
        )
        assert undone.status_code == 200, undone.text
        async with app.state.session_factory() as session:
            practice = await session.get(PracticeSession, UUID(practice_id))
            assert practice is not None
            assert practice.status == "cancelled"


async def test_coach_other_whitelisted_actions_are_scoped_and_recorded(client, app, member_user):
    from app.models.learning import MistakeFlag
    from app.models.wordbooks import Wordbook, WordbookActivation, WordbookEntry

    headers = await login(client, member_user.username)
    async with app.state.session_factory() as session:
        book = Wordbook(
            visibility="private",
            status="ready",
            name="Coach action book",
            owner_id=member_user.id,
            created_by=member_user.id,
        )
        session.add(book)
        await session.flush()
        entry = WordbookEntry(
            wordbook_id=book.id,
            headword="priority",
            normalized_headword="priority",
            sequence=0,
        )
        session.add(entry)
        await session.commit()
        book_id = str(book.id)
        entry_id = str(entry.id)

    with fake_provider_server() as server:
        await create_provider(client, headers, base_url=server.base_url)
        created = await client.post("/api/v1/coach/conversations", headers=headers, json={})
        conversation_id = created.json()["id"]
        accepted = await _create_message(client, headers, conversation_id, "coach-actions-1")
        message_id = UUID(accepted["message_id"])
        async with app.state.session_factory() as session:
            message = await session.get(CoachMessage, message_id)
            assert message is not None and message.ai_job_id is not None
            job_id = message.ai_job_id
        server.queue_json(
            200,
            coach_output(
                actions=[
                    {
                        "action_type": "adjust_notification_preferences",
                        "parameters": {"categories": {"ai_action": False}, "daily_limit": 2},
                        "summary": "关闭 AI 操作提醒并调整每日上限。",
                    },
                    {
                        "action_type": "activate_wordbook",
                        "parameters": {"wordbook_id": book_id},
                        "summary": "切换主词书。",
                    },
                    {
                        "action_type": "mark_review_focus",
                        "parameters": {"entry_id": entry_id, "wordbook_id": book_id},
                        "summary": "标记重点复习。",
                    },
                ]
            ),
        )
        assert (await _run_job(app, job_id))["status"] == "succeeded"
        final = await client.get(f"/api/v1/coach/messages/{message_id}", headers=headers)
        assert final.status_code == 200
        receipts = final.json()["actions"]
        assert [item["status"] for item in receipts] == ["applied", "applied", "applied"]
        assert [item["action_type"] for item in receipts] == [
            "adjust_notification_preferences",
            "activate_wordbook",
            "mark_review_focus",
        ]
        async with app.state.session_factory() as session:
            profile = await session.scalar(
                select(UserProfile).where(UserProfile.user_id == member_user.id)
            )
            assert profile is not None
            assert profile.notification_preferences["categories"]["ai_action"] is False
            assert profile.notification_preferences["daily_limit"] == 2
            activation = await session.get(WordbookActivation, member_user.id)
            assert activation is not None and str(activation.wordbook_id) == book_id
            flag = await session.scalar(
                select(MistakeFlag).where(
                    MistakeFlag.user_id == member_user.id,
                    MistakeFlag.entry_id == UUID(entry_id),
                )
            )
            assert flag is not None and flag.is_priority is True


async def test_coach_conversations_keep_panel_and_page_histories_apart(client, member_user):
    headers = await login(client, member_user.username)
    panel = await client.post(
        "/api/v1/coach/conversations", headers=headers, json={"title": "侧栏对话"}
    )
    page = await client.post(
        "/api/v1/coach/conversations",
        headers=headers,
        json={"title": "页面对话", "scope": "page"},
    )
    assert panel.status_code == 201, panel.text
    assert page.status_code == 201, page.text
    assert panel.json()["scope"] == "panel"
    assert page.json()["scope"] == "page"

    panel_list = await client.get(
        "/api/v1/coach/conversations", headers=headers, params={"scope": "panel"}
    )
    page_list = await client.get(
        "/api/v1/coach/conversations", headers=headers, params={"scope": "page"}
    )
    assert [item["id"] for item in panel_list.json()["items"]] == [panel.json()["id"]]
    assert [item["id"] for item in page_list.json()["items"]] == [page.json()["id"]]
    # The default scope stays the floating panel.
    default_list = await client.get("/api/v1/coach/conversations", headers=headers)
    assert panel.json()["id"] in [item["id"] for item in default_list.json()["items"]]
    assert page.json()["id"] not in [item["id"] for item in default_list.json()["items"]]
