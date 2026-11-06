from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class PersonalTokenCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=80)

    @field_validator("name")
    @classmethod
    def name_not_blank(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("name must not be blank")
        return normalized


class PersonalTokenResponse(BaseModel):
    id: UUID
    name: str
    prefix: str
    created_at: datetime
    last_used_at: datetime | None = None
    revoked_at: datetime | None = None


class PersonalTokenCreated(PersonalTokenResponse):
    token: str


class PersonalTokenListResponse(BaseModel):
    items: list[PersonalTokenResponse]
