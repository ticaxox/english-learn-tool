from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator


class AiMemoryDocumentUpdate(BaseModel):
    """The coach's memory is one editable document, not categorised records."""

    model_config = ConfigDict(extra="forbid")

    content: str = Field(default="", max_length=6000)

    @field_validator("content")
    @classmethod
    def normalise_line_endings(cls, value: str) -> str:
        return value.replace("\r\n", "\n").replace("\r", "\n")


class AiMemoryDocumentResponse(BaseModel):
    content: str
    updated_at: datetime | None
