from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, Field, field_validator

NotificationCategory = Literal[
    "due_review",
    "today_incomplete",
    "streak_risk",
    "ai_completed",
    "ai_failed",
    "plan_adjusted",
    "ai_action",
]
NotificationStatus = Literal["pending", "sent", "suppressed", "merged", "expired"]


class NotificationCategoryPreferences(BaseModel):
    due_review: bool = True
    today_incomplete: bool = True
    streak_risk: bool = True
    ai_completed: bool = True
    ai_failed: bool = True
    plan_adjusted: bool = True
    ai_action: bool = True


class NotificationPreferencesResponse(BaseModel):
    categories: NotificationCategoryPreferences
    dnd_start: str = "22:00"
    dnd_end: str = "08:00"
    daily_limit: int = Field(default=3, ge=0, le=20)
    timezone: str = "Asia/Shanghai"

    @field_validator("dnd_start", "dnd_end")
    @classmethod
    def validate_clock(cls, value: str) -> str:
        parts = value.split(":")
        if len(parts) != 2:
            raise ValueError("time must use HH:MM")
        try:
            hour, minute = int(parts[0]), int(parts[1])
        except ValueError as exc:
            raise ValueError("time must use HH:MM") from exc
        if not (0 <= hour <= 23 and 0 <= minute <= 59):
            raise ValueError("time must use HH:MM")
        return f"{hour:02d}:{minute:02d}"

    @field_validator("timezone")
    @classmethod
    def validate_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except ZoneInfoNotFoundError as exc:
            raise ValueError("timezone must be a valid IANA timezone") from exc
        return value


class NotificationPreferencesUpdate(NotificationPreferencesResponse):
    pass


class NotificationResponse(BaseModel):
    id: UUID
    category: NotificationCategory
    title: str
    body: str
    status: NotificationStatus
    dedupe_key: str
    business_ref_type: str | None = None
    business_ref_id: UUID | None = None
    metadata: dict[str, object] = Field(default_factory=dict)
    scheduled_at: datetime
    sent_at: datetime | None = None
    read_at: datetime | None = None
    expires_at: datetime
    created_at: datetime


class NotificationListResponse(BaseModel):
    items: list[NotificationResponse]
    next_cursor: str | None = None
    has_more: bool = False


class NotificationReadAllResponse(BaseModel):
    updated_count: int


class NotificationUnreadCountResponse(BaseModel):
    unread_count: int


class NotificationPreferencesEnvelope(BaseModel):
    preferences: NotificationPreferencesResponse


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")
