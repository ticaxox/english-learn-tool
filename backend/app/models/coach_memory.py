from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

COACH_MEMORY_KINDS = "'preference', 'goal', 'constraint', 'fact', 'note'"
COACH_MEMORY_STATUSES = "'active', 'superseded', 'archived'"
COACH_MEMORY_SOURCES = "'user_explicit', 'coach_inferred', 'imported'"


class CoachMemory(Base):
    """One typed fact the coach may recall.

    Unlike the old single document, each row can be recalled on its own, carries
    its provenance, and is superseded instead of overwritten when it changes.
    """

    __tablename__ = "coach_memories"
    __table_args__ = (
        CheckConstraint(f"kind IN ({COACH_MEMORY_KINDS})", name="kind_valid"),
        CheckConstraint(f"status IN ({COACH_MEMORY_STATUSES})", name="status_valid"),
        CheckConstraint(f"source IN ({COACH_MEMORY_SOURCES})", name="source_valid"),
        Index("ix_coach_memories_user_status", "user_id", "status"),
        # One live memory per subject keeps conflicting facts from piling up.
        Index(
            "uq_coach_memories_active_subject",
            "user_id",
            "subject_key",
            unique=True,
            postgresql_where=text("status = 'active' AND subject_key IS NOT NULL"),
        ),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    subject_key: Mapped[str | None] = mapped_column(String(64))
    content: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[str] = mapped_column(
        String(16), nullable=False, default="user_explicit", server_default=text("'user_explicit'")
    )
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="active", server_default=text("'active'")
    )
    importance: Mapped[int] = mapped_column(
        Integer, nullable=False, default=3, server_default=text("3")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
