from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.practice import PracticeAnswerInput

ChallengePlanStatus = Literal["generating", "ready", "failed", "completed", "expired"]
ChallengeNodeStatus = Literal["locked", "unlocked", "in_progress", "completed", "failed"]
ChallengeNodeType = Literal[
    "REVIEW", "NEW_WORDS", "WORD_DRILL", "AI_PRACTICE", "BOSS", "OPTIONAL_SIDE"
]


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ChallengeNodeResponse(BaseModel):
    id: UUID
    client_key: str
    node_type: ChallengeNodeType
    order_index: int
    title: str
    description: str
    estimated_minutes: int
    word_entry_ids: list[UUID] = Field(default_factory=list)
    practice_spec: dict[str, Any] = Field(default_factory=dict)
    optional: bool = False
    status: ChallengeNodeStatus
    resource_type: Literal["memory", "practice"] | None = None
    resource_id: UUID | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    error_code: str | None = None
    error_message: str | None = None


class ChallengePlanResponse(BaseModel):
    id: UUID
    local_date: date
    status: ChallengePlanStatus
    title: str | None = None
    summary: str | None = None
    target_minutes: int
    daily_plan_id: UUID
    ai_job_id: UUID | None = None
    generated_at: datetime | None = None
    locked_at: datetime | None = None
    challenge_completed_at: datetime | None = None
    expires_at: datetime
    error_code: str | None = None
    error_message: str | None = None
    main_completed: int = 0
    main_total: int = 0
    map_dsl: str = ""
    nodes: list[ChallengeNodeResponse] = Field(default_factory=list)


class ChallengeGenerateResponse(BaseModel):
    challenge_id: UUID
    status: ChallengePlanStatus
    job_id: UUID | None = None
    status_url: str | None = None
    replayed: bool = False


class ChallengeNodeDetailResponse(BaseModel):
    challenge_id: UUID
    node: ChallengeNodeResponse
    allowed_actions: list[Literal["start", "resume", "view_result"]] = Field(default_factory=list)


class ChallengeStartResponse(BaseModel):
    challenge_id: UUID
    node_id: UUID
    status: ChallengeNodeStatus
    resource_type: Literal["memory", "practice"] | None = None
    resource_id: UUID | None = None
    job_id: UUID | None = None
    message: str


class ChallengeBossSubmitRequest(_StrictModel):
    answers: list[PracticeAnswerInput] = Field(min_length=5, max_length=10)


class ChallengeBossSubmitResponse(BaseModel):
    challenge_id: UUID
    node_id: UUID
    status: Literal["completed", "scoring", "failed"]
    score: float | None = None
    completed: bool = False
    submission_id: UUID | None = None
    result: dict[str, Any] | None = None
    error_code: str | None = None
    error_message: str | None = None
    message: str


class ChallengeHistoryItem(BaseModel):
    id: UUID
    local_date: date
    status: ChallengePlanStatus
    title: str | None = None
    summary: str | None = None
    target_minutes: int
    main_completed: int
    main_total: int
    challenge_completed_at: datetime | None = None


class ChallengeHistoryResponse(BaseModel):
    items: list[ChallengeHistoryItem]
    next_cursor: str | None = None
    has_more: bool = False


class ChallengeJobResponse(BaseModel):
    job_id: UUID
    challenge_id: UUID | None = None
    status: str
    error_code: str | None = None
    error_message: str | None = None
    retryable: bool = False
