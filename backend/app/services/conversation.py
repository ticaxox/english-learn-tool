"""The guide in a conversation practice.

A conversation practice is one dialogue. The AI invents the topic and the
character, then leads: the learner answers, and the guide answers back. This
module owns that second half — the part where the guide has to react to what
the learner actually said rather than replay a script.

Every exchange is stored, so the guide can see the talk so far and the grader
can see the whole thing, not a single answer floating free of context.
"""

from __future__ import annotations

import logging
from uuid import UUID, uuid4

from arq.connections import ArqRedis
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.errors import AppError
from app.models.ai import AiJob
from app.models.identity import User
from app.models.practice import (
    PracticeConversationTurn,
    PracticeQuestion,
    PracticeSession,
)
from app.schemas.ai_tasks import (
    ConversationTurnContext,
    ConversationTurnRequest,
)
from app.schemas.practice import (
    PracticeConversationTurnPublic,
    PracticeConversationTurnResponse,
)
from app.services.ai_jobs import create_ai_job

logger = logging.getLogger(__name__)

# A dialogue that runs forever is a chat, not an exercise. The guide stops
# after this many of its own lines.
MAX_TURNS = 12
# How much of the talk the guide carries in its head.
HISTORY_WINDOW = 12


def _conversation_question(questions: list[PracticeQuestion]) -> PracticeQuestion | None:
    for question in questions:
        if question.question_type == "conversation":
            return question
    return None


async def _turns(session: AsyncSession, session_id: UUID) -> list[PracticeConversationTurn]:
    return list(
        (
            await session.scalars(
                select(PracticeConversationTurn)
                .where(PracticeConversationTurn.session_id == session_id)
                .order_by(PracticeConversationTurn.sequence.asc())
            )
        ).all()
    )


def _turn_public(turn: PracticeConversationTurn) -> PracticeConversationTurnPublic:
    return PracticeConversationTurnPublic(
        id=turn.id,
        sequence=turn.sequence,
        speaker=turn.speaker,
        line=turn.line,
        line_zh=turn.line_zh,
        intent=turn.intent,
        created_at=turn.created_at,
    )


def _history_for_guide(
    turns: list[PracticeConversationTurn],
) -> list[dict[str, str]]:
    """The talk so far, oldest first, in the shape the guide reads it."""
    return [{"speaker": turn.speaker, "line": turn.line} for turn in turns[-HISTORY_WINDOW:]]


async def list_conversation_turns(
    session: AsyncSession,
    user: User,
    practice: PracticeSession,
    questions: list[PracticeQuestion],
) -> list[PracticeConversationTurnPublic]:
    """Every exchange of the dialogue, guide and learner alike."""
    question = _conversation_question(questions)
    if question is None:
        return []
    stored = await _turns(session, practice.id)
    if stored:
        return [_turn_public(turn) for turn in stored]
    # A conversation whose rows have not been written yet still has the guide's
    # opening lines on the question itself.
    return [
        PracticeConversationTurnPublic(
            id=uuid4(),
            sequence=index,
            speaker="guide",
            line=turn.get("line", ""),
            line_zh=turn.get("line_zh"),
            intent=turn.get("intent"),
            created_at=practice.created_at,
        )
        for index, turn in enumerate(question.public_payload.get("turns", []) or [])
    ]


async def append_learner_turn(
    session: AsyncSession,
    practice: PracticeSession,
    questions: list[PracticeQuestion],
    line: str,
) -> PracticeConversationTurn:
    """Record what the learner said, so the guide can answer it."""
    question = _conversation_question(questions)
    if question is None:
        raise AppError(
            status_code=409,
            code="PRACTICE_NOT_CONVERSATION",
            message="This practice session is not a conversation.",
        )
    existing = await _turns(session, practice.id)
    sequence = max((turn.sequence for turn in existing), default=-1) + 1
    turn = PracticeConversationTurn(
        session_id=practice.id,
        user_id=practice.user_id,
        speaker="learner",
        sequence=sequence,
        line=line,
        line_zh=None,
        intent=None,
    )
    session.add(turn)
    await session.flush()
    return turn


async def create_conversation_turn_job(
    session: AsyncSession,
    pool: ArqRedis,
    user: User,
    settings: Settings,
    practice: PracticeSession,
    questions: list[PracticeQuestion],
    learner_line: str,
    *,
    idempotency_key: str,
) -> PracticeConversationTurnResponse:
    """Ask the guide for its next line.

    The learner has just spoken; the guide answers. The whole talk so far
    travels with the request, because a guide that cannot hear the previous
    exchange is not guiding anything.
    """
    question = _conversation_question(questions)
    if question is None:
        raise AppError(
            status_code=409,
            code="PRACTICE_NOT_CONVERSATION",
            message="This practice session is not a conversation.",
        )
    if practice.status != "ready":
        raise AppError(
            status_code=409,
            code="PRACTICE_NOT_READY",
            message="The practice session is not ready.",
        )
    payload = question.public_payload
    stored = await _turns(session, practice.id)
    # Only the guide's own lines count as turns of the exercise; the learner's
    # replies are the answers to them.
    guide_turns = sum(1 for item in stored if item.speaker == "guide")
    if guide_turns >= MAX_TURNS:
        raise AppError(
            status_code=409,
            code="PRACTICE_CONVERSATION_COMPLETE",
            message="This conversation has run its course.",
        )
    # The placeholder row comes first: the job needs to know where its
    # answer will land, and the row needs the job's id to be matched up.
    turn = PracticeConversationTurn(
        session_id=practice.id,
        user_id=practice.user_id,
        speaker="guide",
        sequence=max((item.sequence for item in stored), default=-1) + 1,
        line="",
        line_zh=None,
        intent=None,
    )
    session.add(turn)
    await session.flush()
    request = ConversationTurnRequest(
        task_type="conversation_turn",
        context=ConversationTurnContext(
            topic=str(payload.get("topic") or "A conversation"),
            topic_zh=payload.get("topic_zh"),
            role=str(payload.get("role") or "A friendly conversation partner"),
            role_zh=payload.get("role_zh"),
            scenario=payload.get("scenario"),
            history=_history_for_guide(stored),
            target_words=list(payload.get("target_words") or []),
            learner_line=learner_line,
            conversation_turn_id=turn.id,
        ),
    )
    job, _ = await create_ai_job(
        session,
        pool,
        user,
        settings,
        request,
        idempotency_key=idempotency_key,
    )
    turn.ai_job_id = job.id
    await session.flush()
    return PracticeConversationTurnResponse(
        turn=_turn_public(turn),
        job_id=job.id,
        status="queued",
    )


async def materialize_conversation_turn(session: AsyncSession, job: AiJob) -> None:
    """Write the guide's line once the model has answered."""
    if job.result is None:
        return
    turn_id = job.input_context.get("conversation_turn_id")
    if not turn_id:
        return
    try:
        turn_uuid = UUID(str(turn_id))
    except ValueError:
        return
    turn = await session.scalar(
        select(PracticeConversationTurn)
        .where(PracticeConversationTurn.id == turn_uuid)
        .with_for_update()
    )
    if turn is None or turn.ai_job_id != job.id:
        return
    result = job.result
    turn.line = str(result.get("line") or "")
    turn.line_zh = result.get("line_zh")
    turn.intent = result.get("intent")
    await session.flush()


async def mark_conversation_turn_failed(session: AsyncSession, job: AiJob) -> None:
    """Drop the placeholder turn so the dialogue stays readable."""
    turn_id = job.input_context.get("conversation_turn_id")
    if not turn_id:
        return
    try:
        turn_uuid = UUID(str(turn_id))
    except ValueError:
        return
    turn = await session.scalar(
        select(PracticeConversationTurn)
        .where(PracticeConversationTurn.id == turn_uuid)
        .with_for_update()
    )
    if turn is None or turn.ai_job_id != job.id:
        return
    if not turn.line:
        # The guide never got a line out; the empty row would show up as a
        # blank bubble in the talk.
        await session.delete(turn)
    await session.flush()


async def conversation_transcript(
    session: AsyncSession, practice: PracticeSession, questions: list[PracticeQuestion]
) -> str:
    """The whole dialogue as one block of text, for the grader."""
    question = _conversation_question(questions)
    if question is None:
        return ""
    payload = question.public_payload
    lines = [
        f"Topic: {payload.get('topic', '')}",
        f"You are: {payload.get('role', '')}",
        f"Setting: {payload.get('scenario', '')}",
        "",
        "The conversation so far:",
    ]
    stored = await _turns(session, practice.id)
    if stored:
        for turn in stored:
            who = "Guide" if turn.speaker == "guide" else "Learner"
            lines.append(f"{who}: {turn.line}")
            if turn.speaker == "guide" and turn.intent:
                lines.append(f"   (aim: {turn.intent})")
    else:
        for turn in payload.get("turns", []) or []:
            lines.append(f"Guide: {turn.get('line', '')}")
            if turn.get("intent"):
                lines.append(f"   (aim: {turn['intent']})")
    return "\n".join(lines)


async def count_turns(session: AsyncSession, session_id: UUID) -> int:
    return int(
        await session.scalar(
            select(func.coalesce(func.count(PracticeConversationTurn.id), 0)).where(
                PracticeConversationTurn.session_id == session_id
            )
        )
        or 0
    )


__all__ = [
    "MAX_TURNS",
    "append_learner_turn",
    "conversation_transcript",
    "count_turns",
    "create_conversation_turn_job",
    "list_conversation_turns",
    "mark_conversation_turn_failed",
    "materialize_conversation_turn",
]
