from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

KnowledgeSourceType = Literal["exam"]
KnowledgeStatus = Literal["draft", "indexing", "ready", "failed", "archived"]
KnowledgeScope = Literal["global", "personal"]
KnowledgeDifficulty = Literal["GAOKAO", "CET4", "CET6", "POSTGRAD", "IELTS", "TOEFL"]


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class KnowledgeImportRequest(_StrictModel):
    # Only exam papers are indexed; anything else is rejected, not stored.
    source_type: KnowledgeSourceType = "exam"
    title: str = Field(min_length=1, max_length=200)
    content: str = Field(min_length=1, max_length=400_000)
    metadata: dict[str, Any] = Field(default_factory=dict)
    # The shelf it lands on. Omitted means the general shelf, which is where
    # the old flat list lives.
    folder_id: UUID | None = None


class KnowledgeFolderCreate(_StrictModel):
    name: str = Field(min_length=1, max_length=120)
    # A learner may only create personal shelves; an administrator picks global
    # explicitly, and with a difficulty it becomes that exam's shelf.
    scope: KnowledgeScope = "personal"
    difficulty: KnowledgeDifficulty | None = None
    # Nests under this folder; omitted means a root. A child takes its scope
    # and owner from the parent, so those fields are ignored when this is set.
    parent_id: UUID | None = None


class KnowledgeFolderUpdate(_StrictModel):
    name: str = Field(min_length=1, max_length=120)


class KnowledgeFolderResponse(BaseModel):
    id: UUID
    parent_id: UUID | None = None
    scope: KnowledgeScope
    difficulty: KnowledgeDifficulty | None = None
    name: str
    document_count: int = 0
    writable: bool = False
    # The fallback shelf that holds unclassified papers and cannot be deleted.
    is_general: bool = False
    created_at: datetime
    updated_at: datetime


class KnowledgeFolderListResponse(BaseModel):
    items: list[KnowledgeFolderResponse]


class KnowledgeDocumentUpdate(_StrictModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    content: str | None = Field(default=None, min_length=1, max_length=400_000)
    metadata: dict[str, Any] | None = None
    published: bool | None = None


class KnowledgeDocumentResponse(BaseModel):
    id: UUID
    folder_id: UUID | None = None
    source_type: KnowledgeSourceType
    title: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    status: KnowledgeStatus
    chunk_count: int
    # The opening of the document, so a card can say what it is about without
    # a second request per tile.
    snippet: str = ""
    embedding_model: str | None = None
    error_message: str | None = None
    created_at: datetime
    updated_at: datetime


class KnowledgeDocumentListResponse(BaseModel):
    items: list[KnowledgeDocumentResponse]


class KnowledgeDocumentDetail(KnowledgeDocumentResponse):
    """The document as it is read, not as it is searched."""

    content: str
    folders: str | None = None


class KnowledgeSearchHit(BaseModel):
    document_id: UUID
    title: str
    content: str
    score: float


class KnowledgeSearchResponse(BaseModel):
    items: list[KnowledgeSearchHit]
