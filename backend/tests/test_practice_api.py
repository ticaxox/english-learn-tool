from __future__ import annotations

from uuid import UUID, uuid4

from sqlalchemy import select

from app.models.practice import PracticeQuestion, PracticeSession, PracticeSubmission
from app.services.ai_jobs import process_ai_job
from app.services.learning import local_date_for
from tests.ai_support import (
    create_provider,
    fake_provider_server,
    login,
    practice_output,
)
from tests.learning_support import activate, seed_wordbook

PRACTICE_PATH = "/api/v1/practice"
LOGIN_PATH = "/api/v1/auth/login"


def _reading_output(entry_ids: list[str]) -> dict:
    questions = []
    for index in range(3):
        questions.append(
            {
                "id": f"rq{index}",
                "prompt": "What is the main idea?",
                "options": [
                    {"id": "a", "text": "A", "text_zh": "甲"},
                    {"id": "b", "text": "B", "text_zh": "乙"},
                    {"id": "c", "text": "C", "text_zh": "丙"},
                    {"id": "d", "text": "D", "text_zh": "丁"},
                ],
                "correct_option_id": "a",
                "explanation": "The passage supports A.",
            }
        )
    return {
        "practice_type": "reading",
        "items": [
            {
                "id": "p1",
                "article": " ".join(["word"] * 200),
                "article_zh": "文章",
                "questions": questions,
                "target_entry_ids": [entry_ids[0]],
            }
        ],
    }


def _translation_output(entry_ids: list[str]) -> dict:
    return {
        "practice_type": "translation",
        "items": [
            {
                "id": f"t{index}",
                "source_text": f"Translate sentence {index}.",
                "source_language": "en",
                "target_language": "zh",
                "reference_translation": f"参考译文 {index}",
                "target_entry_ids": [entry_ids[index % len(entry_ids)]],
            }
            for index in range(3)
        ],
    }


def _writing_output(entry_ids: list[str]) -> dict:
    return {
        "practice_type": "writing",
        "items": [
            {
                "id": "w1",
                "prompt": "Write about a harbor.",
                "requirements": ["Use at least 50 words."],
                "reference_essay": "The harbor is busy.",
                "target_entry_ids": [entry_ids[0]],
            }
        ],
    }


def _mixed_output(entry_ids: list[str]) -> dict:
    fill = practice_output(entry_ids[:2])
    reading = _reading_output(entry_ids)
    return {
        "practice_type": "mixed",
        "items": [*fill["items"], {"id": "rp1", **{
            key: value for key, value in reading["items"][0].items() if key != "questions"
        }, "questions": reading["items"][0]["questions"][:1]}],
    }


def _generation_output(practice_type: str, entry_ids: list[str]) -> dict:
    if practice_type == "mixed":
        return _mixed_output(entry_ids)
    if practice_type == "fill_blank":
        return practice_output(entry_ids)
    if practice_type == "reading":
        return _reading_output(entry_ids)
    if practice_type == "translation":
        return _translation_output(entry_ids)
    if practice_type == "writing":
        return _writing_output(entry_ids)
    raise AssertionError(practice_type)


def _grading_output(question_ids: list[str], score: float = 75.0) -> dict:
    return {
        "items": [
            {
                "question_id": question_id,
                "total_score": score,
                "dimensions": [
                    {"name": "Accuracy", "score": score * 0.5, "max_score": 50},
                    {"name": "Coherence", "score": score * 0.5, "max_score": 50},
                ],
                "errors": [],
                "suggestions": ["Add one concrete detail."],
                "reference_content": "参考改进内容",
            }
            for question_id in question_ids
        ]
    }


async def _run_job(app, job_id: UUID) -> dict:
    return await process_ai_job(
        {
            "session_factory": app.state.session_factory,
            "settings": app.state.settings,
            "redis": app.state.redis,
        },
        str(job_id),
    )


async def _job_id_for_session(app, session_id: str) -> UUID:
    async with app.state.session_factory() as session:
        practice = await session.get(PracticeSession, UUID(session_id))
        assert practice is not None and practice.ai_job_id is not None
        return practice.ai_job_id


async def _job_id_for_submission(app, submission_id: str) -> UUID:
    async with app.state.session_factory() as session:
        submission = await session.get(PracticeSubmission, UUID(submission_id))
        assert submission is not None and submission.ai_job_id is not None
        return submission.ai_job_id


async def _questions(app, session_id: str) -> list[PracticeQuestion]:
    async with app.state.session_factory() as session:
        practice = await session.get(PracticeSession, UUID(session_id))
        assert practice is not None
        return list(
            (
                await session.scalars(
                    select(PracticeQuestion)
                    .where(PracticeQuestion.generation_id == practice.current_generation_id)
                    .order_by(PracticeQuestion.position.asc())
                )
            ).all()
        )


async def _create_session(client, headers, practice_type: str, count: int, key: str) -> dict:
    response = await client.post(
        f"{PRACTICE_PATH}/sessions",
        headers={**headers, "Idempotency-Key": key},
        json={
            "practice_type": practice_type,
            "source": "whole_book",
            "count": count,
        },
    )
    assert response.status_code == 202, response.text
    return response.json()


async def _generate(app, client, headers, server, practice_type: str, count: int) -> dict:
    created = await _create_session(client, headers, practice_type, count, f"create-{uuid4().hex}")
    async with app.state.session_factory() as session:
        practice = await session.get(PracticeSession, UUID(created["id"]))
        assert practice is not None
        entry_ids = practice.source_context["target_entry_ids"][:count]
    server.queue_json(200, _generation_output(practice_type, entry_ids))
    await _run_job(app, await _job_id_for_session(app, created["id"]))
    response = await client.get(f"{PRACTICE_PATH}/sessions/{created['id']}", headers=headers)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "ready", body
    assert body["questions"]
    assert "correct_option_id" not in response.text
    assert "explanation" not in response.text
    assert "reference_translation" not in response.text
    assert "reference_essay" not in response.text
    return body


async def test_four_practice_types_draft_regenerate_submit_records_and_delete(
    client, app, admin_user, member_user, user_factory
) -> None:
    admin_headers = await login(client, admin_user.username)
    member_headers = await login(client, member_user.username)
    wordbook_id = await seed_wordbook(app, owner_id=member_user.id, entries=8)
    await activate(app, user_id=member_user.id, wordbook_id=wordbook_id)
    with fake_provider_server() as server:
        await create_provider(client, member_headers, base_url=server.base_url)

        fill = await _generate(app, client, member_headers, server, "fill_blank", 3)
        questions = await _questions(app, fill["id"])
        correct = questions[0].private_payload["correct_option_id"]
        wrong = next(
            option["id"]
            for option in questions[0].public_payload["options"]
            if option["id"] != correct
        )
        answers = [
            {"question_id": str(question.id), "answer": correct if index == 0 else wrong}
            for index, question in enumerate(questions)
        ]
        draft = await client.put(
            f"{PRACTICE_PATH}/sessions/{fill['id']}/draft",
            headers=member_headers,
            json={"version": 0, "answers": {str(questions[0].id): correct}},
        )
        assert draft.status_code == 200, draft.text
        resumed = await client.get(f"{PRACTICE_PATH}/sessions/{fill['id']}", headers=member_headers)
        assert resumed.json()["draft_answers"] == {str(questions[0].id): correct}
        stale_draft = await client.put(
            f"{PRACTICE_PATH}/sessions/{fill['id']}/draft",
            headers=member_headers,
            json={"version": 0, "answers": {}},
        )
        assert stale_draft.status_code == 409
        assert stale_draft.json()["code"] == "PRACTICE_DRAFT_VERSION_CONFLICT"
        submitted = await client.post(
            f"{PRACTICE_PATH}/sessions/{fill['id']}/submit",
            headers={**member_headers, "Idempotency-Key": f"submit-{uuid4().hex}"},
            json={"answers": answers},
        )
        assert submitted.status_code == 202, submitted.text
        assert submitted.json()["status"] == "completed"
        assert submitted.json()["result"]["score"] == 33.33
        result = await client.get(
            f"{PRACTICE_PATH}/sessions/{fill['id']}/result", headers=member_headers
        )
        assert result.status_code == 200
        assert result.json()["questions"][0]["correct_option_id"] == correct
        assert result.json()["questions"][0]["explanation"]

        reading = await _generate(app, client, member_headers, server, "reading", 3)
        reading_questions = await _questions(app, reading["id"])
        reading_answers = [
            {"question_id": str(question.id), "answer": "a"} for question in reading_questions
        ]
        reading_submit = await client.post(
            f"{PRACTICE_PATH}/sessions/{reading['id']}/submit",
            headers={**member_headers, "Idempotency-Key": f"reading-submit-{uuid4().hex}"},
            json={"answers": reading_answers},
        )
        assert reading_submit.status_code == 202, reading_submit.text
        assert reading_submit.json()["result"]["score"] == 100.0

        translation = await _generate(app, client, member_headers, server, "translation", 3)
        translation_questions = await _questions(app, translation["id"])
        translation_answers = [
            {"question_id": str(question.id), "answer": "我的翻译"}
            for question in translation_questions
        ]
        translation_submit = await client.post(
            f"{PRACTICE_PATH}/sessions/{translation['id']}/submit",
            headers={**member_headers, "Idempotency-Key": f"translation-submit-{uuid4().hex}"},
            json={"answers": translation_answers},
        )
        assert translation_submit.status_code == 202, translation_submit.text
        assert translation_submit.json()["status"] == "scoring"
        usage_date = local_date_for(app.state.settings, member_user)
        admin_usage = await client.get(
            "/api/v1/admin/ai/usage",
            headers=admin_headers,
            params={"date_from": usage_date.isoformat(), "date_to": usage_date.isoformat()},
        )
        subjective_reserved = next(
            item
            for item in admin_usage.json()["quotas"]
            if item["quota_kind"] == "subjective_grading"
        )
        assert subjective_reserved["reserved"] == 3
        server.queue_json(
            200,
            _grading_output([str(question.id) for question in translation_questions], score=55),
        )
        await _run_job(
            app, await _job_id_for_submission(app, translation_submit.json()["submission_id"])
        )
        translation_result = await client.get(
            f"{PRACTICE_PATH}/sessions/{translation['id']}/result", headers=member_headers
        )
        assert translation_result.status_code == 200, translation_result.text
        assert translation_result.json()["status"] == "completed"
        assert translation_result.json()["score"] == 55.0
        assert translation_result.json()["wrong_count"] == 3
        usage = await client.get("/api/v1/ai/usage/me", headers=member_headers)
        subjective = next(
            item for item in usage.json()["quotas"] if item["quota_kind"] == "subjective_grading"
        )
        assert subjective["used"] == 3
        assert subjective["reserved"] == 0

        writing = await _generate(app, client, member_headers, server, "writing", 1)
        writing_questions = await _questions(app, writing["id"])
        writing_submit = await client.post(
            f"{PRACTICE_PATH}/sessions/{writing['id']}/submit",
            headers={**member_headers, "Idempotency-Key": f"writing-submit-{uuid4().hex}"},
            json={
                "answers": [{"question_id": str(writing_questions[0].id), "answer": "My essay."}]
            },
        )
        assert writing_submit.status_code == 202, writing_submit.text
        server.queue_json(
            200,
            _grading_output([str(writing_questions[0].id)], score=80),
        )
        await _run_job(
            app, await _job_id_for_submission(app, writing_submit.json()["submission_id"])
        )
        writing_result = await client.get(
            f"{PRACTICE_PATH}/sessions/{writing['id']}/result", headers=member_headers
        )
        assert writing_result.json()["score"] == 80.0
        assert writing_result.json()["wrong_count"] == 0

        records = await client.get(f"{PRACTICE_PATH}/records", headers=member_headers)
        assert records.status_code == 200
        assert records.json()["total"] == 4
        mistakes = await client.get(f"{PRACTICE_PATH}/mistakes", headers=member_headers)
        assert mistakes.status_code == 200
        assert mistakes.json()["total"] >= 2

        other = await user_factory(role="member")
        other_headers = await login(client, other.username)
        hidden = await client.get(f"{PRACTICE_PATH}/sessions/{fill['id']}", headers=other_headers)
        assert hidden.status_code == 404

        deleted = await client.request(
            "DELETE",
            f"{PRACTICE_PATH}/records/bulk",
            headers={**member_headers, "Idempotency-Key": f"delete-{uuid4().hex}"},
            json={"ids": [fill["id"], reading["id"]]},
        )
        assert deleted.status_code == 200, deleted.text
        assert deleted.json()["deleted_count"] == 2
        after = await client.get(f"{PRACTICE_PATH}/records", headers=member_headers)
        assert after.json()["total"] == 2


async def test_practice_regenerate_replaces_generation_without_history(
    client, app, member_user
) -> None:
    member_headers = await login(client, member_user.username)
    wordbook_id = await seed_wordbook(app, owner_id=member_user.id, entries=8)
    await activate(app, user_id=member_user.id, wordbook_id=wordbook_id)
    with fake_provider_server() as server:
        await create_provider(client, member_headers, base_url=server.base_url)
        first = await _generate(app, client, member_headers, server, "fill_blank", 3)
        async with app.state.session_factory() as session:
            practice = await session.get(PracticeSession, UUID(first["id"]))
            assert practice is not None
            entry_ids = practice.source_context["target_entry_ids"][:3]
        regenerated = await client.post(
            f"{PRACTICE_PATH}/sessions/{first['id']}/regenerate",
            headers={**member_headers, "Idempotency-Key": f"regen-{uuid4().hex}"},
        )
        assert regenerated.status_code == 202, regenerated.text
        assert regenerated.json()["generation_number"] == 2
        server.queue_json(200, _generation_output("fill_blank", entry_ids))
        await _run_job(app, await _job_id_for_session(app, first["id"]))
        final = await client.get(f"{PRACTICE_PATH}/sessions/{first['id']}", headers=member_headers)
        assert final.json()["status"] == "ready"
        assert final.json()["generation_number"] == 2
        records = await client.get(f"{PRACTICE_PATH}/records", headers=member_headers)
        assert records.json()["total"] == 0


async def test_practice_generation_and_grading_failures_do_not_default_score(
    client, app, member_user
) -> None:
    member_headers = await login(client, member_user.username)
    wordbook_id = await seed_wordbook(app, owner_id=member_user.id, entries=8)
    await activate(app, user_id=member_user.id, wordbook_id=wordbook_id)
    with fake_provider_server() as server:
        await create_provider(client, member_headers, base_url=server.base_url)

        failed_generation = await _create_session(
            client, member_headers, "fill_blank", 3, f"gen-fail-{uuid4().hex}"
        )
        for _ in range(3):
            server.queue_json(500, {"error": "temporary"})
        await _run_job(app, await _job_id_for_session(app, failed_generation["id"]))
        generation_status = await client.get(
            f"{PRACTICE_PATH}/sessions/{failed_generation['id']}", headers=member_headers
        )
        assert generation_status.json()["status"] == "failed"
        assert generation_status.json()["questions"] == []
        usage = await client.get("/api/v1/ai/usage/me", headers=member_headers)
        question_usage = next(
            item for item in usage.json()["quotas"] if item["quota_kind"] == "question_generation"
        )
        assert question_usage["reserved"] == 0

        translation = await _generate(app, client, member_headers, server, "translation", 3)
        questions = await _questions(app, translation["id"])
        submit = await client.post(
            f"{PRACTICE_PATH}/sessions/{translation['id']}/submit",
            headers={**member_headers, "Idempotency-Key": f"grade-fail-{uuid4().hex}"},
            json={
                "answers": [
                    {"question_id": str(question.id), "answer": "翻译"} for question in questions
                ]
            },
        )
        assert submit.status_code == 202, submit.text
        for _ in range(3):
            server.queue_json(500, {"error": "temporary"})
        await _run_job(app, await _job_id_for_submission(app, submit.json()["submission_id"]))
        result = await client.get(
            f"{PRACTICE_PATH}/sessions/{translation['id']}/result", headers=member_headers
        )
        assert result.status_code == 200
        assert result.json()["status"] == "failed"
        assert result.json()["score"] is None
        assert result.json()["questions"] == []
        assert result.json()["error_code"]
        usage = await client.get("/api/v1/ai/usage/me", headers=member_headers)
        subjective = next(
            item for item in usage.json()["quotas"] if item["quota_kind"] == "subjective_grading"
        )
        assert subjective["reserved"] == 0


async def test_recent_sessions_are_listed_and_can_be_deleted(client, app, member_user) -> None:
    headers = await login(client, member_user.username)
    wordbook_id = await seed_wordbook(app, owner_id=member_user.id, entries=8)
    await activate(app, user_id=member_user.id, wordbook_id=wordbook_id)
    with fake_provider_server() as server:
        await create_provider(client, headers, base_url=server.base_url)
        fill = await _generate(app, client, headers, server, "fill_blank", 3)

    listed = await client.get(f"{PRACTICE_PATH}/sessions?limit=10", headers=headers)
    assert listed.status_code == 200, listed.text
    ids = [item["id"] for item in listed.json()["items"]]
    assert fill["id"] in ids

    deleted = await client.delete(f"{PRACTICE_PATH}/sessions/{fill['id']}", headers=headers)
    assert deleted.status_code == 204

    after = await client.get(f"{PRACTICE_PATH}/sessions?limit=10", headers=headers)
    assert all(item["id"] != fill["id"] for item in after.json()["items"])


async def test_mixed_practice_grades_choice_questions_locally(
    client, app, member_user
) -> None:
    headers = await login(client, member_user.username)
    wordbook_id = await seed_wordbook(app, owner_id=member_user.id, entries=8)
    await activate(app, user_id=member_user.id, wordbook_id=wordbook_id)
    with fake_provider_server() as server:
        await create_provider(client, headers, base_url=server.base_url)
        mixed = await _generate(app, client, headers, server, "mixed", 3)
        questions = await _questions(app, mixed["id"])
        assert len(questions) == 3
        answers = []
        for index, question in enumerate(questions):
            correct = question.private_payload["correct_option_id"]
            wrong = next(
                option["id"]
                for option in question.public_payload["options"]
                if option["id"] != correct
            )
            answers.append({"question_id": str(question.id), "answer": correct if index else wrong})
        submitted = await client.post(
            f"{PRACTICE_PATH}/sessions/{mixed['id']}/submit",
            headers={**headers, "Idempotency-Key": f"mixed-submit-{uuid4().hex}"},
            json={"answers": answers},
        )
        assert submitted.status_code == 202, submitted.text
        body = submitted.json()
        assert body["status"] == "completed"
        assert body["result"]["total_questions"] == 3
        assert body["result"]["correct_count"] == 2
        assert body["result"]["score"] == 66.67
