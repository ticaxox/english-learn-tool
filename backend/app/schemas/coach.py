from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

CoachMessageRole = Literal["user", "assistant"]
CoachMessageStatus = Literal["queued", "streaming", "completed", "failed"]
CoachActionStatus = Literal["applied", "undone", "conflict"]
CoachActionType = Literal[
    "adjust_daily_plan",
    "adjust_notification_preferences",
    "start_practice",
    "activate_wordbook",
    "mark_review_focus",
]


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CoachConversationCreate(_StrictModel):
    title: str = Field(default="新的学习对话", min_length=1, max_length=200)
    # "panel" is the floating window, "page" the full-screen coach page.
    scope: Literal["panel", "page"] = "panel"

    @field_validator("title")
    @classmethod
    def title_not_blank(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("title must not be blank")
        return normalized


class CoachConversationPatch(_StrictModel):
    title: str = Field(min_length=1, max_length=200)

    @field_validator("title")
    @classmethod
    def title_not_blank(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("title must not be blank")
        return normalized


class CoachConversationResponse(BaseModel):
    id: UUID
    title: str
    status: Literal["active", "deleted"]
    scope: Literal["panel", "page"] = "panel"
    message_count: int
    last_message_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class CoachConversationListResponse(BaseModel):
    items: list[CoachConversationResponse]
    next_cursor: str | None = None
    has_more: bool = False


class CoachMessageCreate(_StrictModel):
    content: str = Field(max_length=8_000)
    page_context: dict[str, Any] = Field(default_factory=dict)
    attachment_ids: list[UUID] = Field(default_factory=list, max_length=4)

    @field_validator("content")
    @classmethod
    def content_trimmed(cls, value: str) -> str:
        return value.strip()

    @model_validator(mode="after")
    def content_or_attachment(self) -> CoachMessageCreate:
        if not self.content and not self.attachment_ids:
            raise ValueError("content must not be blank")
        return self

    @field_validator("page_context")
    @classmethod
    def safe_context(cls, value: dict[str, Any]) -> dict[str, Any]:
        allowed = {
            "page_route",
            "entity_ids",
            "selected_options",
            "draft",
            "recent_events",
        }
        if set(value) - allowed:
            raise ValueError("page_context contains unsupported keys")
        if len(str(value)) > 20_000:
            raise ValueError("page_context is too large")
        return value


class CoachActionReceiptResponse(BaseModel):
    id: UUID
    message_id: UUID
    action_index: int
    action_type: CoachActionType
    summary: str
    status: CoachActionStatus
    parameters: dict[str, Any] = Field(default_factory=dict)
    before_state: dict[str, Any] = Field(default_factory=dict)
    after_state: dict[str, Any] = Field(default_factory=dict)
    conflict_code: str | None = None
    conflict_message: str | None = None
    created_at: datetime
    expires_at: datetime
    undone_at: datetime | None = None


class CoachAttachmentResponse(BaseModel):
    id: UUID
    filename: str
    content_type: str
    size_bytes: int


class CoachMessageResponse(BaseModel):
    id: UUID
    conversation_id: UUID
    role: CoachMessageRole
    content: str | None = None
    status: CoachMessageStatus
    sequence: int
    error_code: str | None = None
    error_message: str | None = None
    created_at: datetime
    completed_at: datetime | None = None
    actions: list[CoachActionReceiptResponse] = Field(default_factory=list)
    attachments: list[CoachAttachmentResponse] = Field(default_factory=list)


class CoachMessageListResponse(BaseModel):
    items: list[CoachMessageResponse]
    next_cursor: str | None = None
    has_more: bool = False


class CoachAcceptedResponse(BaseModel):
    message_id: UUID
    status: CoachMessageStatus
    stream_url: str


class CoachUndoResponse(BaseModel):
    receipt: CoachActionReceiptResponse
    message: str


class CoachStreamEventResponse(BaseModel):
    id: UUID
    message_id: UUID
    sequence: int
    event_type: str
    data: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime


class CoachDailyPlanActionParameters(_StrictModel):
    new_words: int | None = Field(default=None, ge=5, le=100)
    study_minutes: int | None = Field(default=None, ge=15, le=180)

    @model_validator(mode="after")
    def at_least_one_change(self) -> CoachDailyPlanActionParameters:
        if self.new_words is None and self.study_minutes is None:
            raise ValueError("at least one daily-plan value is required")
        return self


class CoachNotificationPreferencesActionParameters(_StrictModel):
    categories: dict[str, bool] | None = None
    dnd_start: str | None = None
    dnd_end: str | None = None
    daily_limit: int | None = Field(default=None, ge=0, le=20)
    timezone: str | None = None

    @field_validator("categories")
    @classmethod
    def validate_categories(cls, value: dict[str, bool] | None) -> dict[str, bool] | None:
        if value is None:
            return None
        allowed = {
            "due_review",
            "today_incomplete",
            "streak_risk",
            "ai_completed",
            "ai_failed",
            "plan_adjusted",
            "ai_action",
        }
        if set(value) - allowed:
            raise ValueError("categories contains unsupported keys")
        return value

    @model_validator(mode="after")
    def at_least_one_change(self) -> CoachNotificationPreferencesActionParameters:
        if not self.model_fields_set:
            raise ValueError("at least one notification preference is required")
        return self


class CoachActivateWordbookParameters(_StrictModel):
    wordbook_id: UUID


class CoachReviewFocusParameters(_StrictModel):
    entry_id: UUID
    wordbook_id: UUID | None = None
    is_priority: bool = True
