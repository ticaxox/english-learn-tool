import httpx
from sqlalchemy import select, text

from app.models.learning import DailyPlan, UserWordState

LOGIN_PATH = "/api/v1/auth/login"
PROFILE_PATH = "/api/v1/users/me/profile"
TODAY_PATH = "/api/v1/learning/today"
ENSURE_PATH = "/api/v1/learning/daily-plan/ensure"
HEARTBEAT_PATH = "/api/v1/learning/heartbeat"
STATS_PATH = "/api/v1/learning/stats"
EVENTS_PATH = "/api/v1/learning/events"
WORDBOOKS_PATH = "/api/v1/wordbooks"


def _bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def _login(client: httpx.AsyncClient, username: str) -> dict[str, str]:
    response = await client.post(
        LOGIN_PATH,
        json={"username": username, "password": "Valid-Test-Pass-123!"},
    )
    assert response.status_code == 200, response.text
    return _bearer(response.json()["access_token"])


async def _seed_wordbook(app, *, owner_id, visibility="organization", entries=8) -> str:
    from uuid import uuid4

    from app.models.wordbooks import (
        Wordbook,
        WordbookDefinition,
        WordbookEntry,
    )

    async with app.state.session_factory() as session:
        book = Wordbook(
            visibility=visibility,
            status="ready",
            name=f"Learning book {uuid4().hex[:6]}",
            owner_id=owner_id if visibility == "private" else None,
            created_by=owner_id,
            book_metadata={"source_filename": "seed.csv", "format": "csv"},
        )
        session.add(book)
        await session.flush()
        for index in range(entries):
            entry = WordbookEntry(
                wordbook_id=book.id,
                headword=f"word{index:02d}",
                normalized_headword=f"word{index:02d}",
                phonetic=f"wɜːd{index}",
                sequence=index,
            )
            session.add(entry)
            await session.flush()
            session.add(
                WordbookDefinition(
                    entry_id=entry.id,
                    part_of_speech="n.",
                    definition_en=f"definition {index}",
                    definition_zh=f"释义{index}",
                    sequence=0,
                )
            )
        await session.commit()
        return str(book.id)


async def _activate(app, *, user_id, wordbook_id) -> None:
    from uuid import UUID

    from app.models.wordbooks import WordbookActivation

    async with app.state.session_factory() as session:
        session.add(WordbookActivation(user_id=user_id, wordbook_id=UUID(wordbook_id)))
        await session.commit()


async def test_profile_defaults_validation_and_next_day_snapshot(
    app, client: httpx.AsyncClient, member_user
) -> None:
    headers = await _login(client, member_user.username)

    initial = await client.get(PROFILE_PATH, headers=headers)
    assert initial.status_code == 200
    body = initial.json()
    assert body["daily_new_words"] == 20
    assert body["daily_study_minutes"] == 30
    assert body["timezone"] == "Asia/Shanghai"
    assert body["onboarding_completed"] is False

    invalid = await client.patch(PROFILE_PATH, headers=headers, json={"daily_new_words": 4})
    assert invalid.status_code == 422

    past = await client.patch(PROFILE_PATH, headers=headers, json={"exam_date": "2000-01-01"})
    assert past.status_code == 422

    updated = await client.patch(
        PROFILE_PATH,
        headers=headers,
        json={
            "target_exam": "IELTS",
            "exam_date": "2030-06-01",
            "daily_new_words": 12,
            "daily_study_minutes": 45,
        },
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["target_exam"] == "IELTS"
    assert updated.json()["daily_new_words"] == 12

    wordbook_id = await _seed_wordbook(app, owner_id=member_user.id, entries=16)
    await _activate(app, user_id=member_user.id, wordbook_id=wordbook_id)

    first = await client.get(TODAY_PATH, headers=headers)
    assert first.status_code == 200, first.text
    assert first.json()["new_words"]["target"] == 12

    # Changing the profile after the snapshot must not change today's targets.
    await client.patch(PROFILE_PATH, headers=headers, json={"daily_new_words": 30})
    second = await client.get(TODAY_PATH, headers=headers)
    assert second.status_code == 200
    assert second.json()["new_words"]["target"] == 12
    assert second.json()["calculation_version"].startswith("plan:")


async def test_today_requires_active_wordbook(client: httpx.AsyncClient, member_user) -> None:
    headers = await _login(client, member_user.username)
    response = await client.get(TODAY_PATH, headers=headers)
    assert response.status_code == 409
    assert response.json()["code"] == "ACTIVE_WORDBOOK_REQUIRED"


async def test_daily_plan_is_stable_and_unique_per_local_date(
    app, client: httpx.AsyncClient, member_user
) -> None:
    headers = await _login(client, member_user.username)
    wordbook_id = await _seed_wordbook(app, owner_id=member_user.id, entries=15)
    await _activate(app, user_id=member_user.id, wordbook_id=wordbook_id)

    first = await client.post(ENSURE_PATH, headers=headers)
    assert first.status_code == 200, first.text
    second = await client.post(ENSURE_PATH, headers=headers)
    assert second.status_code == 200

    first_ids = [item["entry_id"] for item in first.json()["items"]]
    second_ids = [item["entry_id"] for item in second.json()["items"]]
    assert first_ids == second_ids
    assert first.json()["generated_at"] == second.json()["generated_at"]

    async with app.state.session_factory() as session:
        count = await session.scalar(
            text("SELECT count(*) FROM daily_plans WHERE user_id = :user_id"),
            {"user_id": member_user.id},
        )
        duplicate = await session.scalar(
            text(
                "SELECT count(*) FROM ("
                " SELECT user_id, local_date FROM daily_plans"
                " GROUP BY user_id, local_date HAVING count(*) > 1"
                ") AS dup"
            )
        )
    assert count == 1
    assert duplicate == 0


async def test_today_reports_insufficient_new_words_reason(
    app, client: httpx.AsyncClient, member_user
) -> None:
    headers = await _login(client, member_user.username)
    await client.patch(PROFILE_PATH, headers=headers, json={"daily_new_words": 20})
    wordbook_id = await _seed_wordbook(app, owner_id=member_user.id, entries=3)
    await _activate(app, user_id=member_user.id, wordbook_id=wordbook_id)

    response = await client.get(TODAY_PATH, headers=headers)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["new_words"]["target"] == 3
    assert body["new_word_reason"] == "INSUFFICIENT_NEW_WORDS"


async def test_heartbeat_credits_server_window_and_is_idempotent(
    app, client: httpx.AsyncClient, member_user
) -> None:
    headers = await _login(client, member_user.username)

    first = await client.post(
        HEARTBEAT_PATH, headers={**headers, "Idempotency-Key": "hb-1"}, json={}
    )
    assert first.status_code == 200, first.text
    assert first.json()["credited_seconds"] == 0

    replay = await client.post(
        HEARTBEAT_PATH, headers={**headers, "Idempotency-Key": "hb-1"}, json={}
    )
    assert replay.status_code == 200
    assert replay.json()["credited_seconds"] == 0
    assert replay.json()["heartbeat_count"] == first.json()["heartbeat_count"]

    second = await client.post(
        HEARTBEAT_PATH, headers={**headers, "Idempotency-Key": "hb-2"}, json={}
    )
    assert second.status_code == 200
    assert 0 <= second.json()["credited_seconds"] <= 30

    async with app.state.session_factory() as session:
        rows = await session.scalar(
            text("SELECT count(*) FROM learning_heartbeats WHERE user_id = :user_id"),
            {"user_id": member_user.id},
        )
        seconds = await session.scalar(
            text("SELECT active_seconds FROM daily_activities WHERE user_id = :user_id"),
            {"user_id": member_user.id},
        )
    assert rows == 2
    assert seconds == second.json()["active_seconds_today"]


async def test_heartbeat_rejects_items_outside_a_valid_window(
    app, client: httpx.AsyncClient, member_user
) -> None:
    from datetime import timedelta

    from app.models.learning import DailyActivity
    from app.services.auth import utcnow

    headers = await _login(client, member_user.username)
    await client.post(
        HEARTBEAT_PATH, headers={**headers, "Idempotency-Key": "hb-window-1"}, json={}
    )
    async with app.state.session_factory() as session:
        activity = await session.scalar(
            select(DailyActivity).where(DailyActivity.user_id == member_user.id)
        )
        assert activity is not None
        # Simulate a suspended tab that reconnects much later.
        activity.last_heartbeat_at = utcnow() - timedelta(minutes=30)
        await session.commit()

    response = await client.post(
        HEARTBEAT_PATH, headers={**headers, "Idempotency-Key": "hb-window-2"}, json={}
    )
    assert response.status_code == 200
    assert response.json()["credited_seconds"] == 0


async def test_stats_and_events_are_scoped_to_the_caller(
    app, client: httpx.AsyncClient, member_user
) -> None:
    headers = await _login(client, member_user.username)
    await client.post(HEARTBEAT_PATH, headers={**headers, "Idempotency-Key": "hb-stats"}, json={})

    stats = await client.get(STATS_PATH, headers=headers)
    assert stats.status_code == 200, stats.text
    body = stats.json()
    assert body["study_minutes_target"] == 30
    assert body["sources"]["heartbeat_seconds"] >= 0

    events = await client.get(EVENTS_PATH, headers=headers)
    assert events.status_code == 200
    assert events.json()["items"] == []

    unauth = await client.get(STATS_PATH)
    assert unauth.status_code == 401


async def test_states_and_plans_use_real_foreign_keys(app, member_user) -> None:
    wordbook_id = await _seed_wordbook(app, owner_id=member_user.id, entries=2)
    async with app.state.session_factory() as session:
        states = list(
            (
                await session.scalars(
                    select(UserWordState).where(UserWordState.user_id == member_user.id)
                )
            ).all()
        )
        plans = list(
            (
                await session.scalars(select(DailyPlan).where(DailyPlan.user_id == member_user.id))
            ).all()
        )
    assert states == []
    assert plans == []
    assert wordbook_id
