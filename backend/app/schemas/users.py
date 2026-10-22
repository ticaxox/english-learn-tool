from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, model_validator

from app.core.security import password_policy_error, validate_username


class ProfileFields(BaseModel):
    department: str | None = Field(default=None, max_length=100)
    learning_group: str | None = Field(default=None, max_length=100)

    @field_validator("department", "learning_group")
    @classmethod
    def normalize_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None


class AdminUserCreate(ProfileFields):
    username: str = Field(min_length=3, max_length=32)
    display_name: str = Field(min_length=1, max_length=100)
    role: Literal["admin", "member"] = "member"
    password: str | None = Field(default=None, min_length=12, max_length=128)

    @field_validator("username")
    @classmethod
    def username_is_valid(cls, value: str) -> str:
        return validate_username(value)

    @field_validator("display_name")
    @classmethod
    def display_name_is_not_blank(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Display name must not be blank.")
        return normalized

    @field_validator("password")
    @classmethod
    def password_is_valid(cls, value: str | None) -> str | None:
        if value is None:
            return None
        error = password_policy_error(value)
        if error:
            raise ValueError(error)
        return value


class AdminUserPatch(ProfileFields):
    display_name: str | None = Field(default=None, min_length=1, max_length=100)
    role: Literal["admin", "member"] | None = None
    status: Literal["active", "disabled"] | None = None

    @field_validator("display_name")
    @classmethod
    def display_name_is_not_blank(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            raise ValueError("Display name must not be blank.")
        return normalized

    @model_validator(mode="after")
    def at_least_one_change(self) -> "AdminUserPatch":
        if not self.model_fields_set:
            raise ValueError("At least one field must be supplied.")
        return self


class UserSummary(BaseModel):
    id: UUID
    username: str
    display_name: str
    role: Literal["admin", "member"]
    status: Literal["active", "disabled"]
    must_change_password: bool
    department: str | None = None
    learning_group: str | None = None
    last_login_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class UserAggregates(BaseModel):
    active_sessions: int
    audit_events_30d: int
    learning_metrics_available: bool = False
    study_minutes: int | None = None
    completed_tasks: int | None = None
    practice_submissions: int | None = None
    ai_usage_count: int | None = None
    error_rate: float | None = None


class UserDetail(BaseModel):
    account: UserSummary
    aggregates: UserAggregates


class UserListResponse(BaseModel):
    items: list[UserSummary]
    next_cursor: str | None
    has_more: bool


class UserCreateResponse(BaseModel):
    user: UserSummary
    temporary_password: str | None = None


class PasswordResetResponse(BaseModel):
    user_id: UUID
    temporary_password: str
    must_change_password: Literal[True] = True


class DeleteUserResponse(BaseModel):
    message: str
