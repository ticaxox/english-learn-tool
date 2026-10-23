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

NOTIFICATION_CATEGORIES = (
    "'due_review', 'today_incomplete', 'streak_risk', 'ai_completed', "
    "'ai_failed', 'plan_adjusted', 'ai_action'"
)
NOTIFICATION_STATUSES = "'pending', 'sent', 'suppressed', 'merged', 'expired'"
OUTBOX_STATUSES = "'pending', 'processed', 'failed'"


class NotificationOutbox(Base):
    __tablename__ = "notification_outbox"
    __table_args__ = (
        CheckConstraint(f"category IN ({NOTIFICATION_CATEGORIES})", name="category_valid"),
        CheckConstraint(f"status IN ({OUTBOX_STATUSES})", name="status_valid"),
        CheckConstraint("attempts >= 0", name="attempts_nonnegative"),
        UniqueConstraint("user_id", "dedupe_key", name="uq_notification_outbox_user_dedupe"),
        Index("ix_notification_outbox_status_available", "status", "available_at"),
        Index("ix_notification_outbox_user_created", "user_id", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    category: Mapped[str] = mapped_column(String(32), nullable=False)
    dedupe_key: Mapped[str] = mapped_column(String(200), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="pending", server_default=text("'pending'")
    )
    attempts: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    available_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_code: Mapped[str | None] = mapped_column(String(64))
    error_message: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class Notification(Base):
    __tablename__ = "notifications"
    __table_args__ = (
        CheckConstraint(f"category IN ({NOTIFICATION_CATEGORIES})", name="category_valid"),
        CheckConstraint(f"status IN ({NOTIFICATION_STATUSES})", name="status_valid"),
        UniqueConstraint("user_id", "dedupe_key", name="uq_notifications_user_dedupe"),
        Index("ix_notifications_user_created", "user_id", "created_at"),
        Index("ix_notifications_user_status_created", "user_id", "status", "created_at"),
        Index("ix_notifications_expiry", "expires_at"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    category: Mapped[str] = mapped_column(String(32), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="pending", server_default=text("'pending'")
    )
    dedupe_key: Mapped[str] = mapped_column(String(200), nullable=False)
    business_ref_type: Mapped[str | None] = mapped_column(String(32))
    business_ref_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    notification_metadata: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    scheduled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    suppressed_reason: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
