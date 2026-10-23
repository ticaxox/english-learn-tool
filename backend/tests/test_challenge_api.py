from __future__ import annotations

from datetime import timedelta
from uuid import UUID

from sqlalchemy import select

from app.models.challenge import DailyChallengePlan
from app.models.learning import DailyPlan, DailyPlanWord
from app.models.practice import PracticeSession
from app.models.wordbooks import Wordbook, WordbookEntry
from app.services.ai_jobs import process_ai_job
from app.services.auth import utcnow
from app.services.learning import local_date_for
from tests.ai_support import (
    create_provider,
    fake_provider_server,
    login,
    practice_output,
)


def challenge_output(entry_ids: list[str]) -> dict:
    return {
        "version": "challenge-plan-v1",
        "title": "今日闯关",
        "summary": "先复习，再学习，最后完成挑战。",
        "nodes": [
            {
                "id": "review-1",
                "node_type": "REVIEW",
                "title": "复习回廊",
                "description": "复习到期单词。",
                "estimated_minutes": 8,
                "word_entry_ids": [entry_ids[0], entry_ids[1], entry_ids[4]],
                "order": 1,
            },
            {
                "id": "new-1",
                "node_type": "NEW_WORDS",
                "title": "新词营地",
                "description": "学习今日新词。",
                "estimated_minutes": 10,
                "word_entry_ids": [entry_ids[2], entry_ids[3]],
                "order": 2,
            },
            {
                "id": "boss-1",
                "node_type": "BOSS",
                "title": "终点挑战",
                "description": "完成今天的混合小测。",
                "estimated_minutes": 12,
                "word_entry_ids": entry_ids,
                "practice_type": "fill_blank",
                "practice_count": 5,
                "order": 3,
            },
        ],
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


async def _seed_plan(app, user) -> tuple[UUID, list[str], list[str]]:
    settings = app.state.settings
    async with app.state.session_factory() as session:
        book = Wordbook(
            visibility="private",
            status="ready",
            name="Challenge test book",
            owner_id=user.id,
            created_by=user.id,
        )
        session.add(book)
        await session.flush()
        entries = [
            WordbookEntry(
                wordbook_id=book.id,
                headword=f"challenge{index}",
                normalized_headword=f"challenge{index}",
                sequence=index,
            )
            for index in range(5)
        ]
        session.add_all(entries)
        await session.flush()
        plan = DailyPlan(
            user_id=user.id,
            local_date=local_date_for(settings, user),
            wordbook_id=book.id,
            new_word_target=2,
            study_minutes_target=30,
            snapshot_time=utcnow(),
            calculation_version="challenge-test-v1",
            status="not_started",
        )
        session.add(plan)
        await session.flush()
        session.add_all(
            [
                DailyPlanWord(plan_id=plan.id, entry_id=entries[0].id, reason="due", position=0),
                DailyPlanWord(plan_id=plan.id, entry_id=entries[1].id, reason="due", position=1),
                DailyPlanWord(plan_id=plan.id, entry_id=entries[2].id, reason="new", position=2),
                DailyPlanWord(plan_id=plan.id, entry_id=entries[3].id, reason="new", position=3),
                DailyPlanWord(plan_id=plan.id, entry_id=entries[4].id, reason="due", position=4),
            ]
        )
        await session.commit()
        return (
            plan.id,
            [str(entry.id) for entry in entries],
            [str(entries[0].id), str(entries[1].id), str(entries[4].id)],
        )


async def test_challenge_generation_sync_boss_and_replay(client, app, admin_user, member_user):
    plan_id, entry_ids, _ = await _seed_plan(app, member_user)
    admin_headers = await login(client, admin_user.username)
    headers = await login(client, member_user.username)
    with fake_provider_server() as server:
        await create_provider(client, admin_headers, base_url=server.base_url)
        server.queue_json(200, challenge_output(entry_ids))
        generated = await client.post("/api/v1/challenges/today/generate", headers=headers)
        assert generated.status_code == 202, generated.text
        generated_body = generated.json()
        challenge_id = generated_body["challenge_id"]
        job_id = generated_body["job_id"]
        assert (await _run_job(app, UUID(job_id)))["status"] == "succeeded"

        today = await client.get("/api/v1/challenges/today", headers=headers)
        assert today.status_code == 200, today.text
        assert today.json()["status"] == "ready"
        assert len(today.json()["nodes"]) == 3
        assert today.json()["nodes"][0]["status"] == "unlocked"
        assert today.json()["nodes"][2]["status"] == "locked"

        replay = await client.post("/api/v1/challenges/today/generate", headers=headers)
        assert replay.status_code == 202
        assert replay.json()["challenge_id"] == challenge_id
        assert replay.json()["job_id"] == job_id
        assert replay.json()["replayed"] is True
        job_status = await client.get(f"/api/v1/challenges/jobs/{job_id}", headers=headers)
        assert job_status.status_code == 200
        assert job_status.json()["challenge_id"] == challenge_id
        assert job_status.json()["status"] == "succeeded"

        async with app.state.session_factory() as session:
            rows = list(
                (
                    await session.scalars(
                        select(DailyPlanWord).where(DailyPlanWord.plan_id == plan_id)
                    )
                ).all()
            )
            for row in rows:
                row.completed_at = utcnow()
            await session.commit()

        synced = await client.get(f"/api/v1/challenges/{challenge_id}", headers=headers)
        assert synced.status_code == 200, synced.text
        nodes = synced.json()["nodes"]
        assert [node["status"] for node in nodes] == ["completed", "completed", "unlocked"]
        boss_id = nodes[2]["id"]
        boss_start = await client.post(
            f"/api/v1/challenges/{challenge_id}/nodes/{boss_id}/start", headers=headers
        )
        assert boss_start.status_code == 200, boss_start.text
        practice_id = boss_start.json()["resource_id"]
        async with app.state.session_factory() as session:
            practice = await session.get(PracticeSession, UUID(practice_id))
            assert practice is not None and practice.ai_job_id is not None
            practice_job_id = practice.ai_job_id
        server.queue_json(200, practice_output(entry_ids))
        assert (await _run_job(app, practice_job_id))["status"] == "succeeded"
        practice_response = await client.get(
            f"/api/v1/practice/sessions/{practice_id}", headers=headers
        )
        assert practice_response.status_code == 200, practice_response.text
        questions = practice_response.json()["questions"]
        answers = [{"question_id": question["id"], "answer": "a"} for question in questions]
        submitted = await client.post(
            f"/api/v1/challenges/{challenge_id}/nodes/{boss_id}/boss-submit",
            headers={**headers, "Idempotency-Key": "boss-key-1"},
            json={"answers": answers},
        )
        assert submitted.status_code == 200, submitted.text
        assert submitted.json()["status"] == "completed"
        assert submitted.json()["completed"] is True
        repeated_submit = await client.post(
            f"/api/v1/challenges/{challenge_id}/nodes/{boss_id}/boss-submit",
            headers={**headers, "Idempotency-Key": "boss-key-1"},
            json={"answers": answers},
        )
        assert repeated_submit.status_code == 200
        assert repeated_submit.json()["completed"] is True
        conflicting_submit = await client.post(
            f"/api/v1/challenges/{challenge_id}/nodes/{boss_id}/boss-submit",
            headers={**headers, "Idempotency-Key": "boss-key-2"},
            json={"answers": answers},
        )
        assert conflicting_submit.status_code == 409

        final = await client.get(f"/api/v1/challenges/{challenge_id}", headers=headers)
        assert final.status_code == 200
        assert final.json()["status"] == "completed"
        assert final.json()["challenge_completed_at"] is not None

        history = await client.get("/api/v1/challenges/history", headers=headers)
        assert history.status_code == 200
        assert history.json()["items"][0]["id"] == challenge_id
        assert history.json()["items"][0]["status"] == "completed"


async def test_challenge_failure_retry_and_user_isolation(
    client, app, admin_user, member_user, user_factory
):
    _, entry_ids, _ = await _seed_plan(app, member_user)
    admin_headers = await login(client, admin_user.username)
    headers = await login(client, member_user.username)
    other = await user_factory(role="member")
    other_headers = await login(client, other.username)
    with fake_provider_server() as server:
        await create_provider(client, admin_headers, base_url=server.base_url)
        for _ in range(3):
            server.queue_json(500, {"error": "provider down"})
        failed = await client.post("/api/v1/challenges/today/generate", headers=headers)
        assert failed.status_code == 202, failed.text
        failed_body = failed.json()
        assert (await _run_job(app, UUID(failed_body["job_id"])))["status"] == "failed"
        failed_today = await client.get("/api/v1/challenges/today", headers=headers)
        assert failed_today.status_code == 200
        assert failed_today.json()["status"] == "failed"

        server.queue_json(200, challenge_output(entry_ids))
        retried = await client.post("/api/v1/challenges/today/generate", headers=headers)
        assert retried.status_code == 202, retried.text
        assert retried.json()["challenge_id"] == failed_body["challenge_id"]
        assert (await _run_job(app, UUID(retried.json()["job_id"])))["status"] == "succeeded"
        ready = await client.get("/api/v1/challenges/today", headers=headers)
        assert ready.status_code == 200
        assert ready.json()["status"] == "ready"
        challenge_id = ready.json()["id"]
        assert (
            await client.get(f"/api/v1/challenges/{challenge_id}", headers=other_headers)
        ).status_code == 404


async def test_challenge_cross_day_is_read_only(client, app, admin_user, member_user):
    _, entry_ids, _ = await _seed_plan(app, member_user)
    admin_headers = await login(client, admin_user.username)
    headers = await login(client, member_user.username)
    with fake_provider_server() as server:
        await create_provider(client, admin_headers, base_url=server.base_url)
        server.queue_json(200, challenge_output(entry_ids))
        generated = await client.post("/api/v1/challenges/today/generate", headers=headers)
        assert generated.status_code == 202
        challenge_id = generated.json()["challenge_id"]
        assert (await _run_job(app, UUID(generated.json()["job_id"])))["status"] == "succeeded"
        async with app.state.session_factory() as session:
            plan = await session.get(DailyChallengePlan, UUID(challenge_id))
            assert plan is not None
            plan.local_date = plan.local_date - timedelta(days=1)
            plan.expires_at = utcnow() - timedelta(days=1)
            await session.commit()
        nodes = (await client.get(f"/api/v1/challenges/{challenge_id}", headers=headers)).json()[
            "nodes"
        ]
        node_id = nodes[0]["id"]
        blocked = await client.post(
            f"/api/v1/challenges/{challenge_id}/nodes/{node_id}/start", headers=headers
        )
        assert blocked.status_code == 409
        assert blocked.json()["code"] in {"CHALLENGE_READ_ONLY", "CHALLENGE_NOT_STARTABLE"}
