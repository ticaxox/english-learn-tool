from __future__ import annotations

from uuid import uuid4

from sqlalchemy import select

from app.models.gamification import UserGameStats, XpEvent
from app.services.gamification import AWARDS, level_for_xp, title_for_level, xp_for_level
from tests.ai_support import create_provider, fake_provider_server, login
from tests.learning_support import activate, seed_wordbook

PROGRESS_PATH = "/api/v1/me/progress"


async def test_level_curve_is_monotonic_and_titles_progress() -> None:
    for level in range(1, 40):
        assert xp_for_level(level + 1) > xp_for_level(level)
        assert level_for_xp(xp_for_level(level)) == level
    assert title_for_level(1) == "点灯人"
    assert title_for_level(6) == "挑灯人"
    assert title_for_level(40) == "长明者"


async def test_fresh_account_reads_zero_progress_with_three_quests(client, member_user) -> None:
    headers = await login(client, member_user.username)
    response = await client.get(PROGRESS_PATH, headers=headers)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["xp"] == 0
    assert body["crumbs"] == 0
    assert body["level"]["level"] == 1
    assert body["streak"] == 0
    assert [quest["key"] for quest in body["quests"]] == [
        "review_due",
        "practice_one",
        "challenge_done",
    ]
    assert all(quest["completed"] is False for quest in body["quests"])


async def test_submitting_practice_awards_once_and_completes_the_quest(
    client, app, member_user
) -> None:
    from tests.test_practice_api import _generate, _questions

    headers = await login(client, member_user.username)
    wordbook_id = await seed_wordbook(app, owner_id=member_user.id, entries=8)
    await activate(app, user_id=member_user.id, wordbook_id=wordbook_id)
    with fake_provider_server() as server:
        await create_provider(client, headers, base_url=server.base_url)
        fill = await _generate(app, client, headers, server, "fill_blank", 3)
        questions = await _questions(app, fill["id"])
        payload = {
            "answers": [{"question_id": str(question.id), "answer": "a"} for question in questions]
        }
        submitted = await client.post(
            f"/api/v1/practice/sessions/{fill['id']}/submit",
            headers={**headers, "Idempotency-Key": f"grade-{uuid4().hex}"},
            json=payload,
        )
        assert submitted.status_code == 202, submitted.text

    progress = (await client.get(PROGRESS_PATH, headers=headers)).json()
    assert progress["xp"] > 0
    assert progress["crumbs"] > 0
    assert progress["streak"] == 1
    practice_quest = next(q for q in progress["quests"] if q["key"] == "practice_one")
    assert practice_quest["completed"] is True

    async with app.state.session_factory() as session:
        events = list(
            (
                await session.scalars(
                    select(XpEvent).where(
                        XpEvent.user_id == member_user.id, XpEvent.source_type == "practice"
                    )
                )
            ).all()
        )
        stats = await session.get(UserGameStats, member_user.id)
    assert len(events) == 1
    assert events[0].xp == AWARDS["practice"][0] * 3
    assert stats is not None and stats.xp >= events[0].xp


async def test_weekly_marks_only_days_with_activity(client, app, member_user) -> None:
    from tests.test_practice_api import _generate, _questions

    headers = await login(client, member_user.username)
    wordbook_id = await seed_wordbook(app, owner_id=member_user.id, entries=8)
    await activate(app, user_id=member_user.id, wordbook_id=wordbook_id)
    with fake_provider_server() as server:
        await create_provider(client, headers, base_url=server.base_url)
        fill = await _generate(app, client, headers, server, "fill_blank", 3)
        questions = await _questions(app, fill["id"])
        await client.post(
            f"/api/v1/practice/sessions/{fill['id']}/submit",
            headers={**headers, "Idempotency-Key": f"weekly-{uuid4().hex}"},
            json={"answers": [{"question_id": str(q.id), "answer": "a"} for q in questions]},
        )

    weekly = await client.get(f"{PROGRESS_PATH}/weekly", headers=headers)
    assert weekly.status_code == 200, weekly.text
    body = weekly.json()
    assert len(body["days"]) == 7
    assert body["active_days"] >= 1
    assert body["days"][-1]["active"] is True
    assert body["xp"] > 0
