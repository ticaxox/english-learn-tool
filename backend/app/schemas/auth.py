from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.core.security import password_policy_error, validate_username


class LoginRequest(BaseModel):
    username: str = Field(min_length=3, max_length=32)
    password: str = Field(min_length=1, max_length=128)

    @field_validator("username")
    @classmethod
    def username_is_valid(cls, value: str) -> str:
        return validate_username(value)


class ChangePasswordRequest(BaseModel):
    old_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=12, max_length=128)

    @field_validator("new_password")
    @classmethod
    def password_is_valid(cls, value: str) -> str:
        error = password_policy_error(value)
        if error:
            raise ValueError(error)
        return value


class UsernameChangeRequest(BaseModel):
    username: str = Field(min_length=3, max_length=32)
    current_password: str = Field(min_length=1, max_length=128)

    @field_validator("username")
    @classmethod
    def username_is_valid(cls, value: str) -> str:
        return validate_username(value)


class UserSelf(BaseModel):
    model_config = ConfigDict(from_attributes=True)

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


class AuthSessionResponse(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_in: int
    csrf_token: str
    user: UserSelf


class MessageResponse(BaseModel):
    message: str
