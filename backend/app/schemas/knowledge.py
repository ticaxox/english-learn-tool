from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

KnowledgeSourceType = Literal["exam", "wordbook", "upload"]
KnowledgeStatus = Literal["draft", "indexing", "ready", "failed", "archived"]


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class KnowledgeImportRequest(_StrictModel):
    source_type: KnowledgeSourceType = "exam"
    title: str = Field(min_length=1, max_length=200)
    content: str = Field(min_length=1, max_length=400_000)
    metadata: dict[str, Any] = Field(default_factory=dict)


class KnowledgeDocumentUpdate(_StrictModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    content: str | None = Field(default=None, min_length=1, max_length=400_000)
    metadata: dict[str, Any] | None = None
    published: bool | None = None


class KnowledgeDocumentResponse(BaseModel):
    id: UUID
    owner_scoped: bool = False
    source_type: KnowledgeSourceType
    title: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    status: KnowledgeStatus
    chunk_count: int
    embedding_model: str | None = None
    error_message: str | None = None
    created_at: datetime
    updated_at: datetime


class KnowledgeDocumentListResponse(BaseModel):
    items: list[KnowledgeDocumentResponse]


class KnowledgeSearchHit(BaseModel):
    document_id: UUID
    title: str
    content: str
    score: float


class KnowledgeSearchResponse(BaseModel):
    items: list[KnowledgeSearchHit]
