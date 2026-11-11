from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

PracticeType = Literal["fill_blank", "reading", "translation", "writing", "mixed"]
PracticeSource = Literal["today_new", "today_review", "memory_mistakes", "whole_book", "difficulty"]
PracticeSessionStatus = Literal["generating", "ready", "submitted", "failed", "cancelled"]
PracticeSubmissionStatus = Literal["scoring", "completed", "failed"]
Difficulty = Literal["GAOKAO", "CET4", "CET6", "POSTGRAD", "IELTS", "TOEFL"]


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


TranslationDirection = Literal["en_to_zh", "zh_to_en", "mixed"]


class PracticeCreateRequest(_StrictModel):
    practice_type: PracticeType
    source: PracticeSource
    count: int = Field(ge=1, le=20)
    difficulty: Difficulty | None = None
    wordbook_id: UUID | None = None
    # Translation only: which way the sentences run.
    translation_direction: TranslationDirection | None = None
    # Writing only: the essay length the prompt should ask for.
    writing_target_words: int | None = Field(default=None, ge=50, le=300)

    @model_validator(mode="after")
    def validate_request(self) -> PracticeCreateRequest:
        allowed = {1} if self.practice_type == "writing" else {3, 5, 10, 15, 20}
        if self.count not in allowed:
            raise ValueError("count does not match the selected practice type")
        if self.source == "difficulty" and self.difficulty is None:
            raise ValueError("difficulty is required for difficulty-based practice")
        if self.translation_direction is not None and self.practice_type != "translation":
            raise ValueError("translation_direction only applies to translation practice")
        if self.writing_target_words is not None and self.practice_type != "writing":
            raise ValueError("writing_target_words only applies to writing practice")
        return self


class PracticeOptionPublic(BaseModel):
    id: str
    text: str
    text_zh: str | None = None


class PracticeQuestionPublic(BaseModel):
    id: UUID
    position: int
    question_type: PracticeType
    prompt: str | None = None
    sentence: str | None = None
    sentence_zh: str | None = None
    article: str | None = None
    article_zh: str | None = None
    options: list[PracticeOptionPublic] = Field(default_factory=list)
    source_text: str | None = None
    source_language: Literal["en", "zh"] | None = None
    target_language: Literal["en", "zh"] | None = None
    requirements: list[str] = Field(default_factory=list)
    target_entry_ids: list[str] = Field(default_factory=list)
    # Headwords of the words this question was built from, for on-page highlighting.
    target_words: list[str] = Field(default_factory=list)
    # The reference passage this question came from, as "[n] title". Null when the
    # model wrote it from scratch.
    source_citation: str | None = None


class PracticeSessionResponse(BaseModel):
    id: UUID
    practice_type: PracticeType
    source: PracticeSource
    difficulty: Difficulty | None = None
    wordbook_id: UUID | None = None
    translation_direction: TranslationDirection | None = None
    writing_target_words: int | None = None
    status: PracticeSessionStatus
    question_count: int
    generation_number: int
    draft_version: int
    draft_answers: dict[str, str] = Field(default_factory=dict)
    questions: list[PracticeQuestionPublic] = Field(default_factory=list)
    job_status: str | None = None
    error_code: str | None = None
    error_message: str | None = None
    created_at: datetime
    updated_at: datetime


class PracticeDraftRequest(_StrictModel):
    version: int = Field(ge=0)
    answers: dict[str, str] = Field(default_factory=dict, max_length=50)

    @field_validator("answers")
    @classmethod
    def validate_answers(cls, value: dict[str, str]) -> dict[str, str]:
        for key, answer in value.items():
            if len(key) > 64 or len(answer) > 20_000:
                raise ValueError("draft answers exceed the allowed length")
        return value


class PracticeDraftResponse(BaseModel):
    session_id: UUID
    draft_version: int
    answers: dict[str, str]
    saved_at: datetime


class PracticeAnswerInput(BaseModel):
    question_id: str = Field(min_length=1, max_length=64)
    answer: str = Field(min_length=1, max_length=20_000)


class PracticeSubmitRequest(_StrictModel):
    answers: list[PracticeAnswerInput] = Field(min_length=1, max_length=20)

    @model_validator(mode="after")
    def unique_answers(self) -> PracticeSubmitRequest:
        ids = [answer.question_id for answer in self.answers]
        if len(ids) != len(set(ids)):
            raise ValueError("answers must contain each question once")
        return self


class PracticeGradingDimension(BaseModel):
    name: str
    score: float
    max_score: float


class PracticeQuestionResult(BaseModel):
    question_id: str
    question_type: PracticeType
    user_answer: str
    is_correct: bool | None = None
    is_mistake: bool = False
    score: float | None = None
    correct_option_id: str | None = None
    correct_option_text: str | None = None
    explanation: str | None = None
    reference_content: str | None = None
    dimensions: list[PracticeGradingDimension] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    suggestions: list[str] = Field(default_factory=list)


class PracticeResultResponse(BaseModel):
    session_id: UUID
    submission_id: UUID
    status: PracticeSubmissionStatus
    score: float | None = None
    correct_count: int | None = None
    total_questions: int
    wrong_count: int | None = None
    questions: list[PracticeQuestionResult] = Field(default_factory=list)
    mistakes: list[PracticeQuestionResult] = Field(default_factory=list)
    error_code: str | None = None
    error_message: str | None = None
    submitted_at: datetime | None = None


class PracticeSubmitResponse(BaseModel):
    session_id: UUID
    submission_id: UUID
    status: PracticeSubmissionStatus
    result: PracticeResultResponse | None = None
    error_code: str | None = None
    error_message: str | None = None


class PracticeRecordSummary(BaseModel):
    id: UUID
    practice_type: PracticeType
    source: PracticeSource
    difficulty: Difficulty | None = None
    score: float | None = None
    correct_count: int | None = None
    total_questions: int
    wrong_count: int | None = None
    submitted_at: datetime | None = None
    status: PracticeSessionStatus


class PracticeRecordListResponse(BaseModel):
    items: list[PracticeRecordSummary]
    total: int
    offset: int
    limit: int


class PracticeRecordDetail(PracticeRecordSummary):
    result: PracticeResultResponse | None = None


class PracticeDeleteRequest(_StrictModel):
    ids: list[UUID] = Field(min_length=1, max_length=100)


class PracticeDeleteResponse(BaseModel):
    deleted_count: int
    deleted_ids: list[UUID]


class PracticeEventResponse(BaseModel):
    id: UUID
    session_id: UUID | None = None
    event_type: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime


class PracticeEventListResponse(BaseModel):
    items: list[PracticeEventResponse]
    total: int
    offset: int
    limit: int


class BackgroundTaskResponse(BaseModel):
    id: UUID
    practice_type: PracticeType
    question_count: int
    status: Literal["generating", "ready", "failed"]
    attempts: int
    error_code: str | None = None
    error_message: str | None = None
    created_at: datetime
    updated_at: datetime


class BackgroundTaskListResponse(BaseModel):
    items: list[BackgroundTaskResponse]


class PracticeSessionSummary(BaseModel):
    id: UUID
    practice_type: PracticeType
    source: PracticeSource
    status: PracticeSessionStatus
    question_count: int
    score: float | None = None
    created_at: datetime
    submitted_at: datetime | None = None
    error_code: str | None = None
    error_message: str | None = None


class PracticeSessionListResponse(BaseModel):
    items: list[PracticeSessionSummary]
