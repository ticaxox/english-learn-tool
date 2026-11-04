from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

AiMemoryKind = Literal["profile", "practice", "chat", "preference", "custom"]
AiMemorySource = Literal["auto", "user"]

AI_MEMORY_KIND_LABELS: dict[str, str] = {
    "profile": "用户信息",
    "practice": "做题情况",
    "chat": "聊天要点",
    "preference": "习惯偏好",
    "custom": "指定记忆",
}


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class AiMemoryCreateRequest(_StrictModel):
    kind: AiMemoryKind = "custom"
    content: str = Field(min_length=1, max_length=500)

    @field_validator("content")
    @classmethod
    def clean_content(cls, value: str) -> str:
        cleaned = " ".join(value.split())
        if not cleaned:
            raise ValueError("content must not be blank")
        return cleaned


class AiMemoryUpdateRequest(_StrictModel):
    kind: AiMemoryKind | None = None
    content: str | None = Field(default=None, min_length=1, max_length=500)
    pinned: bool | None = None

    @field_validator("content")
    @classmethod
    def clean_content(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = " ".join(value.split())
        if not cleaned:
            raise ValueError("content must not be blank")
        return cleaned


class AiMemoryResponse(BaseModel):
    id: UUID
    kind: AiMemoryKind
    content: str
    source: AiMemorySource
    pinned: bool
    created_at: datetime
    updated_at: datetime
    last_used_at: datetime | None


class AiMemoryListResponse(BaseModel):
    items: list[AiMemoryResponse]
    counts: dict[str, int]


class AiMemoryClearResponse(BaseModel):
    deleted_count: int
