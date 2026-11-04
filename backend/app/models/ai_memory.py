from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

AI_MEMORY_KINDS = "'profile', 'practice', 'chat', 'preference', 'custom'"
AI_MEMORY_SOURCES = "'auto', 'user'"


class AiMemory(Base):
    """One durable fact the coach may use in later answers.

    ``memory_key`` marks a single auto-refreshed slot (the learner profile and
    the stated preferences); rows without it are append-only notes such as a
    finished practice run, capped per kind by the service layer.
    """

    __tablename__ = "ai_memories"
    __table_args__ = (
        CheckConstraint(f"kind IN ({AI_MEMORY_KINDS})", name="kind_valid"),
        CheckConstraint(f"source IN ({AI_MEMORY_SOURCES})", name="source_valid"),
        UniqueConstraint("user_id", "memory_key", name="uq_ai_memories_user_key"),
        Index("ix_ai_memories_user_kind_updated", "user_id", "kind", "updated_at"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[str] = mapped_column(
        String(16), nullable=False, default="auto", server_default=text("'auto'")
    )
    memory_key: Mapped[str | None] = mapped_column(String(64))
    pinned: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
