"""Memory training, FSRS queue rules, plan snapshots, heartbeats, and privacy."""

from __future__ import annotations

import asyncio
from datetime import date, datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy import delete, func, select, text, update

from app.core.security import hash_password
from app.models.identity import AuditLog, User, UserProfile
from app.models.learning import (
    DailyActivity,
    DailyPlan,
    DailyPlanWord,
    LearningHeartbeat,
    MemoryEvent,
    MemorySession,
    MemorySessionItem,
    MistakeFlag,
    UserWordState,
)
from app.models.wordbooks import Wordbook, WordbookActivation, WordbookEntry
from app.schemas.wordbooks import DeleteWordbookRequest
from app.services.auth import utcnow
from app.services.wordbook_jobs import process_wordbook_job
from app.services.wordbooks import start_delete_wordbook
from tests.conftest import TEST_USER_PASSWORD
from tests.learning_support import (
    ENSURE_PATH,
    EVENTS_PATH,
    HEARTBEAT_PATH,
    MEMORY_CONFIG_PATH,
    MISTAKES_PATH,
    PROFILE_PATH,
    SESSIONS_PATH,
    STATS_PATH,
    TODAY_PATH,
    WORDBOOKS_PATH,
    activate,
    entry_facts,
    login,
    seed_wordbook,
    session_headers,
)


def _job_context(app, factory) -> dict:
    return {
        "session_factory": factory,
        "settings": app.state.settings,
        "wordbook_storage": app.state.wordbook_storage,
    }


async def _create_isolated_actor(app) -> tuple[User, object]:
    """A user bound to the real engine so concurrency runs on separate connections."""

    factory = app.state.session_factory.__class__(
        bind=app.state.engine,
        class_=app.state.session_factory.class_,
        expire_on_commit=False,
        autoflush=False,
    )
    username = f"memory_{uuid4().hex[:12]}"
    async with factory() as session:
        user = User(
            username=username,
            username_normalized=username.lower(),
            display_name="Memory Concurrency User",
            role="member",
            status="active",
            password_hash=hash_password(TEST_USER_PASSWORD),
            must_change_password=False,
            profile=UserProfile(department="Learning", learning_group="Core"),
        )
        session.add(user)
        await session.commit()
        user_id = user.id
    async with factory() as session:
        actor = await session.get(User, user_id)
        assert actor is not None
    return actor, factory


async def _cleanup_actor(factory, actor_id: UUID) -> None:
    async with factory() as session:
        await session.execute(delete(AuditLog).where(AuditLog.actor_id == actor_id))
        await session.execute(delete(User).where(User.id == actor_id))
        await session.commit()


async def _submit(client, headers, session_id, item_id, action, *, key, answer=None):
    response = await client.post(
        f"{SESSIONS_PATH}/{session_id}/events",
        headers=session_headers(headers, key),
        json={"item_id": item_id, "action": action, "answer": answer, "duration_ms": 1500},
    )
    assert response.status_code == 200, response.text
    return response.json()


async def _first_plan_word(app, user_id, wordbook_id) -> tuple[UUID, UUID]:
    async with app.state.session_factory() as session:
        plan = await session.scalar(
            select(DailyPlan).where(
                DailyPlan.user_id == user_id, DailyPlan.wordbook_id == UUID(str(wordbook_id))
            )
        )
        assert plan is not None
        plan_word = await session.scalar(
            select(DailyPlanWord)
            .where(DailyPlanWord.plan_id == plan.id)
            .order_by(DailyPlanWord.position)
        )
        assert plan_word is not None
        return plan_word.entry_id, plan_word.id


async def _ensure_plan(session, actor, settings):
    from app.services.learning import ensure_daily_plan

    return await ensure_daily_plan(session, actor, settings=settings)


async def _heartbeat(session, actor, settings, key):
    from app.services.learning import record_heartbeat

    return await record_heartbeat(session, actor, settings=settings, idempotency_key=key)


async def test_new_word_needs_two_goods_with_a_four_card_gap(app, client, member_user) -> None:
    headers = await login(client, member_user.username)
    wordbook_id = await seed_wordbook(app, owner_id=member_user.id, entries=8)
    await activate(app, user_id=member_user.id, wordbook_id=wordbook_id)
    await client.get(TODAY_PATH, headers=headers)

    created = await client.post(SESSIONS_PATH, headers=headers, json={"module": "flashcard"})
    assert created.status_code == 201, created.text
    body = created.json()
    session_id = body["session_id"]
    assert body["items_total"] >= 4
    first = body["next_item"]
    assert first["position"] == 0
    assert "fsrs_card" not in body
    assert "due_at" not in first

    first_good = await _submit(
        client, headers, session_id, first["item_id"], "good", key="mem-good-1"
    )
    assert first_good["rating"] == "good"
    assert first_good["item_completed"] is False
    assert first_good["session"]["next_item"]["item_id"] != first["item_id"]

    async with app.state.session_factory() as session:
        item = await session.scalar(
            select(MemorySessionItem).where(MemorySessionItem.id == UUID(first["item_id"]))
        )
        assert item is not None
        assert item.good_count == 1
        assert item.relearn_count == 1
        assert item.position >= first["position"] + 4
        state = await session.scalar(
            select(UserWordState).where(UserWordState.id == item.word_state_id)
        )
        assert state is not None
        assert state.status in {"learning", "review"}
        assert state.review_count == 1
        assert state.algorithm_version == "fsrs-6.3.2"
        first_card = dict(state.fsrs_card or {})

    resumed = await client.post(SESSIONS_PATH, headers=headers, json={"module": "flashcard"})
    assert resumed.status_code == 201, resumed.text
    assert resumed.json()["session_id"] == session_id
    assert resumed.json()["next_item"]["position"] == first_good["session"]["next_item"]["position"]
    fetched = await client.get(f"{SESSIONS_PATH}/{session_id}", headers=headers)
    assert fetched.status_code == 200
    assert fetched.json()["session_id"] == session_id

    again = await _submit(client, headers, session_id, first["item_id"], "again", key="mem-again-1")
    assert again["rating"] == "again"
    assert again["item_completed"] is False
    async with app.state.session_factory() as session:
        item = await session.scalar(
            select(MemorySessionItem).where(MemorySessionItem.id == UUID(first["item_id"]))
        )
        assert item is not None
        assert item.good_count == 1
        assert item.again_count == 1
        assert item.relearn_count >= 2
        state = await session.scalar(
            select(UserWordState).where(UserWordState.id == item.word_state_id)
        )
        assert state is not None
        assert state.status == "relearning"
        assert state.lapse_count == 1
        assert dict(state.fsrs_card or {}) != first_card
        assert state.due_at is not None
        assert state.due_at > utcnow()
    second_good = await _submit(
        client, headers, session_id, first["item_id"], "good", key="mem-good-2"
    )
    assert second_good["item_completed"] is True

    refreshed = await client.get(TODAY_PATH, headers=headers)
    assert refreshed.status_code == 200
    assert refreshed.json()["new_words"]["completed"] >= 1


async def test_wordbook_switch_keeps_plan_session_items_and_states_consistent(
    app, client, member_user
) -> None:
    headers = await login(client, member_user.username)
    primary_id = await seed_wordbook(app, owner_id=member_user.id, entries=8, prefix="primary")
    small_id = await seed_wordbook(app, owner_id=member_user.id, entries=4, prefix="small")
    await activate(app, user_id=member_user.id, wordbook_id=primary_id)

    today = await client.get(TODAY_PATH, headers=headers)
    assert today.status_code == 200, today.text
    assert today.json()["wordbook_id"] == primary_id

    first = await client.post(SESSIONS_PATH, headers=headers, json={"module": "flashcard"})
    assert first.status_code == 201, first.text
    first_session_id = first.json()["session_id"]
    assert first.json()["wordbook_id"] == primary_id

    switched = await client.post(f"{WORDBOOKS_PATH}/{small_id}/activate", headers=headers)
    assert switched.status_code == 200, switched.text

    today_after_switch = await client.get(TODAY_PATH, headers=headers)
    assert today_after_switch.status_code == 200, today_after_switch.text
    assert today_after_switch.json()["wordbook_id"] == primary_id
    assert {item["entry_id"] for item in today_after_switch.json()["items"]} == {
        item["entry_id"] for item in today.json()["items"]
    }

    resumed = await client.post(SESSIONS_PATH, headers=headers, json={"module": "flashcard"})
    assert resumed.status_code == 201, resumed.text
    assert resumed.json()["session_id"] == first_session_id
    assert resumed.json()["wordbook_id"] == primary_id

    choice = await client.post(SESSIONS_PATH, headers=headers, json={"module": "choice"})
    assert choice.status_code == 201, choice.text
    assert choice.json()["wordbook_id"] == primary_id

    mismatched = await client.post(
        SESSIONS_PATH,
        headers=headers,
        json={"module": "spelling", "wordbook_id": small_id},
    )
    assert mismatched.status_code == 409
    assert mismatched.json()["code"] == "MEMORY_WORDBOOK_PLAN_MISMATCH"

    session_ids = [UUID(first_session_id), UUID(choice.json()["session_id"])]
    async with app.state.session_factory() as session:
        for session_id in session_ids:
            memory_session = await session.get(MemorySession, session_id)
            assert memory_session is not None
            assert str(memory_session.wordbook_id) == primary_id

            items = list(
                (
                    await session.scalars(
                        select(MemorySessionItem).where(MemorySessionItem.session_id == session_id)
                    )
                ).all()
            )
            assert items
            for item in items:
                entry = await session.get(WordbookEntry, item.entry_id)
                state = await session.get(UserWordState, item.word_state_id)
                assert entry is not None
                assert state is not None
                assert str(entry.wordbook_id) == primary_id
                assert str(state.wordbook_id) == primary_id
                assert state.entry_id == entry.id

        cross_book_states = await session.scalar(
            select(func.count(UserWordState.id))
            .join(WordbookEntry, WordbookEntry.id == UserWordState.entry_id)
            .where(
                UserWordState.user_id == member_user.id,
                UserWordState.wordbook_id != WordbookEntry.wordbook_id,
            )
        )
        small_states = await session.scalar(
            select(func.count(UserWordState.id)).where(
                UserWordState.user_id == member_user.id,
                UserWordState.wordbook_id == UUID(small_id),
            )
        )
    assert cross_book_states == 0
    assert small_states == 0


async def test_due_review_completes_with_one_good_and_again_relearns(
    app, client, member_user
) -> None:
    headers = await login(client, member_user.username)
    wordbook_id = await seed_wordbook(app, owner_id=member_user.id, entries=6)
    await activate(app, user_id=member_user.id, wordbook_id=wordbook_id)
    await client.get(TODAY_PATH, headers=headers)

    entry_id, plan_word_id = await _first_plan_word(app, member_user.id, wordbook_id)
    await _force_due(app, member_user.id, wordbook_id, entry_id, plan_word_id)

    created = await client.post(SESSIONS_PATH, headers=headers, json={"module": "flashcard"})
    assert created.status_code == 201, created.text
    body = created.json()
    due_item = body["next_item"]
    assert due_item["reason"] == "due"
    assert due_item["entry_id"] == str(entry_id)

    good = await _submit(
        client, headers, body["session_id"], due_item["item_id"], "good", key="due-good"
    )
    assert good["item_completed"] is True

    async with app.state.session_factory() as session:
        state = await session.scalar(
            select(UserWordState).where(
                UserWordState.user_id == member_user.id,
                UserWordState.entry_id == entry_id,
            )
        )
        assert state is not None
        assert state.status in {"learning", "review"}
        assert state.review_count == 4


async def test_choice_and_spelling_never_leak_the_answer(app, client, member_user) -> None:
    headers = await login(client, member_user.username)
    wordbook_id = await seed_wordbook(app, owner_id=member_user.id, entries=8)
    await activate(app, user_id=member_user.id, wordbook_id=wordbook_id)
    await client.get(TODAY_PATH, headers=headers)

    choice = await client.post(SESSIONS_PATH, headers=headers, json={"module": "choice"})
    assert choice.status_code == 201, choice.text
    choice_body = choice.json()
    card = choice_body["card"]
    assert card["module"] == "choice"
    assert card["option_count"] == 4
    options = card["options"]
    assert len(options) == 4
    assert len({option.casefold() for option in options}) == 4
    serialized = str(choice_body)
    for marker in ("correct_option", "answer_key", "option_ids", "'is_correct': True"):
        assert marker not in serialized

    facts = await entry_facts(app, choice_body["next_item"]["entry_id"])
    correct_option = (
        facts["definition_zh"] if card["prompt_label"] == "headword" else facts["headword"]
    )
    assert correct_option in options

    graded = await _submit(
        client,
        headers,
        choice_body["session_id"],
        choice_body["next_item"]["item_id"],
        "good",
        key="choice-answer",
        answer=correct_option,
    )
    assert graded["rating"] == "good"
    assert graded["is_correct"] is True

    spelling = await client.post(SESSIONS_PATH, headers=headers, json={"module": "spelling"})
    assert spelling.status_code == 201, spelling.text
    spelling_body = spelling.json()
    spelling_card = spelling_body["card"]
    assert spelling_card["module"] == "spelling"
    assert spelling_card["cloze"]
    headword = (await entry_facts(app, spelling_body["next_item"]["entry_id"]))["headword"]
    assert headword not in str(spelling_card)

    upper = await _submit(
        client,
        headers,
        spelling_body["session_id"],
        spelling_body["next_item"]["item_id"],
        "good",
        key="spelling-upper",
        answer=headword.upper(),
    )
    assert upper["is_correct"] is True
    assert upper["correct_answer"] == headword


async def test_event_idempotency_replays_and_rejects_conflicts(app, client, member_user) -> None:
    headers = await login(client, member_user.username)
    wordbook_id = await seed_wordbook(app, owner_id=member_user.id, entries=5)
    await activate(app, user_id=member_user.id, wordbook_id=wordbook_id)
    await client.get(TODAY_PATH, headers=headers)
    created = await client.post(SESSIONS_PATH, headers=headers, json={"module": "flashcard"})
    body = created.json()
    item_id = body["next_item"]["item_id"]

    first = await _submit(client, headers, body["session_id"], item_id, "good", key="idem-1")
    replay = await _submit(client, headers, body["session_id"], item_id, "good", key="idem-1")
    assert replay["event_id"] == first["event_id"]
    assert replay["item_completed"] == first["item_completed"]

    conflict = await client.post(
        f"{SESSIONS_PATH}/{body['session_id']}/events",
        headers=session_headers(headers, "idem-1"),
        json={"item_id": item_id, "action": "again", "duration_ms": 1000},
    )
    assert conflict.status_code == 409
    assert conflict.json()["code"] == "IDEMPOTENCY_CONFLICT"

    async with app.state.session_factory() as session:
        events = await session.scalar(
            select(func.count(MemoryEvent.id)).where(
                MemoryEvent.session_id == UUID(body["session_id"])
            )
        )
    assert events == 1

    missing_key = await client.post(
        f"{SESSIONS_PATH}/{body['session_id']}/events",
        headers=headers,
        json={"item_id": item_id, "action": "good"},
    )
    assert missing_key.status_code == 422


async def test_mastered_restore_and_suspended_exclusion(app, client, member_user) -> None:
    headers = await login(client, member_user.username)
    wordbook_id = await seed_wordbook(app, owner_id=member_user.id, entries=6)
    await activate(app, user_id=member_user.id, wordbook_id=wordbook_id)
    await client.get(TODAY_PATH, headers=headers)
    created = await client.post(SESSIONS_PATH, headers=headers, json={"module": "flashcard"})
    body = created.json()
    state_id = body["next_item"]["word_state_id"]

    mastered = await client.patch(f"/api/v1/memory/words/{state_id}/master", headers=headers)
    assert mastered.status_code == 200, mastered.text
    assert mastered.json()["status"] == "mastered"
    assert mastered.json()["mastered_at"] is not None

    restored = await client.patch(f"/api/v1/memory/words/{state_id}/restore", headers=headers)
    assert restored.status_code == 200, restored.text
    payload = restored.json()
    assert payload["status"] == "relearning"
    assert payload["mastered_at"] is None
    due_at = datetime.fromisoformat(payload["due_at"].replace("Z", "+00:00"))
    assert due_at > utcnow()

    async with app.state.session_factory() as session:
        state = await session.scalar(
            select(UserWordState).where(UserWordState.id == UUID(state_id))
        )
        assert state is not None
        entry_id = state.entry_id
        state.status = "suspended"
        state.due_at = utcnow() - timedelta(days=1)
        await session.commit()

    today = await client.get(TODAY_PATH, headers=headers)
    # The frozen snapshot keeps its rows, but no new session may hand out a suspended word.
    today = await client.get(TODAY_PATH, headers=headers)
    assert today.status_code == 200
    async with app.state.session_factory() as session:
        active = await session.scalar(
            select(MemorySession).where(
                MemorySession.user_id == member_user.id, MemorySession.module == "flashcard"
            )
        )
        assert active is not None
        active.status = "abandoned"
        await session.commit()

    fresh = await client.post(SESSIONS_PATH, headers=headers, json={"module": "flashcard"})
    assert fresh.status_code == 201, fresh.text
    async with app.state.session_factory() as session:
        handed_out = await session.scalar(
            select(func.count(MemorySessionItem.id)).where(
                MemorySessionItem.session_id == UUID(fresh.json()["session_id"]),
                MemorySessionItem.entry_id == entry_id,
            )
        )
    assert handed_out == 0


async def test_mistakes_order_priority_and_do_not_mutate_events(app, client, member_user) -> None:
    headers = await login(client, member_user.username)
    wordbook_id = await seed_wordbook(app, owner_id=member_user.id, entries=6)
    await activate(app, user_id=member_user.id, wordbook_id=wordbook_id)
    await client.get(TODAY_PATH, headers=headers)
    created = await client.post(SESSIONS_PATH, headers=headers, json={"module": "flashcard"})
    body = created.json()

    await _submit(
        client, headers, body["session_id"], body["next_item"]["item_id"], "again", key="mistake-1"
    )
    next_item = (await client.get(f"{SESSIONS_PATH}/{body['session_id']}", headers=headers)).json()[
        "next_item"
    ]
    await _submit(
        client, headers, body["session_id"], next_item["item_id"], "again", key="mistake-2"
    )

    mistakes = await client.get(MISTAKES_PATH, headers=headers)
    assert mistakes.status_code == 200, mistakes.text
    items = mistakes.json()["items"]
    assert len(items) == 2
    latest = items[0]
    assert latest["entry_id"] == next_item["entry_id"]
    assert latest["again_count"] == 1
    assert latest["is_priority"] is False

    async with app.state.session_factory() as session:
        events_before = await session.scalar(
            select(func.count(MemoryEvent.id)).where(MemoryEvent.user_id == member_user.id)
        )

    priority = await client.patch(
        f"{MISTAKES_PATH}/{latest['entry_id']}/priority",
        headers=headers,
        json={"is_priority": True},
    )
    assert priority.status_code == 200, priority.text
    assert priority.json()["is_priority"] is True

    async with app.state.session_factory() as session:
        events_after = await session.scalar(
            select(func.count(MemoryEvent.id)).where(MemoryEvent.user_id == member_user.id)
        )
        flags = await session.scalar(
            select(func.count(MistakeFlag.id)).where(MistakeFlag.user_id == member_user.id)
        )
    assert events_after == events_before
    assert flags == 2

    missing = await client.patch(
        f"{MISTAKES_PATH}/{uuid4()}/priority", headers=headers, json={"is_priority": True}
    )
    assert missing.status_code == 404


async def test_learning_data_is_scoped_to_the_caller(app, client, member_user, admin_user) -> None:
    owner_headers = await login(client, member_user.username)
    admin_headers = await login(client, admin_user.username)
    wordbook_id = await seed_wordbook(app, owner_id=member_user.id, entries=5)
    await activate(app, user_id=member_user.id, wordbook_id=wordbook_id)
    await client.get(TODAY_PATH, headers=owner_headers)
    created = await client.post(SESSIONS_PATH, headers=owner_headers, json={"module": "flashcard"})
    body = created.json()
    await _submit(
        client,
        owner_headers,
        body["session_id"],
        body["next_item"]["item_id"],
        "again",
        key="priv-1",
    )

    foreign_session = await client.get(
        f"{SESSIONS_PATH}/{body['session_id']}", headers=admin_headers
    )
    assert foreign_session.status_code == 404
    foreign_state = await client.patch(
        f"/api/v1/memory/words/{body['next_item']['word_state_id']}/master",
        headers=admin_headers,
    )
    assert foreign_state.status_code == 404

    admin_events = await client.get(EVENTS_PATH, headers=admin_headers)
    assert admin_events.status_code == 200
    assert admin_events.json()["items"] == []
    admin_mistakes = await client.get(MISTAKES_PATH, headers=admin_headers)
    assert admin_mistakes.status_code == 200
    assert admin_mistakes.json()["items"] == []
    admin_stats = await client.get(STATS_PATH, headers=admin_headers)
    assert admin_stats.status_code == 200
    assert admin_stats.json()["total_reviews"] == 0

    owner_events = await client.get(EVENTS_PATH, headers=owner_headers)
    assert owner_events.status_code == 200
    assert len(owner_events.json()["items"]) == 1


async def test_plan_filters_and_reports_extra_due_after_snapshot(app, client, member_user) -> None:
    headers = await login(client, member_user.username)
    wordbook_id = await seed_wordbook(app, owner_id=member_user.id, entries=6)
    await activate(app, user_id=member_user.id, wordbook_id=wordbook_id)
    await client.patch(PROFILE_PATH, headers=headers, json={"daily_new_words": 5})
    first = await client.get(TODAY_PATH, headers=headers)
    assert first.status_code == 200
    assert len(first.json()["items"]) == 5
    planned = {item["entry_id"] for item in first.json()["items"]}

    entry_id, _ = await _first_plan_word(app, member_user.id, wordbook_id)
    async with app.state.session_factory() as session:
        session.add(
            UserWordState(
                user_id=member_user.id,
                wordbook_id=UUID(str(wordbook_id)),
                entry_id=entry_id,
                status="suspended",
                fsrs_card={},
                algorithm_version="fsrs-6.3.2",
                due_at=utcnow() - timedelta(days=1),
            )
        )
        await session.commit()

    again = await client.post(ENSURE_PATH, headers=headers)
    assert again.status_code == 200
    assert {item["entry_id"] for item in again.json()["items"]} == planned

    async with app.state.session_factory() as session:
        candidates = list(
            (
                await session.scalars(
                    select(WordbookEntry.id)
                    .where(WordbookEntry.wordbook_id == UUID(str(wordbook_id)))
                    .order_by(WordbookEntry.sequence)
                )
            ).all()
        )
        unplanned = next(item for item in candidates if str(item) not in planned)
        session.add(
            UserWordState(
                user_id=member_user.id,
                wordbook_id=UUID(str(wordbook_id)),
                entry_id=unplanned,
                status="review",
                fsrs_card={},
                algorithm_version="fsrs-6.3.2",
                due_at=utcnow(),
            )
        )
        await session.commit()
        assert str(unplanned) not in planned

    extra = await client.get(TODAY_PATH, headers=headers)
    assert extra.status_code == 200
    assert extra.json()["extra_due_available"] is True
    assert extra.json()["extra_due_count"] == 1
    assert {item["entry_id"] for item in extra.json()["items"]} == planned


async def test_concurrent_ensure_and_heartbeats_stay_consistent(app) -> None:
    actor, factory = await _create_isolated_actor(app)
    try:
        async with factory() as session:
            book = Wordbook(
                visibility="private",
                status="ready",
                name="Concurrent plan",
                owner_id=actor.id,
                created_by=actor.id,
                book_metadata={},
            )
            session.add(book)
            await session.flush()
            for index in range(6):
                session.add(
                    WordbookEntry(
                        wordbook_id=book.id,
                        headword=f"conc{index}",
                        normalized_headword=f"conc{index}",
                        sequence=index,
                    )
                )
            session.add(WordbookActivation(user_id=actor.id, wordbook_id=book.id))
            await session.commit()

        settings = app.state.settings

        async def ensure_once():
            async with factory() as session:
                return await _ensure_plan(session, actor, settings)

        plans = await asyncio.wait_for(
            asyncio.gather(ensure_once(), ensure_once(), ensure_once()), timeout=30
        )
        assert len({plan.id for plan in plans}) == 1
        async with factory() as session:
            count = await session.scalar(
                select(func.count(DailyPlan.id)).where(DailyPlan.user_id == actor.id)
            )
            duplicates = await session.scalar(
                text(
                    "SELECT count(*) FROM (SELECT user_id, local_date FROM daily_plans"
                    " WHERE user_id = :uid GROUP BY user_id, local_date HAVING count(*) > 1) dup"
                ),
                {"uid": actor.id},
            )
        assert count == 1
        assert duplicates == 0

        async def heartbeat(key: str):
            async with factory() as session:
                return await _heartbeat(session, actor, settings, key)

        results = await asyncio.wait_for(
            asyncio.gather(heartbeat("conc-hb-1"), heartbeat("conc-hb-2")), timeout=30
        )
        async with factory() as session:
            rows = await session.scalar(
                select(func.count(LearningHeartbeat.id)).where(
                    LearningHeartbeat.user_id == actor.id
                )
            )
            activity = await session.scalar(
                select(DailyActivity).where(DailyActivity.user_id == actor.id)
            )
        credited = sum(result.credited_seconds for result in results)
        assert rows == 2
        assert activity is not None
        assert credited <= 30
        assert activity.active_seconds == credited
    finally:
        await _cleanup_actor(factory, actor.id)


async def test_heartbeat_cap_stale_window_and_daily_rollover(app, client, member_user) -> None:
    headers = await login(client, member_user.username)

    first = await client.post(
        HEARTBEAT_PATH, headers=session_headers(headers, "hb-roll-1"), json={}
    )
    assert first.status_code == 200
    assert first.json()["credited_seconds"] == 0

    async with app.state.session_factory() as session:
        activity = await session.scalar(
            select(DailyActivity).where(DailyActivity.user_id == member_user.id)
        )
        assert activity is not None
        activity.last_heartbeat_at = utcnow() - timedelta(seconds=45)
        await session.commit()

    capped = await client.post(
        HEARTBEAT_PATH, headers=session_headers(headers, "hb-roll-2"), json={}
    )
    assert capped.status_code == 200
    assert capped.json()["credited_seconds"] == 30

    async with app.state.session_factory() as session:
        activity = await session.scalar(
            select(DailyActivity).where(DailyActivity.user_id == member_user.id)
        )
        assert activity is not None
        activity.last_heartbeat_at = utcnow() - timedelta(seconds=200)
        await session.commit()

    stale = await client.post(
        HEARTBEAT_PATH, headers=session_headers(headers, "hb-roll-3"), json={}
    )
    assert stale.status_code == 200
    assert stale.json()["credited_seconds"] == 0

    yesterday = date.today() - timedelta(days=1)
    async with app.state.session_factory() as session:
        session.add(
            DailyActivity(
                user_id=member_user.id,
                local_date=yesterday,
                active_seconds=600,
                heartbeat_count=20,
            )
        )
        await session.commit()

    rollover = await client.post(
        HEARTBEAT_PATH, headers=session_headers(headers, "hb-roll-4"), json={}
    )
    assert rollover.status_code == 200
    assert rollover.json()["local_date"] != str(yesterday)

    async with app.state.session_factory() as session:
        rows = await session.scalar(
            select(func.count(DailyActivity.user_id)).where(DailyActivity.user_id == member_user.id)
        )
        yesterday_row = await session.scalar(
            select(DailyActivity).where(
                DailyActivity.user_id == member_user.id,
                DailyActivity.local_date == yesterday,
            )
        )
    assert rows == 2
    assert yesterday_row is not None and yesterday_row.active_seconds == 600

    stats = await client.get(STATS_PATH, headers=headers)
    assert stats.status_code == 200
    assert stats.json()["sources"]["heartbeat_seconds"] >= 30


async def test_memory_module_config_requires_an_enabled_module(app, client, member_user) -> None:
    headers = await login(client, member_user.username)
    current = await client.get(MEMORY_CONFIG_PATH, headers=headers)
    assert current.status_code == 200
    assert current.json()["flashcard_enabled"] is True

    disabled_all = await client.put(
        MEMORY_CONFIG_PATH,
        headers=headers,
        json={"flashcard_enabled": False, "choice_enabled": False, "spelling_enabled": False},
    )
    assert disabled_all.status_code == 422
    assert disabled_all.json()["code"] == "MEMORY_MODULE_REQUIRED"

    updated = await client.put(
        MEMORY_CONFIG_PATH,
        headers=headers,
        json={
            "flashcard_enabled": True,
            "choice_enabled": False,
            "spelling_enabled": False,
            "preferences": {"spelling_mode": "first_letter"},
        },
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["choice_enabled"] is False

    wordbook_id = await seed_wordbook(app, owner_id=member_user.id, entries=4)
    await activate(app, user_id=member_user.id, wordbook_id=wordbook_id)
    blocked = await client.post(SESSIONS_PATH, headers=headers, json={"module": "choice"})
    assert blocked.status_code == 409
    assert blocked.json()["code"] == "MEMORY_MODULE_DISABLED"


async def test_wordbook_delete_removes_learning_rows(app, client, member_user) -> None:
    headers = await login(client, member_user.username)
    wordbook_id = await seed_wordbook(app, owner_id=member_user.id, entries=5, visibility="private")
    await activate(app, user_id=member_user.id, wordbook_id=wordbook_id)
    await client.get(TODAY_PATH, headers=headers)
    created = await client.post(SESSIONS_PATH, headers=headers, json={"module": "flashcard"})
    body = created.json()
    await _submit(
        client,
        headers,
        body["session_id"],
        body["next_item"]["item_id"],
        "again",
        key="del-1",
    )

    async with app.state.session_factory() as session:
        actor = await session.get(User, member_user.id)
        assert actor is not None
        job = await start_delete_wordbook(
            session,
            actor,
            settings=app.state.settings,
            wordbook_id=UUID(str(wordbook_id)),
            payload=DeleteWordbookRequest(),
            idempotency_key=f"delete-{uuid4().hex}",
        )
        job_id = job.id

    result = await process_wordbook_job(_job_context(app, app.state.session_factory), str(job_id))
    assert result["deleted_entries"] == 5, result
    assert result["deleted_word_states"] >= 1
    assert result["deleted_sessions"] >= 1
    assert result["deleted_events"] >= 1
    assert result["deleted_plans"] >= 1

    async with app.state.session_factory() as session:
        counts = {
            "states": await session.scalar(
                select(func.count(UserWordState.id)).where(
                    UserWordState.wordbook_id == UUID(str(wordbook_id))
                )
            ),
            "sessions": await session.scalar(
                select(func.count(MemorySession.id)).where(
                    MemorySession.wordbook_id == UUID(str(wordbook_id))
                )
            ),
            "events": await session.scalar(
                select(func.count(MemoryEvent.id)).where(
                    MemoryEvent.wordbook_id == UUID(str(wordbook_id))
                )
            ),
            "plans": await session.scalar(
                select(func.count(DailyPlan.id)).where(
                    DailyPlan.wordbook_id == UUID(str(wordbook_id))
                )
            ),
            "mistakes": await session.scalar(
                select(func.count(MistakeFlag.id)).where(
                    MistakeFlag.wordbook_id == UUID(str(wordbook_id))
                )
            ),
        }
    assert counts == {
        "states": 0,
        "sessions": 0,
        "events": 0,
        "plans": 0,
        "mistakes": 0,
    }

    after = await client.get(TODAY_PATH, headers=headers)
    assert after.status_code == 409
    assert after.json()["code"] == "ACTIVE_WORDBOOK_REQUIRED"


async def _force_due(app, user_id, wordbook_id, entry_id, plan_word_id) -> None:
    """Promote one planned word into an overdue review with a real state row."""

    async with app.state.session_factory() as session:
        await session.execute(
            update(DailyPlanWord).where(DailyPlanWord.id == plan_word_id).values(reason="due")
        )
        existing = await session.scalar(
            select(UserWordState).where(
                UserWordState.user_id == user_id,
                UserWordState.entry_id == entry_id,
            )
        )
        if existing is None:
            session.add(
                UserWordState(
                    user_id=user_id,
                    wordbook_id=UUID(str(wordbook_id)),
                    entry_id=entry_id,
                    status="review",
                    fsrs_card={},
                    algorithm_version="fsrs-6.3.2",
                    due_at=utcnow() - timedelta(hours=1),
                    review_count=3,
                )
            )
        else:
            existing.status = "review"
            existing.due_at = utcnow() - timedelta(hours=1)
            existing.review_count = 3
        await session.commit()


async def test_reset_today_progress_clears_sessions_and_requeues_words(
    app, client, member_user
) -> None:
    headers = await login(client, member_user.username)
    wordbook_id = await seed_wordbook(app, owner_id=member_user.id, entries=6)
    await activate(app, user_id=member_user.id, wordbook_id=wordbook_id)
    await client.get(TODAY_PATH, headers=headers)

    entry_id, plan_word_id = await _first_plan_word(app, member_user.id, wordbook_id)
    await _force_due(app, member_user.id, wordbook_id, entry_id, plan_word_id)

    created = await client.post(SESSIONS_PATH, headers=headers, json={"module": "flashcard"})
    assert created.status_code == 201, created.text
    body = created.json()
    item = body["next_item"]
    await _submit(client, headers, body["session_id"], item["item_id"], "good", key="reset-good")

    reset = await client.post("/api/v1/memory/progress/reset", headers=headers, json={})
    assert reset.status_code == 200, reset.text
    data = reset.json()
    assert data["sessions_reset"] >= 1
    assert data["words_reset"] >= 1

    async with app.state.session_factory() as session:
        remaining = await session.scalar(
            select(func.count(MemorySession.id)).where(MemorySession.user_id == member_user.id)
        )
        assert remaining == 0
        state = await session.scalar(
            select(UserWordState).where(
                UserWordState.user_id == member_user.id,
                UserWordState.entry_id == entry_id,
            )
        )
        assert state is not None
        assert state.due_at <= utcnow()

    again = await client.post(SESSIONS_PATH, headers=headers, json={"module": "flashcard"})
    assert again.status_code == 201, again.text
    assert again.json()["next_item"]["entry_id"] == str(entry_id)

    empty = await client.post("/api/v1/memory/progress/reset", headers=headers, json={})
    assert empty.status_code == 200
    assert empty.json()["words_reset"] >= 1


async def test_an_active_session_from_an_earlier_day_is_not_resumed(
    app, client, member_user
) -> None:
    headers = await login(client, member_user.username)
    wordbook_id = await seed_wordbook(app, owner_id=member_user.id, entries=6)
    await activate(app, user_id=member_user.id, wordbook_id=wordbook_id)
    await client.get(TODAY_PATH, headers=headers)

    entry_id, plan_word_id = await _first_plan_word(app, member_user.id, wordbook_id)
    await _force_due(app, member_user.id, wordbook_id, entry_id, plan_word_id)

    created = await client.post(SESSIONS_PATH, headers=headers, json={"module": "choice"})
    assert created.status_code == 201, created.text
    old_id = UUID(created.json()["session_id"])

    async with app.state.session_factory() as session:
        old = await session.get(MemorySession, old_id)
        assert old is not None
        old.local_date = old.local_date - timedelta(days=3)
        await session.commit()

    again = await client.post(SESSIONS_PATH, headers=headers, json={"module": "choice"})
    assert again.status_code == 201, again.text
    assert UUID(again.json()["session_id"]) != old_id
    assert again.json()["next_item"] is not None

    async with app.state.session_factory() as session:
        old = await session.get(MemorySession, old_id)
        assert old is not None
        assert old.status == "abandoned"

    # Reset also clears active sessions left open on earlier days.
    async with app.state.session_factory() as session:
        current = await session.get(MemorySession, UUID(again.json()["session_id"]))
        assert current is not None
        current.local_date = current.local_date - timedelta(days=2)
        await session.commit()

    reset = await client.post("/api/v1/memory/progress/reset", headers=headers, json={})
    assert reset.status_code == 200, reset.text
    async with app.state.session_factory() as session:
        stale = await session.get(MemorySession, UUID(again.json()["session_id"]))
        assert stale is None
