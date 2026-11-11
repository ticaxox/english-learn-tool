from __future__ import annotations

from uuid import uuid4

from tests.ai_support import create_provider, fake_provider_server, login
from tests.learning_support import activate, seed_wordbook

REGISTER_PATH = "/api/v1/auth/register"
PROGRESS_PATH = "/api/v1/me/progress"
MEMORY_PATH = "/api/v1/memory/config"


async def test_registration_creates_a_member_and_signs_in(client) -> None:
    username = f"newbie_{uuid4().hex[:8]}"
    registered = await client.post(
        REGISTER_PATH, json={"username": username, "password": "Strong-Pass-2026!"}
    )
    assert registered.status_code == 201, registered.text
    body = registered.json()
    assert body["user"]["username"] == username
    assert body["user"]["role"] == "member"
    assert body["user"]["must_change_password"] is False
    assert body["access_token"]

    # The same credentials work on a normal login.
    again = await client.post(
        "/api/v1/auth/login", json={"username": username, "password": "Strong-Pass-2026!"}
    )
    assert again.status_code == 200, again.text
    headers = {"Authorization": f"Bearer {again.json()['access_token']}"}
    assert (await client.get("/api/v1/auth/me", headers=headers)).status_code == 200


async def test_registration_rejects_duplicates_and_weak_passwords(client, member_user) -> None:
    duplicate = await client.post(
        REGISTER_PATH,
        json={"username": member_user.username, "password": "Strong-Pass-2026!"},
    )
    assert duplicate.status_code == 409
    assert duplicate.json()["code"] == "USERNAME_TAKEN"

    weak = await client.post(
        REGISTER_PATH,
        json={"username": f"weak_{uuid4().hex[:6]}", "password": "short"},
    )
    assert weak.status_code == 422


async def test_gaokao_is_an_allowed_difficulty(client, member_user) -> None:
    headers = await login(client, member_user.username)
    with fake_provider_server() as server:
        await create_provider(client, headers, base_url=server.base_url)
        response = await client.post(
            "/api/v1/practice/sessions",
            headers={**headers, "Idempotency-Key": f"gaokao-{uuid4().hex}"},
            json={
                "practice_type": "fill_blank",
                "source": "difficulty",
                "count": 3,
                "difficulty": "GAOKAO",
            },
        )
    assert response.status_code == 202, response.text


async def test_translation_direction_reaches_the_generation_context(
    client, app, member_user
) -> None:
    from uuid import UUID

    from app.models.ai import AiJob
    from app.models.practice import PracticeSession

    headers = await login(client, member_user.username)
    wordbook_id = await seed_wordbook(app, owner_id=member_user.id, entries=8)
    await activate(app, user_id=member_user.id, wordbook_id=wordbook_id)
    with fake_provider_server() as server:
        await create_provider(client, headers, base_url=server.base_url)
        created = await client.post(
            "/api/v1/practice/sessions",
            headers={**headers, "Idempotency-Key": f"dir-{uuid4().hex}"},
            json={
                "practice_type": "translation",
                "source": "whole_book",
                "count": 3,
                "translation_direction": "zh_to_en",
            },
        )
        assert created.status_code == 202, created.text
        async with app.state.session_factory() as session:
            practice = await session.get(PracticeSession, UUID(created.json()["id"]))
            assert practice is not None and practice.ai_job_id is not None
            job = await session.get(AiJob, practice.ai_job_id)
    assert job.input_context["translation_direction"] == "zh_to_en"
    assert created.json()["translation_direction"] == "zh_to_en"


async def test_writing_target_words_reaches_the_generation_context(
    client, app, member_user
) -> None:
    from uuid import UUID

    from app.models.ai import AiJob
    from app.models.practice import PracticeSession

    headers = await login(client, member_user.username)
    wordbook_id = await seed_wordbook(app, owner_id=member_user.id, entries=8)
    await activate(app, user_id=member_user.id, wordbook_id=wordbook_id)
    with fake_provider_server() as server:
        await create_provider(client, headers, base_url=server.base_url)
        created = await client.post(
            "/api/v1/practice/sessions",
            headers={**headers, "Idempotency-Key": f"words-{uuid4().hex}"},
            json={
                "practice_type": "writing",
                "source": "whole_book",
                "count": 1,
                "writing_target_words": 150,
            },
        )
        assert created.status_code == 202, created.text
        async with app.state.session_factory() as session:
            practice = await session.get(PracticeSession, UUID(created.json()["id"]))
            assert practice is not None and practice.ai_job_id is not None
            job = await session.get(AiJob, practice.ai_job_id)
    assert job.input_context["writing_target_words"] == 150


async def test_direction_is_rejected_for_other_practice_types(client, member_user) -> None:
    headers = await login(client, member_user.username)
    rejected = await client.post(
        "/api/v1/practice/sessions",
        headers={**headers, "Idempotency-Key": f"bad-dir-{uuid4().hex}"},
        json={
            "practice_type": "fill_blank",
            "source": "whole_book",
            "count": 3,
            "translation_direction": "en_to_zh",
        },
    )
    assert rejected.status_code == 422


async def test_memory_config_keeps_the_prompt_sides(client, member_user) -> None:
    headers = await login(client, member_user.username)
    saved = await client.put(
        MEMORY_PATH,
        headers=headers,
        json={
            "flashcard_enabled": True,
            "choice_enabled": True,
            "spelling_enabled": True,
            "preferences": {
                "flashcard_prompt_types": ["headword", "definition"],
                "choice_prompt_types": ["phonetic"],
            },
        },
    )
    assert saved.status_code == 200, saved.text
    loaded = (await client.get(MEMORY_PATH, headers=headers)).json()
    assert loaded["preferences"]["flashcard_prompt_types"] == ["headword", "definition"]
    assert loaded["preferences"]["choice_prompt_types"] == ["phonetic"]


async def test_badges_unlock_from_real_activity(client, app, member_user) -> None:
    from tests.test_practice_api import _generate, _questions

    headers = await login(client, member_user.username)
    wordbook_id = await seed_wordbook(app, owner_id=member_user.id, entries=8)
    await activate(app, user_id=member_user.id, wordbook_id=wordbook_id)

    fresh = (await client.get(f"{PROGRESS_PATH}/badges", headers=headers)).json()["items"]
    assert fresh and all(item["unlocked"] is False for item in fresh)

    with fake_provider_server() as server:
        await create_provider(client, headers, base_url=server.base_url)
        fill = await _generate(app, client, headers, server, "fill_blank", 3)
        questions = await _questions(app, fill["id"])
        await client.post(
            f"/api/v1/practice/sessions/{fill['id']}/submit",
            headers={**headers, "Idempotency-Key": f"badge-{uuid4().hex}"},
            json={"answers": [{"question_id": str(q.id), "answer": "a"} for q in questions]},
        )
        await client.get(PROGRESS_PATH, headers=headers)

    listed = (await client.get(f"{PROGRESS_PATH}/badges", headers=headers)).json()["items"]
    badges = {item["key"]: item for item in listed}
    assert badges["first_lesson"]["unlocked"] is True
    # Every badge in the catalogue is offered, and the wall only grows.
    assert len(listed) >= 23
    assert "streak_14" in badges
    assert "night_owl" in badges
    assert badges["streak_3"]["unlocked"] is False


async def test_direction_request_skips_the_pre_generated_pool(client, app, member_user) -> None:
    from uuid import UUID

    from app.models.practice import PracticePoolItem, PracticeSession

    headers = await login(client, member_user.username)
    wordbook_id = await seed_wordbook(app, owner_id=member_user.id, entries=8)
    await activate(app, user_id=member_user.id, wordbook_id=wordbook_id)

    # Seed a claimable pool row directly; the generation job is not the subject here.
    async with app.state.session_factory() as session:
        pool_session = PracticeSession(
            user_id=member_user.id,
            practice_type="translation",
            source="whole_book",
            wordbook_id=UUID(wordbook_id),
            question_count=3,
            status="ready",
            generation_number=1,
            source_context={"practice_type": "translation", "count": 3, "pre_generated": True},
            idempotency_key=f"pool-seed-{uuid4().hex}",
            request_hash="0" * 64,
            is_pool=True,
        )
        session.add(pool_session)
        await session.flush()
        session.add(
            PracticePoolItem(
                user_id=member_user.id,
                practice_type="translation",
                question_count=3,
                session_id=pool_session.id,
            )
        )
        await session.commit()
        seeded_id = pool_session.id

    with fake_provider_server() as server:
        await create_provider(client, headers, base_url=server.base_url)
        created = await client.post(
            "/api/v1/practice/sessions",
            headers={**headers, "Idempotency-Key": f"pool-skip-{uuid4().hex}"},
            json={
                "practice_type": "translation",
                "source": "whole_book",
                "count": 3,
                "translation_direction": "zh_to_en",
            },
        )
    assert created.status_code == 202, created.text
    assert created.json()["id"] != str(seeded_id)
    assert created.json()["translation_direction"] == "zh_to_en"
