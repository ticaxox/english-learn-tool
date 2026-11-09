from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

CoachMemoryKind = Literal["preference", "goal", "constraint", "fact", "note"]
CoachMemoryStatus = Literal["active", "superseded", "archived"]
CoachMemorySource = Literal["user_explicit", "coach_inferred", "imported"]


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CoachMemoryCreate(_StrictModel):
    kind: CoachMemoryKind = "fact"
    content: str = Field(min_length=1, max_length=500)
    subject_key: str | None = Field(default=None, max_length=64)
    importance: int = Field(default=3, ge=1, le=5)
    source: CoachMemorySource = "user_explicit"


class CoachMemoryUpdate(_StrictModel):
    kind: CoachMemoryKind | None = None
    content: str | None = Field(default=None, min_length=1, max_length=500)
    subject_key: str | None = Field(default=None, max_length=64)
    importance: int | None = Field(default=None, ge=1, le=5)


class CoachMemoryResponse(BaseModel):
    id: UUID
    kind: CoachMemoryKind
    subject_key: str | None = None
    content: str
    source: CoachMemorySource
    status: CoachMemoryStatus
    importance: int
    created_at: datetime
    updated_at: datetime
    last_used_at: datetime | None = None


class CoachMemoryListResponse(BaseModel):
    items: list[CoachMemoryResponse]
