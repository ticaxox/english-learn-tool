from __future__ import annotations

import hashlib
from datetime import timedelta
from uuid import uuid4

from sqlalchemy import delete

from app.models.ai import AiJob, AiUsageLedger
from app.models.challenge import DailyChallengePlan
from app.models.coach import CoachConversation, CoachMessage
from app.models.identity import User
from app.models.learning import DailyActivity, DailyPlan, DailyPlanWord, MistakeFlag
from app.models.practice import PracticeSession, PracticeSubmission
from app.models.wordbooks import Wordbook, WordbookEntry
from app.services.auth import utcnow
from app.services.learning import local_date_for
from tests.ai_support import login


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


async def _seed_dashboard(app, members):
    settings = app.state.settings
    today = local_date_for(settings, members[0])
    async with app.state.session_factory() as session:
        owner = members[0]
        book = Wordbook(
            visibility="private",
            status="ready",
            name="PRIVATE-WORDBOOK-SECRET",
            owner_id=owner.id,
            created_by=owner.id,
        )
        session.add(book)
        await session.flush()
        entry = WordbookEntry(
            wordbook_id=book.id,
            headword="secret-entry",
            normalized_headword="secret-entry",
            sequence=0,
        )
        session.add(entry)
        await session.flush()
        due_entry = WordbookEntry(
            wordbook_id=book.id,
            headword="secret-due",
            normalized_headword="secret-due",
            sequence=1,
        )
        session.add(due_entry)
        await session.flush()
        conversation = CoachConversation(user_id=owner.id, title="COACH-TITLE-SECRET")
        session.add(conversation)
        await session.flush()
        session.add(
            CoachMessage(
                conversation_id=conversation.id,
                user_id=owner.id,
                role="user",
                content="COACH-CONTENT-SECRET",
                status="completed",
                sequence=1,
                completed_at=utcnow(),
            )
        )
        owner_plan_id = None
        for index, member in enumerate(members[:3]):
            session.add_all(
                [
                    DailyActivity(
                        user_id=member.id,
                        local_date=today,
                        active_seconds=600,
                        heartbeat_count=2,
                        last_heartbeat_at=utcnow(),
                    ),
                    DailyActivity(
                        user_id=member.id,
                        local_date=today - timedelta(days=1),
                        active_seconds=300,
                        heartbeat_count=1,
                        last_heartbeat_at=utcnow(),
                    ),
                ]
            )
            plan = DailyPlan(
                user_id=member.id,
                local_date=today,
                wordbook_id=book.id,
                new_word_target=2,
                study_minutes_target=30,
                snapshot_time=utcnow(),
                calculation_version="dashboard-test-v1",
                status="completed" if index < 2 else "not_started",
            )
            session.add(plan)
            await session.flush()
            if index == 0:
                owner_plan_id = plan.id
            session.add_all(
                [
                    DailyPlanWord(
                        plan_id=plan.id,
                        entry_id=entry.id,
                        reason="new",
                        position=0,
                        completed_at=utcnow() if index < 2 else None,
                    ),
                    DailyPlanWord(
                        plan_id=plan.id,
                        entry_id=due_entry.id,
                        reason="due",
                        position=1,
                        completed_at=utcnow() if index < 2 else None,
                    ),
                ]
            )
        practice = PracticeSession(
            user_id=owner.id,
            practice_type="fill_blank",
            source="whole_book",
            wordbook_id=book.id,
            question_count=5,
            status="submitted",
            generation_number=1,
            source_context={},
            idempotency_key=f"dashboard-practice-{uuid4()}",
            request_hash=_hash("practice"),
        )
        session.add(practice)
        await session.flush()
        session.add(
            PracticeSubmission(
                session_id=practice.id,
                user_id=owner.id,
                status="completed",
                answers={"q1": "SECRET-ANSWER"},
                score=80,
                correct_count=4,
                total_questions=5,
                wrong_count=1,
                idempotency_key=f"dashboard-submit-{uuid4()}",
                request_hash=_hash("submission"),
                created_at=utcnow(),
                completed_at=utcnow(),
            )
        )
        session.add_all(
            [
                MistakeFlag(
                    user_id=owner.id,
                    wordbook_id=book.id,
                    entry_id=entry.id,
                    again_count=2,
                    last_again_at=utcnow(),
                    is_priority=True,
                ),
                MistakeFlag(
                    user_id=members[1].id,
                    wordbook_id=book.id,
                    entry_id=entry.id,
                    again_count=1,
                    last_again_at=utcnow(),
                    is_priority=False,
                ),
            ]
        )
        successful_job = AiJob(
            user_id=owner.id,
            task_type="coach_reply",
            status="succeeded",
            quota_kind="coach_messages",
            prompt_key="coach_reply",
            prompt_snapshot="safe prompt",
            input_context={},
            idempotency_key=f"dashboard-ai-{uuid4()}",
            request_hash=_hash("ai-success"),
        )
        failed_job = AiJob(
            user_id=owner.id,
            task_type="challenge_plan",
            status="failed",
            quota_kind=None,
            prompt_key="challenge_plan",
            prompt_snapshot="safe prompt",
            input_context={},
            idempotency_key=f"dashboard-ai-{uuid4()}",
            request_hash=_hash("ai-failure"),
        )
        session.add_all([successful_job, failed_job])
        await session.flush()
        session.add(
            AiUsageLedger(
                user_id=owner.id,
                job_id=successful_job.id,
                local_date=today,
                quota_kind="coach_messages",
                quota_item="job",
                reserved=0,
                consumed=1,
                released=0,
                status="consumed",
            )
        )
        session.add(
            DailyChallengePlan(
                user_id=owner.id,
                local_date=today,
                daily_plan_id=owner_plan_id,
                wordbook_id=book.id,
                status="completed",
                title="SECRET-CHALLENGE-TITLE",
                target_minutes=30,
                expires_at=utcnow() + timedelta(days=1),
                challenge_completed_at=utcnow(),
            )
        )
        await session.commit()


async def test_admin_dashboard_aggregates_filters_and_privacy(
    client, app, admin_user, user_factory
):
    core = [
        await user_factory(role="member", department="Engineering", learning_group="Core")
        for _ in range(3)
    ]
    small = [
        await user_factory(role="member", department="Sales", learning_group="Small")
        for _ in range(2)
    ]
    await _seed_dashboard(app, core + small)
    admin_headers = await login(client, admin_user.username)
    member_headers = await login(client, core[0].username)

    response = await client.get("/api/v1/admin/dashboard", headers=admin_headers)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["privacy"]["suppressed"] is False
    assert body["metrics"]["total_members"] == 5
    assert body["metrics"]["active_members"] == 3
    assert body["metrics"]["study_minutes"] == 45.0
    assert body["metrics"]["plans_completed"] == 2
    assert body["metrics"]["task_completion_rate"] == 0.6667
    assert body["metrics"]["practice_submissions"] == 1
    assert body["metrics"]["practice_correct_rate"] == 0.8
    assert body["metrics"]["mistake_flags"] == 2
    assert body["metrics"]["ai_jobs"] == 2
    assert body["metrics"]["ai_failed"] == 1
    assert body["metrics"]["ai_failure_rate"] == 0.5
    assert body["metrics"]["challenges_completed"] == 1
    assert body["risk_hints"]["inactive_members_3d"] == 2
    assert body["groups"][0]["member_count"] == 3
    assert body["suppressed_group_count"] == 1
    assert body["quota_usage"][0]["consumed"] == 1
    serialized = response.text
    assert "SECRET-ANSWER" not in serialized
    assert "COACH-CONTENT-SECRET" not in serialized
    assert "COACH-TITLE-SECRET" not in serialized
    assert "PRIVATE-WORDBOOK-SECRET" not in serialized
    assert "SECRET-CHALLENGE-TITLE" not in serialized

    filtered = await client.get(
        "/api/v1/admin/dashboard?department=Engineering&learning_group=Core",
        headers=admin_headers,
    )
    assert filtered.status_code == 200
    assert filtered.json()["metrics"]["total_members"] == 3
    assert filtered.json()["groups"][0]["member_count"] == 3

    small_filtered = await client.get(
        "/api/v1/admin/dashboard?department=Sales&learning_group=Small",
        headers=admin_headers,
    )
    assert small_filtered.status_code == 200
    assert small_filtered.json()["privacy"]["suppressed"] is True
    assert small_filtered.json()["metrics"]["active_members"] is None

    forbidden = await client.get("/api/v1/admin/dashboard", headers=member_headers)
    assert forbidden.status_code == 403

    invalid_range = await client.get(
        "/api/v1/admin/dashboard?date_from=2026-10-20&date_to=2026-10-19",
        headers=admin_headers,
    )
    assert invalid_range.status_code == 422
    too_large = await client.get(
        "/api/v1/admin/dashboard?date_from=2026-01-01&date_to=2026-10-23",
        headers=admin_headers,
    )
    assert too_large.status_code == 422

    async with app.state.session_factory() as session:
        await session.execute(delete(User).where(User.id == small[1].id))
        await session.commit()
    after_delete = await client.get("/api/v1/admin/dashboard", headers=admin_headers)
    assert after_delete.status_code == 200
    assert after_delete.json()["metrics"]["total_members"] == 4
    assert after_delete.json()["metrics"]["active_members"] == 3
    assert after_delete.json()["metrics"]["study_minutes"] == 45.0


async def test_dashboard_openapi_and_empty_range(client, app, admin_user, user_factory):
    await user_factory(role="member", department="Engineering", learning_group="Core")
    admin_headers = await login(client, admin_user.username)
    response = await client.get("/api/v1/admin/dashboard", headers=admin_headers)
    assert response.status_code == 200
    assert response.json()["privacy"]["suppressed"] is True
    assert response.json()["metrics"]["total_members"] == 1
    openapi = await client.get("/api/v1/openapi.json")
    assert openapi.status_code == 200
    paths = openapi.json()["paths"]
    assert "/api/v1/admin/dashboard" in paths
    assert "AdminDashboardResponse" in openapi.json()["components"]["schemas"]
