from __future__ import annotations

from datetime import date, datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
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

WORD_STATE_VALUES = "'new', 'learning', 'review', 'relearning', 'mastered', 'suspended'"
SESSION_MODULE_VALUES = "'flashcard', 'choice', 'spelling'"
PLAN_STATUS_VALUES = "'not_started', 'in_progress', 'completed', 'extra_available'"


class UserWordState(Base):
    """Per-user, per-book memory state. FSRS fields are backend-owned."""

    __tablename__ = "user_word_states"
    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "wordbook_id",
            "entry_id",
            name="uq_user_word_states_user_wordbook_entry",
        ),
        CheckConstraint(f"status IN ({WORD_STATE_VALUES})", name="status_valid"),
        CheckConstraint("lapse_count >= 0", name="lapse_count_nonnegative"),
        CheckConstraint("review_count >= 0", name="review_count_nonnegative"),
        Index("ix_user_word_states_user_wordbook_status", "user_id", "wordbook_id", "status"),
        Index("ix_user_word_states_user_due", "user_id", "due_at"),
        Index("ix_user_word_states_wordbook_entry", "wordbook_id", "entry_id"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    wordbook_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("wordbooks.id", ondelete="CASCADE"),
        nullable=False,
    )
    entry_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("wordbook_entries.id", ondelete="CASCADE"),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="new", server_default=text("'new'")
    )
    fsrs_card: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    algorithm_version: Mapped[str] = mapped_column(String(32), nullable=False)
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    mastered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    suspended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    review_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    lapse_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class MemoryConfig(Base):
    __tablename__ = "memory_configs"

    user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    )
    flashcard_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("true")
    )
    choice_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("true")
    )
    spelling_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("true")
    )
    preferences: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
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


class MemorySession(Base):
    __tablename__ = "memory_sessions"
    __table_args__ = (
        CheckConstraint(f"module IN ({SESSION_MODULE_VALUES})", name="module_valid"),
        CheckConstraint("status IN ('active', 'completed', 'abandoned')", name="status_valid"),
        Index("ix_memory_sessions_user_date", "user_id", "local_date"),
        Index("ix_memory_sessions_user_wordbook_module", "user_id", "wordbook_id", "module"),
        Index(
            "uq_memory_sessions_active",
            "user_id",
            "wordbook_id",
            "module",
            unique=True,
            postgresql_where=text("status = 'active'"),
        ),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    wordbook_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("wordbooks.id", ondelete="CASCADE"),
        nullable=False,
    )
    module: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="active", server_default=text("'active'")
    )
    local_date: Mapped[date] = mapped_column(Date, nullable=False)
    config_snapshot: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    stats: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    calculation_version: Mapped[str] = mapped_column(String(64), nullable=False)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class MemorySessionItem(Base):
    __tablename__ = "memory_session_items"
    __table_args__ = (
        UniqueConstraint("session_id", "entry_id", name="uq_memory_session_items_session_entry"),
        CheckConstraint("reason IN ('new', 'due', 'mistake')", name="reason_valid"),
        CheckConstraint("position >= 0", name="position_nonnegative"),
        CheckConstraint("good_count >= 0", name="good_count_nonnegative"),
        CheckConstraint("again_count >= 0", name="again_count_nonnegative"),
        Index("ix_memory_session_items_session_position", "session_id", "position"),
        Index("ix_memory_session_items_word_state", "word_state_id"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    session_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("memory_sessions.id", ondelete="CASCADE"),
        nullable=False,
    )
    entry_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("wordbook_entries.id", ondelete="CASCADE"),
        nullable=False,
    )
    word_state_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("user_word_states.id", ondelete="CASCADE"),
        nullable=False,
    )
    reason: Mapped[str] = mapped_column(String(16), nullable=False)
    is_extra: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    first_position: Mapped[int] = mapped_column(Integer, nullable=False)
    completed: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    good_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    again_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    relearn_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    next_position: Mapped[int | None] = mapped_column(Integer)
    last_rating: Mapped[str | None] = mapped_column(String(8))
    card_payload: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
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


class MemoryEvent(Base):
    __tablename__ = "memory_events"
    __table_args__ = (
        CheckConstraint(f"module IN ({SESSION_MODULE_VALUES})", name="module_valid"),
        CheckConstraint(
            "event_type IN ('shown', 'answer', 'mastered', 'restore')",
            name="type_valid",
        ),
        CheckConstraint("rating IS NULL OR rating IN ('again', 'good')", name="rating_valid"),
        CheckConstraint("duration_ms >= 0", name="duration_nonnegative"),
        UniqueConstraint(
            "session_id",
            "idempotency_key",
            name="uq_memory_events_session_idempotency",
        ),
        Index("ix_memory_events_user_created", "user_id", "created_at"),
        Index("ix_memory_events_session_created", "session_id", "created_at"),
        Index("ix_memory_events_user_entry_rating", "user_id", "entry_id", "rating"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    session_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("memory_sessions.id", ondelete="CASCADE"),
        nullable=False,
    )
    item_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("memory_session_items.id", ondelete="CASCADE"),
        nullable=False,
    )
    entry_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("wordbook_entries.id", ondelete="CASCADE"),
        nullable=False,
    )
    wordbook_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("wordbooks.id", ondelete="CASCADE"),
        nullable=False,
    )
    module: Mapped[str] = mapped_column(String(16), nullable=False)
    event_type: Mapped[str] = mapped_column(String(16), nullable=False)
    rating: Mapped[str | None] = mapped_column(String(8))
    answer: Mapped[str | None] = mapped_column(Text)
    is_correct: Mapped[bool | None] = mapped_column(Boolean)
    duration_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    request_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    challenge_node_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class DailyPlan(Base):
    __tablename__ = "daily_plans"
    __table_args__ = (
        UniqueConstraint("user_id", "local_date", name="uq_daily_plans_user_local_date"),
        CheckConstraint(f"status IN ({PLAN_STATUS_VALUES})", name="status_valid"),
        CheckConstraint("new_word_target >= 0", name="new_word_target_nonnegative"),
        CheckConstraint(
            "study_minutes_target >= 1 AND study_minutes_target <= 180",
            name="study_minutes_target_range",
        ),
        Index("ix_daily_plans_wordbook", "wordbook_id"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    local_date: Mapped[date] = mapped_column(Date, nullable=False)
    wordbook_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("wordbooks.id", ondelete="CASCADE"),
        nullable=False,
    )
    new_word_target: Mapped[int] = mapped_column(Integer, nullable=False)
    study_minutes_target: Mapped[int] = mapped_column(Integer, nullable=False)
    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    snapshot_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    calculation_version: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="not_started", server_default=text("'not_started'")
    )
    new_word_reason: Mapped[str | None] = mapped_column(String(64))
    stats: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
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


class DailyPlanWord(Base):
    __tablename__ = "daily_plan_words"
    __table_args__ = (
        UniqueConstraint("plan_id", "entry_id", name="uq_daily_plan_words_plan_entry"),
        CheckConstraint("reason IN ('new', 'due')", name="reason_valid"),
        CheckConstraint("position >= 0", name="position_nonnegative"),
        Index("ix_daily_plan_words_plan_reason_position", "plan_id", "reason", "position"),
        Index("ix_daily_plan_words_entry", "entry_id"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    plan_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("daily_plans.id", ondelete="CASCADE"),
        nullable=False,
    )
    entry_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("wordbook_entries.id", ondelete="CASCADE"),
        nullable=False,
    )
    reason: Mapped[str] = mapped_column(String(8), nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    is_extra: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class DailyActivity(Base):
    __tablename__ = "daily_activities"
    __table_args__ = (CheckConstraint("active_seconds >= 0", name="active_seconds_nonnegative"),)

    user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    )
    local_date: Mapped[date] = mapped_column(Date, primary_key=True)
    active_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    heartbeat_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class LearningHeartbeat(Base):
    __tablename__ = "learning_heartbeats"
    __table_args__ = (
        UniqueConstraint("user_id", "idempotency_key", name="uq_learning_heartbeats_user_key"),
        CheckConstraint("credited_seconds >= 0", name="credited_seconds_nonnegative"),
        Index("ix_learning_heartbeats_user_date", "user_id", "local_date"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    local_date: Mapped[date] = mapped_column(Date, nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    credited_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class MistakeFlag(Base):
    __tablename__ = "mistake_flags"
    __table_args__ = (
        UniqueConstraint("user_id", "entry_id", name="uq_mistake_flags_user_entry"),
        CheckConstraint("again_count >= 0", name="again_count_nonnegative"),
        Index("ix_mistake_flags_user_last_again", "user_id", "last_again_at"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    wordbook_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("wordbooks.id", ondelete="CASCADE"),
        nullable=False,
    )
    entry_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("wordbook_entries.id", ondelete="CASCADE"),
        nullable=False,
    )
    again_count: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    last_again_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    is_priority: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
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
