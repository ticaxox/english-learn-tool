from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Wordbook(Base):
    __tablename__ = "wordbooks"
    __table_args__ = (
        CheckConstraint("visibility IN ('organization', 'private')", name="visibility_valid"),
        CheckConstraint(
            "status IN ('importing', 'ready', 'failed', 'deleting', 'deleted')",
            name="status_valid",
        ),
        CheckConstraint(
            "(visibility = 'private' AND owner_id IS NOT NULL) OR "
            "(visibility = 'organization' AND owner_id IS NULL)",
            name="owner_visibility_valid",
        ),
        Index("ix_wordbooks_visibility_status", "visibility", "status"),
        Index("ix_wordbooks_owner_created", "owner_id", "created_at"),
        Index("ix_wordbooks_created_at_id", "created_at", "id"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    visibility: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="importing")
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    owner_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=True,
    )
    created_by: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    version: Mapped[str] = mapped_column(
        String(32), nullable=False, default="1", server_default=text("'1'")
    )
    book_metadata: Mapped[dict[str, Any]] = mapped_column(
        "metadata",
        JSONB,
        nullable=False,
        default=dict,
        server_default=text("'{}'::jsonb"),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class WordbookEntry(Base):
    __tablename__ = "wordbook_entries"
    __table_args__ = (
        UniqueConstraint(
            "wordbook_id",
            "normalized_headword",
            name="uq_wordbook_entries_wordbook_normalized",
        ),
        CheckConstraint("btrim(headword) <> ''", name="headword_not_blank"),
        CheckConstraint("btrim(normalized_headword) <> ''", name="normalized_not_blank"),
        CheckConstraint("sequence >= 0", name="sequence_nonnegative"),
        Index("ix_wordbook_entries_wordbook_sequence", "wordbook_id", "sequence"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    wordbook_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("wordbooks.id", ondelete="CASCADE"),
        nullable=False,
    )
    headword: Mapped[str] = mapped_column(String(200), nullable=False)
    normalized_headword: Mapped[str] = mapped_column(String(200), nullable=False)
    phonetic: Mapped[str | None] = mapped_column(String(200))
    sequence: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class WordbookDefinition(Base):
    __tablename__ = "wordbook_definitions"
    __table_args__ = (
        CheckConstraint("btrim(definition_en) <> ''", name="definition_en_not_blank"),
        CheckConstraint("btrim(definition_zh) <> ''", name="definition_zh_not_blank"),
        CheckConstraint("sequence >= 0", name="sequence_nonnegative"),
        Index("ix_wordbook_definitions_entry_sequence", "entry_id", "sequence"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    entry_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("wordbook_entries.id", ondelete="CASCADE"),
        nullable=False,
    )
    part_of_speech: Mapped[str | None] = mapped_column(String(64))
    definition_en: Mapped[str] = mapped_column(Text, nullable=False)
    definition_zh: Mapped[str] = mapped_column(Text, nullable=False)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class WordbookExample(Base):
    __tablename__ = "wordbook_examples"
    __table_args__ = (
        CheckConstraint("btrim(example_en) <> ''", name="example_en_not_blank"),
        CheckConstraint("sequence >= 0", name="sequence_nonnegative"),
        Index("ix_wordbook_examples_definition_sequence", "definition_id", "sequence"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    definition_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("wordbook_definitions.id", ondelete="CASCADE"),
        nullable=False,
    )
    example_en: Mapped[str] = mapped_column(Text, nullable=False)
    example_zh: Mapped[str | None] = mapped_column(Text)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class WordbookActivation(Base):
    __tablename__ = "wordbook_activations"
    __table_args__ = (Index("ix_wordbook_activations_wordbook", "wordbook_id"),)

    user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    )
    wordbook_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("wordbooks.id", ondelete="CASCADE"),
        nullable=False,
    )
    activated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class WordbookImportPreview(Base):
    __tablename__ = "wordbook_import_previews"
    __table_args__ = (
        CheckConstraint(
            "status IN ('previewed', 'queued', 'processing', 'completed', 'failed', 'expired')",
            name="status_valid",
        ),
        CheckConstraint(
            "requested_visibility IN ('organization', 'private')",
            name="visibility_valid",
        ),
        CheckConstraint("file_size > 0", name="file_size_positive"),
        CheckConstraint("total_rows >= 0", name="total_rows_nonnegative"),
        CheckConstraint("valid_rows >= 0", name="valid_rows_nonnegative"),
        CheckConstraint("warning_count >= 0", name="warning_count_nonnegative"),
        CheckConstraint("error_count >= 0", name="error_count_nonnegative"),
        Index("ix_wordbook_import_previews_owner_expires", "created_by", "expires_at"),
        Index("ix_wordbook_import_previews_wordbook", "wordbook_id"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    created_by: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    wordbook_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("wordbooks.id", ondelete="SET NULL"),
        nullable=True,
    )
    storage_key: Mapped[str] = mapped_column(String(128), nullable=False)
    source_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    file_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    file_size: Mapped[int] = mapped_column(Integer, nullable=False)
    detected_format: Mapped[str] = mapped_column(String(16), nullable=False)
    encoding: Mapped[str] = mapped_column(String(32), nullable=False)
    delimiter: Mapped[str | None] = mapped_column(String(8))
    columns: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb")
    )
    suggested_mapping: Mapped[dict[str, str | None]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    mapping: Mapped[dict[str, str | None]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    ignored_columns: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb")
    )
    sample_rows: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb")
    )
    warnings: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb")
    )
    errors: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb")
    )
    total_rows: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    valid_rows: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    warning_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    preview_token_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    preview_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    requested_name: Mapped[str] = mapped_column(String(200), nullable=False)
    requested_description: Mapped[str | None] = mapped_column(Text)
    requested_visibility: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="previewed", server_default=text("'previewed'")
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class WordbookJob(Base):
    __tablename__ = "wordbook_jobs"
    __table_args__ = (
        CheckConstraint("kind IN ('import', 'export', 'delete')", name="kind_valid"),
        CheckConstraint(
            "status IN ('queued', 'running', 'succeeded', 'failed', 'cancelled')",
            name="status_valid",
        ),
        CheckConstraint(
            "cleanup_status IN ('pending', 'completed', 'failed')",
            name="cleanup_status_valid",
        ),
        CheckConstraint("progress >= 0 AND progress <= 100", name="progress_range_valid"),
        CheckConstraint("attempts >= 0", name="attempts_nonnegative"),
        CheckConstraint("max_attempts >= 1 AND max_attempts <= 5", name="max_attempts_valid"),
        UniqueConstraint(
            "owner_id",
            "kind",
            "idempotency_key",
            name="uq_wordbook_jobs_owner_kind_idempotency",
        ),
        Index("ix_wordbook_jobs_owner_created", "owner_id", "created_at"),
        Index("ix_wordbook_jobs_status_created", "status", "created_at"),
        Index("ix_wordbook_jobs_wordbook", "wordbook_id"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    owner_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="queued", server_default=text("'queued'")
    )
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    request_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    wordbook_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("wordbooks.id", ondelete="SET NULL"),
        nullable=True,
    )
    preview_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("wordbook_import_previews.id", ondelete="SET NULL"),
        nullable=True,
    )
    format: Mapped[str | None] = mapped_column(String(16))
    options: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    progress: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_code: Mapped[str | None] = mapped_column(String(64))
    error_message: Mapped[str | None] = mapped_column(Text)
    result: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    storage_key: Mapped[str | None] = mapped_column(String(128))
    download_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    cleanup_status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="pending", server_default=text("'pending'")
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
