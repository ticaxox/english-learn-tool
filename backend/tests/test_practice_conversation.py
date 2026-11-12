"""The conversation practice: the guide leads, the learner answers.

The point of the type is that the guide reacts to what the learner said, so
these tests cover the whole exchange: the topic is invented, the guide's line
comes back, the transcript is kept, and the grader is handed the talk rather
than a single answer.
"""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest
from sqlalchemy import select

from app.models.practice import PracticeSession
from app.models.wordbooks import WordbookEntry
from app.services.ai_jobs import process_ai_job
from tests.ai_support import create_provider, fake_provider_server, login
from tests.learning_support import activate, seed_wordbook

PRACTICE_PATH = "/api/v1/practice"


def _conversation_output(entry_ids: list[str], words: list[str] | None = None) -> dict:
    words = words or ["word"] * len(entry_ids)
    return {
        "practice_type": "conversation",
        "items": [
            {
                "id": "c1",
                "topic": "A weekend hike",
                "topic_zh": "一次周末徒步",
                "role": "A guide at the trailhead",
                "role_zh": "登山口的向导",
                "scenario": "You meet at the trailhead.",
                "scenario_zh": "你们在登山口相遇。",
                "target_words": [words[0]],
                "turns": [
                    {
                        "id": "t1",
                        "line": "Morning! Ready to head up the trail?",
                        "line_zh": "早上好！准备出发了吗？",
                        "intent": "greet the learner",
                    },
                    {
                        "id": "t2",
                        "line": f"I heard about the {words[0]} on this path.",
                        "line_zh": "我听说过这条路上的事。",
                        "intent": "introduce the target word",
                    },
                ],
                "target_entry_ids": [entry_ids[0]],
            }
        ],
    }


def _turn_output(line: str) -> dict:
    return {
        "line": line,
        "line_zh": "水带够了吗？",
        "intent": "check on the learner",
    }


def _grading_output(question_ids: list[str], score: float = 80.0) -> dict:
    return {
        "items": [
            {
                "question_id": question_id,
                "total_score": score,
                "dimensions": [
                    {"name": "Fluency", "score": score * 0.5, "max_score": 50},
                    {"name": "Relevance", "score": score * 0.5, "max_score": 50},
                ],
                "errors": [],
                "suggestions": ["Answer the question you were asked."],
                "reference_content": "A better reply.",
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


async def _questions(app, session_id: str):
    async with app.state.session_factory() as session:
        practice = await session.get(PracticeSession, UUID(session_id))
        assert practice is not None
        from app.models.practice import PracticeQuestion

        return list(
            (
                await session.scalars(
                    select(PracticeQuestion)
                    .where(PracticeQuestion.generation_id == practice.current_generation_id)
                    .order_by(PracticeQuestion.position.asc())
                )
            ).all()
        )


async def _create_conversation(app, client, headers, server) -> dict:
    created = await client.post(
        f"{PRACTICE_PATH}/sessions",
        headers={**headers, "Idempotency-Key": f"create-{uuid4().hex}"},
        json={"practice_type": "conversation", "source": "whole_book", "count": 1},
    )
    assert created.status_code == 202, created.text
    session_id = created.json()["id"]
    async with app.state.session_factory() as session:
        practice = await session.get(PracticeSession, UUID(session_id))
        assert practice is not None
        entry_ids = practice.source_context["target_entry_ids"][:1]
        rows = (
            await session.execute(
                select(WordbookEntry.id, WordbookEntry.headword).where(
                    WordbookEntry.id.in_([UUID(entry) for entry in entry_ids])
                )
            )
        ).all()
    headwords = {str(entry_id): headword for entry_id, headword in rows}
    words = [headwords.get(entry, "word") for entry in entry_ids]
    server.queue_json(200, _conversation_output(entry_ids, words))
    await _run_job(app, await _job_id_for_session(app, session_id))
    response = await client.get(f"{PRACTICE_PATH}/sessions/{session_id}", headers=headers)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "ready", body
    return body


@pytest.mark.asyncio
async def test_conversation_guide_answers_what_the_learner_said(client, app, member_user) -> None:
    headers = await login(client, member_user.username)
    wordbook_id = await seed_wordbook(app, owner_id=member_user.id, entries=4)
    await activate(app, user_id=member_user.id, wordbook_id=wordbook_id)
    with fake_provider_server() as server:
        await create_provider(client, headers, base_url=server.base_url)
        session = await _create_conversation(app, client, headers, server)
        question = session["questions"][0]

        # The generated item carries the topic, the character and the guide's
        # opening lines.
        assert question["topic"] == "A weekend hike"
        assert question["role"] == "A guide at the trailhead"
        assert len(question["turns"]) == 2
        assert question["turns"][0]["intent"] == "greet the learner"

        # The dialogue opens with the guide's lines.
        turns = await client.get(
            f"{PRACTICE_PATH}/sessions/{session['id']}/conversation/turns", headers=headers
        )
        assert turns.status_code == 200, turns.text
        assert [turn["speaker"] for turn in turns.json()] == ["guide", "guide"]
        assert turns.json()[0]["line"] == "Morning! Ready to head up the trail?"

        # The learner says something; the guide answers it.
        said = await client.post(
            f"{PRACTICE_PATH}/sessions/{session['id']}/conversation/turns",
            headers={**headers, "Idempotency-Key": f"turn-{uuid4().hex}"},
            json={"line": "Yes, I brought plenty of water."},
        )
        assert said.status_code == 202, said.text
        assert said.json()["status"] == "queued"

        server.queue_json(200, _turn_output("Did you bring plenty of water?"))
        await _run_job(app, UUID(said.json()["job_id"]))

        after = await client.get(
            f"{PRACTICE_PATH}/sessions/{session['id']}/conversation/turns", headers=headers
        )
        assert after.status_code == 200, after.text
        speakers = [turn["speaker"] for turn in after.json()]
        assert speakers == ["guide", "guide", "learner", "guide"]
        assert after.json()[2]["line"] == "Yes, I brought plenty of water."
        assert after.json()[3]["line"] == "Did you bring plenty of water?"
        assert after.json()[3]["intent"] == "check on the learner"


@pytest.mark.asyncio
async def test_conversation_is_graded_on_the_whole_talk(client, app, member_user) -> None:
    headers = await login(client, member_user.username)
    wordbook_id = await seed_wordbook(app, owner_id=member_user.id, entries=4)
    await activate(app, user_id=member_user.id, wordbook_id=wordbook_id)
    with fake_provider_server() as server:
        await create_provider(client, headers, base_url=server.base_url)
        session = await _create_conversation(app, client, headers, server)
        questions = await _questions(app, session["id"])

        said = await client.post(
            f"{PRACTICE_PATH}/sessions/{session['id']}/conversation/turns",
            headers={**headers, "Idempotency-Key": f"turn-{uuid4().hex}"},
            json={"line": "I am ready."},
        )
        assert said.status_code == 202, said.text
        server.queue_json(200, _turn_output("What did you bring?"))
        await _run_job(app, UUID(said.json()["job_id"]))

        submitted = await client.post(
            f"{PRACTICE_PATH}/sessions/{session['id']}/submit",
            headers={**headers, "Idempotency-Key": f"submit-{uuid4().hex}"},
            json={"answers": [{"question_id": str(questions[0].id), "answer": "I am ready."}]},
        )
        assert submitted.status_code == 202, submitted.text
        assert submitted.json()["status"] == "scoring"

        server.queue_json(200, _grading_output([str(questions[0].id)], score=90))
        await _run_job(app, await _submission_job(app, submitted.json()["submission_id"]))
        result = await client.get(
            f"{PRACTICE_PATH}/sessions/{session['id']}/result", headers=headers
        )
        assert result.status_code == 200, result.text
        assert result.json()["status"] == "completed"
        assert result.json()["score"] == 90.0


async def _submission_job(app, submission_id: str) -> UUID:
    from app.models.practice import PracticeSubmission

    async with app.state.session_factory() as session:
        submission = await session.get(PracticeSubmission, UUID(submission_id))
        assert submission is not None and submission.ai_job_id is not None
        return submission.ai_job_id


@pytest.mark.asyncio
async def test_conversation_turn_is_refused_on_another_practice_type(
    client, app, member_user
) -> None:
    headers = await login(client, member_user.username)
    wordbook_id = await seed_wordbook(app, owner_id=member_user.id, entries=4)
    await activate(app, user_id=member_user.id, wordbook_id=wordbook_id)
    with fake_provider_server() as server:
        await create_provider(client, headers, base_url=server.base_url)
        created = await client.post(
            f"{PRACTICE_PATH}/sessions",
            headers={**headers, "Idempotency-Key": f"create-{uuid4().hex}"},
            json={"practice_type": "fill_blank", "source": "whole_book", "count": 3},
        )
        assert created.status_code == 202, created.text
        session_id = created.json()["id"]
        refused = await client.post(
            f"{PRACTICE_PATH}/sessions/{session_id}/conversation/turns",
            headers={**headers, "Idempotency-Key": f"turn-{uuid4().hex}"},
            json={"line": "Hello"},
        )
        assert refused.status_code == 409
        assert refused.json()["code"] == "PRACTICE_NOT_CONVERSATION"
