from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


class ImportPreviewRow(BaseModel):
    line_number: int
    username: str
    display_name: str
    department: str | None = None
    learning_group: str | None = None
    status: Literal["valid", "conflict", "error"]
    errors: list[str] = Field(default_factory=list)


class ImportPreviewResponse(BaseModel):
    preview_id: UUID
    preview_hash: str
    expires_at: datetime
    total_rows: int
    valid_rows: int
    invalid_rows: int
    rows: list[ImportPreviewRow]


class ImportConfirmRequest(BaseModel):
    preview_id: UUID
    preview_hash: str = Field(pattern=r"^[0-9a-f]{64}$")


class ImportedUser(BaseModel):
    id: UUID
    username: str
    display_name: str


class ImportCreatedUser(ImportedUser):
    temporary_password: str | None = None


class ImportAcceptedResponse(BaseModel):
    import_id: UUID
    status: Literal["imported", "failed"]
    created_count: int
    created_users: list[ImportCreatedUser]


class ImportStatusResponse(BaseModel):
    import_id: UUID
    status: Literal["previewed", "imported", "failed", "expired"]
    created_count: int
    created_users: list[ImportedUser]
    expires_at: datetime
    used_at: datetime | None = None
