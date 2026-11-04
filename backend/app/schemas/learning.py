from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, model_validator

TargetExam = Literal["CET4", "CET6", "POSTGRAD", "IELTS", "TOEFL"]
WordStateStatus = Literal["new", "learning", "review", "relearning", "mastered", "suspended"]
SessionModule = Literal["flashcard", "choice", "spelling"]
PlanStatus = Literal["not_started", "in_progress", "completed", "extra_available"]


class LearningProfileResponse(BaseModel):
    target_exam: TargetExam | None = None
    exam_date: date | None = None
    daily_new_words: int
    daily_study_minutes: int
    department: str | None = None
    learning_group: str | None = None
    timezone: str
    onboarding_completed: bool
    notification_preferences: dict[str, Any] = Field(default_factory=dict)
    updated_at: datetime


class LearningProfilePatch(BaseModel):
    target_exam: TargetExam | None = None
    exam_date: date | None = None
    daily_new_words: int | None = Field(default=None, ge=5, le=100)
    daily_study_minutes: int | None = Field(default=None, ge=15, le=180)
    notification_preferences: dict[str, Any] | None = None
    onboarding_completed: bool | None = None

    @field_validator("exam_date")
    @classmethod
    def exam_date_is_future(cls, value: date | None) -> date | None:
        if value is None:
            return None
        if value < date.today():
            raise ValueError("The exam date must not be in the past.")
        return value

    @model_validator(mode="after")
    def at_least_one_change(self) -> LearningProfilePatch:
        if not self.model_fields_set:
            raise ValueError("At least one field must be supplied.")
        return self


class MemoryModuleConfig(BaseModel):
    flashcard_enabled: bool = True
    choice_enabled: bool = True
    spelling_enabled: bool = True
    preferences: dict[str, Any] = Field(default_factory=dict)


class MemoryConfigResponse(MemoryModuleConfig):
    updated_at: datetime


class MemoryProgressResetResponse(BaseModel):
    sessions_reset: int
    words_reset: int


class PlanWordResponse(BaseModel):
    entry_id: UUID
    headword: str
    phonetic: str | None = None
    definition_zh: str | None = None
    reason: Literal["new", "due"]
    is_extra: bool = False
    position: int
    completed: bool


class PlanSectionProgress(BaseModel):
    target: int
    completed: int
    status: Literal["not_started", "in_progress", "completed"]


class AiPracticeSummary(BaseModel):
    status: Literal["not_available"] = "not_available"
    reason: str = "AI practice is not implemented in this milestone."


class TodayResponse(BaseModel):
    local_date: date
    wordbook_id: UUID
    wordbook_name: str
    status: PlanStatus
    new_words: PlanSectionProgress
    due_reviews: PlanSectionProgress
    ai_practice: AiPracticeSummary = Field(default_factory=AiPracticeSummary)
    new_word_reason: str | None = None
    extra_due_available: bool = False
    extra_due_count: int = 0
    study_minutes_target: int
    active_minutes_today: int
    goal_reached: bool
    calculation_version: str
    generated_at: datetime
    items: list[PlanWordResponse] = Field(default_factory=list)


class HeartbeatRequest(BaseModel):
    session_id: UUID | None = None


class HeartbeatResponse(BaseModel):
    local_date: date
    credited_seconds: int
    active_seconds_today: int
    active_minutes_today: int
    study_minutes_target: int
    goal_reached: bool
    heartbeat_count: int


class StatsSourceBreakdown(BaseModel):
    memory_event_count: int
    heartbeat_seconds: int
    session_count: int


class LearningStatsResponse(BaseModel):
    local_date: date
    active_minutes_today: int
    study_minutes_target: int
    goal_reached: bool
    current_streak_days: int
    new_words_completed_today: int
    due_words_completed_today: int
    total_reviews: int
    sources: StatsSourceBreakdown


class LearningEventResponse(BaseModel):
    event_id: UUID
    event_type: Literal["shown", "answer", "mastered", "restore"]
    module: SessionModule
    rating: Literal["again", "good"] | None = None
    is_correct: bool | None = None
    duration_ms: int
    wordbook_id: UUID
    entry_id: UUID
    session_id: UUID
    created_at: datetime


class LearningEventListResponse(BaseModel):
    items: list[LearningEventResponse]
    next_cursor: str | None = None
    has_more: bool = False


class SessionCreateRequest(BaseModel):
    wordbook_id: UUID | None = None
    module: SessionModule
    limit: int = Field(default=20, ge=1, le=200)


class SessionItemResponse(BaseModel):
    item_id: UUID
    entry_id: UUID
    word_state_id: UUID
    reason: Literal["new", "due", "mistake"]
    is_extra: bool = False
    position: int
    completed: bool
    good_count: int
    again_count: int
    relearn_count: int
    last_rating: Literal["again", "good"] | None = None


class SessionCardPrompt(BaseModel):
    module: SessionModule
    prompt: str
    prompt_label: Literal["headword", "definition", "phonetic", "cloze"]
    cloze: str | None = None
    phonetic: str | None = None
    part_of_speech: str | None = None
    options: list[str] = Field(default_factory=list)
    option_count: int = 0


class SessionResponse(BaseModel):
    session_id: UUID
    module: SessionModule
    status: Literal["active", "completed", "abandoned"]
    wordbook_id: UUID
    wordbook_name: str
    local_date: date
    config_snapshot: dict[str, Any]
    stats: dict[str, Any]
    calculation_version: str
    items_total: int
    items_completed: int
    next_item: SessionItemResponse | None = None
    card: SessionCardPrompt | None = None
    started_at: datetime
    ended_at: datetime | None = None


class SessionEventRequest(BaseModel):
    item_id: UUID
    action: Literal["again", "good", "mastered", "shown"]
    answer: str | None = Field(default=None, max_length=2000)
    duration_ms: int = Field(default=0, ge=0, le=600_000)

    @field_validator("answer")
    @classmethod
    def answer_is_bounded(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized[:2000] if normalized else None


class SessionEventResponse(BaseModel):
    event_id: UUID
    item_id: UUID
    action: Literal["again", "good", "mastered", "shown"]
    rating: Literal["again", "good"] | None = None
    is_correct: bool | None = None
    correct_answer: str | None = None
    item_completed: bool
    session_completed: bool
    session: SessionResponse


class SessionCompleteRequest(BaseModel):
    pass


class WordStateResponse(BaseModel):
    word_state_id: UUID
    entry_id: UUID
    headword: str
    status: WordStateStatus
    due_at: datetime | None = None
    mastered_at: datetime | None = None
    review_count: int
    lapse_count: int
    algorithm_version: str


class MistakeResponse(BaseModel):
    word_state_id: UUID
    entry_id: UUID
    headword: str
    phonetic: str | None = None
    definition_zh: str | None = None
    again_count: int
    last_again_at: datetime
    is_priority: bool
    status: WordStateStatus


class MistakeListResponse(BaseModel):
    items: list[MistakeResponse]
    next_cursor: str | None = None
    has_more: bool = False


class MistakePriorityRequest(BaseModel):
    is_priority: bool
