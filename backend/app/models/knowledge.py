from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    ARRAY,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

KNOWLEDGE_SOURCE_TYPES = "'exam'"
KNOWLEDGE_STATUSES = "'draft', 'indexing', 'ready', 'failed', 'archived'"
KNOWLEDGE_SCOPES = "'global', 'personal'"
KNOWLEDGE_DIFFICULTIES = "'GAOKAO', 'CET4', 'CET6', 'POSTGRAD', 'IELTS', 'TOEFL'"


class KnowledgeFolder(Base):
    """A shelf a document sits on; shelves nest.

    Two scopes, one table. A global folder belongs to the product: only an
    administrator writes to it. A personal folder belongs to one learner, who
    names it and keeps their own material there; nobody else can read it.

    Nesting is arbitrary. A difficulty is a tag on a *root* folder — CET-4 is
    one shelf, and under it an administrator files 真题 / 词汇 / 解析 as deep as
    it needs to go. A learner's folder nests the same way.

    `scope` and `owner_id` are copied down the tree rather than looked up, so a
    permission check never has to walk to the root; the service keeps the copy
    honest when a folder is created.
    """

    __tablename__ = "knowledge_folders"
    __table_args__ = (
        CheckConstraint(f"scope IN ({KNOWLEDGE_SCOPES})", name="scope_valid"),
        CheckConstraint(
            f"difficulty IS NULL OR difficulty IN ({KNOWLEDGE_DIFFICULTIES})",
            name="difficulty_valid",
        ),
        CheckConstraint(
            "(scope = 'global' AND owner_id IS NULL) "
            "OR (scope = 'personal' AND owner_id IS NOT NULL)",
            name="scope_owner_valid",
        ),
        # A difficulty is a root tag: it decides which exam a whole shelf is
        # for, so it cannot appear halfway down one.
        CheckConstraint("parent_id IS NULL OR difficulty IS NULL", name="difficulty_root_only"),
        Index("ix_knowledge_folders_owner", "scope", "owner_id"),
        Index("ix_knowledge_folders_parent", "parent_id"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    parent_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("knowledge_folders.id", ondelete="CASCADE")
    )
    scope: Mapped[str] = mapped_column(String(16), nullable=False, default="personal")
    owner_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE")
    )
    difficulty: Mapped[str | None] = mapped_column(String(16))
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class KnowledgeDocument(Base):
    """One imported reference document, filed on a folder.

    Wordbooks and coach attachments are deliberately not indexed: a wordbook is
    a SQL record with its own scheduling, and an attachment stays an attachment.
    """

    __tablename__ = "knowledge_documents"
    __table_args__ = (
        CheckConstraint(f"source_type IN ({KNOWLEDGE_SOURCE_TYPES})", name="source_type_valid"),
        CheckConstraint(f"status IN ({KNOWLEDGE_STATUSES})", name="status_valid"),
        CheckConstraint("chunk_count >= 0", name="chunk_count_nonnegative"),
        Index("ix_knowledge_documents_status", "source_type", "status"),
        Index("ix_knowledge_documents_folder", "folder_id"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    # SET NULL, not CASCADE: deleting a shelf must not silently destroy papers;
    # the service moves them to the general shelf instead.
    folder_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("knowledge_folders.id", ondelete="SET NULL")
    )
    source_type: Mapped[str] = mapped_column(String(16), nullable=False, default="exam")
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    # Free-form filters: year, paper, question types, tags.
    metadata_json: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="draft", server_default=text("'draft'")
    )
    chunk_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    embedding_model: Mapped[str | None] = mapped_column(String(120))
    error_message: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class KnowledgeChunk(Base):
    """A searchable slice of a document.

    The vector is a plain float array: a demo-sized corpus (hundreds of chunks)
    is scored in Python, which avoids swapping the database image for pgvector.
    shortcut: linear scan, switch to pgvector once the corpus passes ~20k chunks.
    """

    __tablename__ = "knowledge_chunks"
    __table_args__ = (Index("ix_knowledge_chunks_document", "document_id", "ordinal"),)

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    document_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("knowledge_documents.id", ondelete="CASCADE"),
        nullable=False,
    )
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    embedding: Mapped[list[float] | None] = mapped_column(ARRAY(Float))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
