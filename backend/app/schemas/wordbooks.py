from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, model_validator

WordbookVisibility = Literal["organization", "private"]
WordbookStatus = Literal["importing", "ready", "failed", "deleting", "deleted"]
WordbookJobStatus = Literal["queued", "running", "succeeded", "failed", "cancelled"]
ExportFormat = Literal["csv", "txt", "pdf"]


class WordbookSummary(BaseModel):
    id: UUID
    visibility: WordbookVisibility
    status: WordbookStatus
    name: str
    description: str | None = None
    owner_id: UUID | None = None
    created_by: UUID | None = None
    version: str
    entry_count: int
    is_active: bool
    created_at: datetime
    updated_at: datetime


class WordbookListResponse(BaseModel):
    items: list[WordbookSummary]
    total: int
    offset: int
    limit: int


class WordbookExampleResponse(BaseModel):
    example_en: str
    example_zh: str | None = None


class WordbookDefinitionResponse(BaseModel):
    part_of_speech: str | None = None
    definition_en: str | None = None
    definition_zh: str | None = None
    examples: list[WordbookExampleResponse] = Field(default_factory=list)


class WordbookEntryResponse(BaseModel):
    id: UUID
    headword: str
    normalized_headword: str
    phonetic: str | None = None
    definitions: list[WordbookDefinitionResponse] = Field(default_factory=list)


class WordbookDetailResponse(BaseModel):
    wordbook: WordbookSummary
    entries: list[WordbookEntryResponse]
    total_entries: int
    offset: int
    limit: int


class WordbookPatchRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=4000)

    @field_validator("name")
    @classmethod
    def name_is_not_blank(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            raise ValueError("The wordbook name must not be blank.")
        return normalized

    @field_validator("description")
    @classmethod
    def description_is_not_blank(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None

    @model_validator(mode="after")
    def at_least_one_change(self) -> WordbookPatchRequest:
        if not self.model_fields_set:
            raise ValueError("At least one field must be supplied.")
        return self


class ActivationResponse(BaseModel):
    wordbook_id: UUID
    is_active: Literal[True] = True
    activated_at: datetime


class ImportPreviewResponse(BaseModel):
    preview_id: UUID
    preview_token: str
    preview_hash: str
    filename: str
    detected_format: Literal["csv", "json", "txt"]
    encoding: str
    delimiter: str | None = None
    columns: list[str]
    suggested_mapping: dict[str, str | None]
    mapping: dict[str, str | None]
    ignored_columns: list[str]
    sample_rows: list[dict[str, Any]]
    total_rows: int
    valid_rows: int
    warning_count: int
    error_count: int
    warnings: list[dict[str, Any]]
    errors: list[dict[str, Any]]
    expires_at: datetime
    status: Literal["previewed", "queued", "processing", "completed", "failed", "expired"]
    requested_name: str
    requested_description: str | None = None
    requested_visibility: WordbookVisibility


class ImportRemapRequest(BaseModel):
    preview_token: str = Field(min_length=20, max_length=256)
    mapping: dict[str, str | None]
    ignored_columns: list[str] = Field(default_factory=list)


class ImportConfirmRequest(BaseModel):
    preview_id: UUID
    preview_token: str = Field(min_length=20, max_length=256)
    preview_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=4000)
    visibility: WordbookVisibility | None = None

    @field_validator("name")
    @classmethod
    def name_is_not_blank(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            raise ValueError("The wordbook name must not be blank.")
        return normalized


class ExportCreateRequest(BaseModel):
    format: ExportFormat
    page_rows: int | None = Field(default=None, ge=1, le=100)
    columns: int | None = Field(default=None, ge=1, le=4)


class DeleteWordbookRequest(BaseModel):
    confirm_name: str | None = Field(default=None, max_length=200)


class WordbookJobResponse(BaseModel):
    job_id: UUID
    kind: Literal["import", "export", "delete"]
    status: WordbookJobStatus
    progress: int = Field(ge=0, le=100)
    wordbook_id: UUID | None = None
    error_code: str | None = None
    error_message: str | None = None
    result: dict[str, Any] = Field(default_factory=dict)
    download_url: str | None = None
    download_expires_at: datetime | None = None
    cleanup_status: Literal["pending", "completed", "failed"]
    created_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None
