from __future__ import annotations

from zoneinfo import ZoneInfo

from sqlalchemy import select

from app.models.challenge import DailyChallengePlan
from app.services.auth import utcnow
from app.workers.scheduler import challenge_schedule_tick
from tests.ai_support import create_provider, fake_provider_server, login
from tests.learning_support import PROFILE_PATH, activate, seed_wordbook


async def test_scheduled_map_time_generates_today_plan(app, client, member_user) -> None:
    headers = await login(client, member_user.username)
    wordbook_id = await seed_wordbook(app, owner_id=member_user.id, entries=8)
    await activate(app, user_id=member_user.id, wordbook_id=wordbook_id)

    settings = app.state.settings
    current = utcnow().astimezone(ZoneInfo(settings.app_timezone)).strftime("%H:%M")
    patched = await client.patch(
        PROFILE_PATH,
        headers=headers,
        json={"target_exam": "CET4", "challenge_generation_time": current},
    )
    assert patched.status_code == 200, patched.text
    assert patched.json()["challenge_generation_time"] == current

    with fake_provider_server() as server:
        await create_provider(client, headers, base_url=server.base_url)
        await challenge_schedule_tick(
            {
                "session_factory": app.state.session_factory,
                "settings": settings,
                "redis": app.state.arq,
            }
        )

    async with app.state.session_factory() as session:
        plan = await session.scalar(
            select(DailyChallengePlan).where(DailyChallengePlan.user_id == member_user.id)
        )
        assert plan is not None
        assert plan.status == "generating"
        assert plan.ai_job_id is not None


async def test_invalid_map_time_is_rejected(client, member_user) -> None:
    headers = await login(client, member_user.username)
    rejected = await client.patch(
        PROFILE_PATH, headers=headers, json={"challenge_generation_time": "25:99"}
    )
    assert rejected.status_code == 422
