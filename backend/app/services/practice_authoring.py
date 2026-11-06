"""Create a practice set from questions supplied by the caller.

No AI job and no quota: the caller (an MCP client) writes the questions, the
same row shape the AI generation materializer writes.
"""

from __future__ import annotations

import hashlib
import json
from uuid import uuid4

from pydantic import Field, model_validator
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.identity import User
from app.models.practice import PracticeGeneration, PracticeSession
from app.schemas.ai_tasks import (
    FillBlankItem,
    PracticeItem,
    PracticeType,
    ReadingPassage,
    StrictModel,
    TranslationItem,
    WritingItem,
)
from app.services.auth import utcnow
from app.services.practice import _event, question_rows

_ITEM_TYPES = {
    "fill_blank": FillBlankItem,
    "reading": ReadingPassage,
    "translation": TranslationItem,
    "writing": WritingItem,
}


class AuthoredPracticeRequest(StrictModel):
    practice_type: PracticeType
    items: list[PracticeItem] = Field(min_length=1, max_length=20)

    @model_validator(mode="after")
    def items_match_type(self) -> AuthoredPracticeRequest:
        expected = _ITEM_TYPES[self.practice_type]
        if any(not isinstance(item, expected) for item in self.items):
            raise ValueError("practice items do not match practice_type")
        return self


async def create_authored_practice(
    session: AsyncSession, user: User, output: AuthoredPracticeRequest
) -> PracticeSession:
    session_id = uuid4()
    generation_id = uuid4()
    payload = output.model_dump(mode="json")
    practice = PracticeSession(
        id=session_id,
        user_id=user.id,
        practice_type=output.practice_type,
        source="whole_book",
        question_count=len(output.items),
        status="ready",
        generation_number=1,
        current_generation_id=generation_id,
        source_context={"started_by": "mcp"},
        request_hash=hashlib.sha256(
            json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
        ).hexdigest(),
        idempotency_key=f"mcp-practice:{uuid4()}",
    )
    session.add(practice)
    await session.flush()

    generation = PracticeGeneration(
        id=generation_id,
        session_id=session_id,
        generation_number=1,
        status="ready",
        question_count=len(output.items),
        ready_at=utcnow(),
    )
    session.add(generation)
    await session.flush()

    session.add_all(question_rows(output.items, generation))
    session.add(
        _event(
            practice,
            "practice.generated",
            metadata={"question_count": len(output.items), "source": "mcp"},
        )
    )
    await session.commit()
    return practice
