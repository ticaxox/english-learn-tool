from __future__ import annotations

from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo

from sqlalchemy import func, select

from app.models.learning import DailyActivity, DailyPlan, DailyPlanWord, UserWordState
from app.models.notifications import Notification, NotificationOutbox
from app.services.ai_jobs import process_ai_job
from app.services.notifications import (
    enqueue_notification_event,
    enqueue_scheduled_notification_events,
    process_notification_outbox,
)
from tests.ai_support import create_provider, fake_provider_server, login
from tests.learning_support import seed_wordbook

NOTIFICATIONS_PATH = "/api/v1/notifications"
PREFERENCES_PATH = "/api/v1/notifications/preferences"


async def _user_from_session(app, user):
    async with app.state.session_factory() as session:
        return await session.get(type(user), user.id)


async def test_preferences_defaults_and_update(client, member_user) -> None:
    headers = await login(client, member_user.username)
    response = await client.get(PREFERENCES_PATH, headers=headers)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["dnd_start"] == "22:00"
    assert body["dnd_end"] == "08:00"
    assert body["daily_limit"] == 3
    assert body["categories"]["due_review"] is True

    updated = await client.put(
        PREFERENCES_PATH,
        headers=headers,
        json={
            "categories": {
                "due_review": False,
                "today_incomplete": True,
                "streak_risk": True,
                "ai_completed": True,
                "ai_failed": True,
                "plan_adjusted": True,
                "ai_action": True,
            },
            "dnd_start": "21:00",
            "dnd_end": "07:00",
            "daily_limit": 2,
            "timezone": "Asia/Shanghai",
        },
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["categories"]["due_review"] is False
    assert updated.json()["dnd_start"] == "21:00"
    assert updated.json()["daily_limit"] == 2


async def test_outbox_dedupe_dnd_and_ai_exception(app, member_user) -> None:
    async with app.state.session_factory() as session:
        user = await session.get(type(member_user), member_user.id)
        assert user is not None
        settings = app.state.settings
        at_2159 = datetime(2026, 10, 23, 21, 59, tzinfo=ZoneInfo("Asia/Shanghai"))
        at_2200 = datetime(2026, 10, 23, 22, 0, tzinfo=ZoneInfo("Asia/Shanghai"))
        await enqueue_notification_event(
            session,
            user_id=user.id,
            category="due_review",
            dedupe_key="user:test:due:1",
            event_type="learning.due_review",
            payload={"title": "复习提醒", "body": "可以复习到期单词。"},
            available_at=at_2159,
        )
        await enqueue_notification_event(
            session,
            user_id=user.id,
            category="due_review",
            dedupe_key="user:test:due:1",
            event_type="learning.due_review",
            payload={"title": "重复", "body": "不应重复。"},
            available_at=at_2159,
        )
        await session.commit()
        await process_notification_outbox(session, settings, now=at_2159)
        await enqueue_notification_event(
            session,
            user_id=user.id,
            category="today_incomplete",
            dedupe_key="user:test:today:1",
            event_type="learning.today_incomplete",
            payload={"title": "今天任务", "body": "可以继续完成。"},
            available_at=at_2200,
        )
        await enqueue_notification_event(
            session,
            user_id=user.id,
            category="ai_completed",
            dedupe_key="user:test:ai:1",
            event_type="ai.job.completed",
            payload={"title": "AI 完成", "body": "AI 任务已完成。"},
            available_at=at_2200,
        )
        await session.commit()
        outbox_count = int(
            await session.scalar(
                select(func.count(NotificationOutbox.id)).where(
                    NotificationOutbox.user_id == user.id
                )
            )
            or 0
        )
        assert outbox_count == 3
        await process_notification_outbox(session, settings, now=at_2200)
        rows = list(
            (
                await session.scalars(
                    select(Notification)
                    .where(Notification.user_id == user.id)
                    .order_by(Notification.created_at.asc())
                )
            ).all()
        )
        by_key = {row.dedupe_key: row for row in rows}
        assert by_key["user:test:due:1"].status == "sent"
        assert by_key["user:test:today:1"].status == "suppressed"
        assert by_key["user:test:today:1"].suppressed_reason == "do_not_disturb"
        assert by_key["user:test:ai:1"].status == "sent"


async def test_notification_inbox_cursor_read_and_privacy(
    client, app, admin_user, member_user, user_factory
) -> None:
    other = await user_factory(role="member")
    async with app.state.session_factory() as session:
        member = await session.get(type(member_user), member_user.id)
        admin = await session.get(type(admin_user), admin_user.id)
        other_loaded = await session.get(type(other), other.id)
        assert member is not None and admin is not None and other_loaded is not None
        now = datetime(2026, 10, 23, 12, 0, tzinfo=ZoneInfo("Asia/Shanghai"))
        for index in range(3):
            await enqueue_notification_event(
                session,
                user_id=member.id,
                category="due_review",
                dedupe_key=f"inbox:{index}",
                event_type="learning.due_review",
                payload={"title": f"提醒 {index}", "body": "安全正文"},
                available_at=now,
            )
        await enqueue_notification_event(
            session,
            user_id=other_loaded.id,
            category="due_review",
            dedupe_key="other:1",
            event_type="learning.due_review",
            payload={"title": "他人的提醒", "body": "不可见"},
            available_at=now,
        )
        await session.commit()
        await process_notification_outbox(session, app.state.settings, now=now)

    member_headers = await login(client, member_user.username)
    page = await client.get(f"{NOTIFICATIONS_PATH}?limit=2", headers=member_headers)
    assert page.status_code == 200, page.text
    body = page.json()
    assert len(body["items"]) == 2
    assert body["has_more"] is True
    assert body["next_cursor"]
    second = await client.get(
        f"{NOTIFICATIONS_PATH}?limit=2&cursor={body['next_cursor']}",
        headers=member_headers,
    )
    assert second.status_code == 200
    assert len(second.json()["items"]) == 1

    notification_id = body["items"][0]["id"]
    read = await client.patch(
        f"{NOTIFICATIONS_PATH}/{notification_id}/read",
        headers=member_headers,
    )
    assert read.status_code == 200
    assert read.json()["read_at"] is not None
    read_again = await client.patch(
        f"{NOTIFICATIONS_PATH}/{notification_id}/read",
        headers=member_headers,
    )
    assert read_again.status_code == 200
    unread = await client.get(f"{NOTIFICATIONS_PATH}/unread-count", headers=member_headers)
    assert unread.json()["unread_count"] == 2
    all_read = await client.post(f"{NOTIFICATIONS_PATH}/read-all", headers=member_headers)
    assert all_read.status_code == 200
    assert all_read.json()["updated_count"] == 2
    unread = await client.get(f"{NOTIFICATIONS_PATH}/unread-count", headers=member_headers)
    assert unread.json()["unread_count"] == 0

    other_headers = await login(client, other.username)
    other_list = await client.get(NOTIFICATIONS_PATH, headers=other_headers)
    assert len(other_list.json()["items"]) == 1
    assert other_list.json()["items"][0]["title"] == "他人的提醒"
    admin_headers = await login(client, admin_user.username)
    admin_list = await client.get(NOTIFICATIONS_PATH, headers=admin_headers)
    assert admin_list.status_code == 200
    assert admin_list.json()["items"] == []


async def test_scheduler_creates_due_incomplete_and_streak_events_once(
    client, app, admin_user, member_user
) -> None:
    wordbook_id = await seed_wordbook(app, owner_id=member_user.id, entries=3)
    async with app.state.session_factory() as session:
        from app.models.wordbooks import WordbookEntry

        entries = list(
            (
                await session.scalars(
                    select(WordbookEntry)
                    .where(WordbookEntry.wordbook_id == wordbook_id)
                    .order_by(WordbookEntry.sequence.asc())
                )
            ).all()
        )
        plan = DailyPlan(
            user_id=member_user.id,
            local_date=date(2026, 10, 23),
            wordbook_id=wordbook_id,
            new_word_target=3,
            study_minutes_target=30,
            snapshot_time=datetime(2026, 10, 23, 8, 0, tzinfo=UTC),
            calculation_version="test",
            status="in_progress",
        )
        session.add(plan)
        await session.flush()
        for index, entry in enumerate(entries):
            session.add(
                DailyPlanWord(
                    plan_id=plan.id,
                    entry_id=entry.id,
                    reason="new",
                    position=index,
                )
            )
        session.add(
            UserWordState(
                user_id=member_user.id,
                wordbook_id=wordbook_id,
                entry_id=entries[0].id,
                status="review",
                algorithm_version="fsrs-6.3.2",
                due_at=datetime(2026, 10, 23, 9, 0, tzinfo=UTC),
            )
        )
        session.add(
            DailyActivity(
                user_id=member_user.id,
                local_date=date(2026, 10, 22),
                active_seconds=60,
                heartbeat_count=1,
                last_heartbeat_at=datetime(2026, 10, 22, 9, 0, tzinfo=UTC),
            )
        )
        await session.commit()
        now = datetime(2026, 10, 23, 20, 0, tzinfo=ZoneInfo("Asia/Shanghai"))
        first = await enqueue_scheduled_notification_events(session, app.state.settings, now=now)
        second = await enqueue_scheduled_notification_events(session, app.state.settings, now=now)
        assert first >= 2
        assert second == 0
        await process_notification_outbox(session, app.state.settings, now=now)
        notifications = list(
            (
                await session.scalars(
                    select(Notification).where(Notification.user_id == member_user.id)
                )
            ).all()
        )
        assert {item.category for item in notifications} >= {
            "due_review",
            "today_incomplete",
            "streak_risk",
        }


async def test_ai_job_terminal_status_creates_one_notification_per_job(
    client, app, member_user
) -> None:
    member_headers = await login(client, member_user.username)
    with fake_provider_server() as server:
        await create_provider(client, member_headers, base_url=server.base_url)
        success = await client.post(
            "/api/v1/ai/jobs",
            headers={**member_headers, "Idempotency-Key": "notification-ai-success"},
            json={
                "task_type": "json_repair",
                "context": {"raw_text": "not json", "validation_errors": ["invalid"]},
            },
        )
        assert success.status_code == 202, success.text
        server.queue_json(200, {"corrected": {"ok": True}})
        await process_ai_job(
            {
                "session_factory": app.state.session_factory,
                "settings": app.state.settings,
                "redis": app.state.redis,
            },
            success.json()["job_id"],
        )

        failure = await client.post(
            "/api/v1/ai/jobs",
            headers={**member_headers, "Idempotency-Key": "notification-ai-failure"},
            json={
                "task_type": "json_repair",
                "context": {"raw_text": "not json", "validation_errors": ["invalid"]},
            },
        )
        assert failure.status_code == 202, failure.text
        for _ in range(3):
            server.queue_json(500, {"error": "temporary"})
        await process_ai_job(
            {
                "session_factory": app.state.session_factory,
                "settings": app.state.settings,
                "redis": app.state.redis,
            },
            failure.json()["job_id"],
        )

        async with app.state.session_factory() as session:
            outbox = list(
                (
                    await session.scalars(
                        select(NotificationOutbox).where(
                            NotificationOutbox.user_id == member_user.id
                        )
                    )
                ).all()
            )
            assert {item.category for item in outbox} == {"ai_completed", "ai_failed"}
            await process_notification_outbox(session, app.state.settings)
            rows = list(
                (
                    await session.scalars(
                        select(Notification).where(
                            Notification.user_id == member_user.id,
                            Notification.category.in_(("ai_completed", "ai_failed")),
                        )
                    )
                ).all()
            )
            assert len(rows) == 2
            assert all(item.status == "sent" for item in rows)


async def test_category_switch_daily_limit_and_same_category_merge(
    client, app, member_user
) -> None:
    headers = await login(client, member_user.username)
    updated = await client.put(
        PREFERENCES_PATH,
        headers=headers,
        json={
            "categories": {
                "due_review": False,
                "today_incomplete": True,
                "streak_risk": True,
                "ai_completed": True,
                "ai_failed": True,
                "plan_adjusted": True,
                "ai_action": True,
            },
            "dnd_start": "22:00",
            "dnd_end": "08:00",
            "daily_limit": 1,
            "timezone": "Asia/Shanghai",
        },
    )
    assert updated.status_code == 200, updated.text
    now = datetime(2026, 10, 23, 12, 0, tzinfo=ZoneInfo("Asia/Shanghai"))
    async with app.state.session_factory() as session:
        for category, key in (
            ("due_review", "limit:due"),
            ("today_incomplete", "limit:today"),
            ("streak_risk", "limit:streak"),
            ("today_incomplete", "limit:today:second"),
        ):
            await enqueue_notification_event(
                session,
                user_id=member_user.id,
                category=category,
                dedupe_key=key,
                event_type=f"test.{category}",
                payload={"title": category, "body": "安全正文"},
                available_at=now,
            )
        await session.commit()
        await process_notification_outbox(session, app.state.settings, now=now)
        rows = list(
            (
                await session.scalars(
                    select(Notification)
                    .where(Notification.user_id == member_user.id)
                    .order_by(Notification.created_at.asc())
                )
            ).all()
        )
        by_key = {row.dedupe_key: row for row in rows}
        assert by_key["limit:due"].status == "suppressed"
        assert by_key["limit:due"].suppressed_reason == "category_disabled"
        assert by_key["limit:today"].status == "sent"
        assert by_key["limit:streak"].status == "suppressed"
        assert by_key["limit:streak"].suppressed_reason == "daily_limit"
        assert by_key["limit:today:second"].status == "merged"
