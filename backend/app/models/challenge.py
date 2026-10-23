from __future__ import annotations

from datetime import date, datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Float,
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

CHALLENGE_PLAN_STATUSES = "'generating', 'ready', 'failed', 'completed', 'expired'"
CHALLENGE_NODE_STATUSES = "'locked', 'unlocked', 'in_progress', 'completed', 'failed'"
CHALLENGE_NODE_TYPES = "'REVIEW', 'NEW_WORDS', 'WORD_DRILL', 'AI_PRACTICE', 'BOSS', 'OPTIONAL_SIDE'"


class DailyChallengePlan(Base):
    __tablename__ = "daily_challenge_plans"
    __table_args__ = (
        UniqueConstraint("user_id", "local_date", name="uq_daily_challenge_plans_user_date"),
        CheckConstraint(f"status IN ({CHALLENGE_PLAN_STATUSES})", name="status_valid"),
        CheckConstraint(
            "target_minutes >= 15 AND target_minutes <= 180", name="target_minutes_range"
        ),
        CheckConstraint("generation_attempts >= 0", name="generation_attempts_nonnegative"),
        Index("ix_daily_challenge_plans_user_date_status", "user_id", "local_date", "status"),
        Index("ix_daily_challenge_plans_expiry", "expires_at"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    local_date: Mapped[date] = mapped_column(Date, nullable=False)
    daily_plan_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("daily_plans.id", ondelete="CASCADE"), nullable=False
    )
    wordbook_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("wordbooks.id", ondelete="CASCADE"), nullable=False
    )
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="generating", server_default=text("'generating'")
    )
    title: Mapped[str | None] = mapped_column(String(200))
    summary: Mapped[str | None] = mapped_column(Text)
    target_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    ai_job_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("ai_jobs.id", ondelete="SET NULL")
    )
    generation_attempts: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    generated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    locked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    challenge_completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    error_code: Mapped[str | None] = mapped_column(String(64))
    error_message: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class ChallengeNode(Base):
    __tablename__ = "challenge_nodes"
    __table_args__ = (
        UniqueConstraint("plan_id", "order_index", name="uq_challenge_nodes_plan_order"),
        UniqueConstraint("plan_id", "client_key", name="uq_challenge_nodes_plan_client_key"),
        CheckConstraint(f"node_type IN ({CHALLENGE_NODE_TYPES})", name="node_type_valid"),
        CheckConstraint("order_index >= 0", name="order_nonnegative"),
        CheckConstraint(
            "estimated_minutes >= 1 AND estimated_minutes <= 120", name="minutes_range"
        ),
        Index("ix_challenge_nodes_plan_order", "plan_id", "order_index"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    plan_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("daily_challenge_plans.id", ondelete="CASCADE"),
        nullable=False,
    )
    client_key: Mapped[str] = mapped_column(String(64), nullable=False)
    node_type: Mapped[str] = mapped_column(String(20), nullable=False)
    order_index: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    estimated_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    word_entry_ids: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb")
    )
    practice_spec: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    optional: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class ChallengeNodeProgress(Base):
    __tablename__ = "challenge_node_progress"
    __table_args__ = (
        UniqueConstraint("node_id", name="uq_challenge_node_progress_node"),
        CheckConstraint(f"status IN ({CHALLENGE_NODE_STATUSES})", name="status_valid"),
        Index("ix_challenge_node_progress_plan_status", "plan_id", "status"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    node_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("challenge_nodes.id", ondelete="CASCADE"), nullable=False
    )
    plan_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("daily_challenge_plans.id", ondelete="CASCADE"),
        nullable=False,
    )
    user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="locked", server_default=text("'locked'")
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    memory_session_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("memory_sessions.id", ondelete="SET NULL")
    )
    practice_session_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("practice_sessions.id", ondelete="SET NULL")
    )
    error_code: Mapped[str | None] = mapped_column(String(64))
    error_message: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class ChallengePlanContext(Base):
    __tablename__ = "challenge_plan_contexts"
    __table_args__ = (
        UniqueConstraint("plan_id", name="uq_challenge_plan_contexts_plan"),
        Index("ix_challenge_plan_contexts_expiry", "expires_at"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    plan_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("daily_challenge_plans.id", ondelete="CASCADE"),
        nullable=False,
    )
    user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    context: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class ChallengeBossResult(Base):
    __tablename__ = "challenge_boss_results"
    __table_args__ = (
        UniqueConstraint("plan_id", name="uq_challenge_boss_results_plan"),
        CheckConstraint("score IS NULL OR (score >= 0 AND score <= 100)", name="score_range"),
        Index("ix_challenge_boss_results_user_submitted", "user_id", "submitted_at"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    plan_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("daily_challenge_plans.id", ondelete="CASCADE"),
        nullable=False,
    )
    node_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("challenge_nodes.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    practice_submission_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("practice_submissions.id", ondelete="SET NULL")
    )
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    score: Mapped[float | None] = mapped_column(Float)
    question_stats: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    answer_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    submitted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
