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

KNOWLEDGE_SOURCE_TYPES = "'exam', 'wordbook', 'upload'"
KNOWLEDGE_STATUSES = "'draft', 'indexing', 'ready', 'failed', 'archived'"


class KnowledgeDocument(Base):
    """One imported reference document (an exam paper, a shared wordbook export)."""

    __tablename__ = "knowledge_documents"
    __table_args__ = (
        CheckConstraint(f"source_type IN ({KNOWLEDGE_SOURCE_TYPES})", name="source_type_valid"),
        CheckConstraint(f"status IN ({KNOWLEDGE_STATUSES})", name="status_valid"),
        CheckConstraint("chunk_count >= 0", name="chunk_count_nonnegative"),
        Index("ix_knowledge_documents_status", "source_type", "status"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    # NULL means shared reference material; a value means one learner's upload.
    owner_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE")
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
