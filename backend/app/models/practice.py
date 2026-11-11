from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

PRACTICE_TYPES = "'fill_blank', 'reading', 'translation', 'writing'"
PRACTICE_SESSION_TYPES = PRACTICE_TYPES + ", 'mixed'"
PRACTICE_SOURCES = "'today_new', 'today_review', 'memory_mistakes', 'whole_book', 'difficulty'"
PRACTICE_SESSION_STATUSES = "'generating', 'ready', 'submitted', 'failed', 'cancelled'"
PRACTICE_GENERATION_STATUSES = "'generating', 'ready', 'failed', 'superseded', 'cancelled'"
PRACTICE_SUBMISSION_STATUSES = "'scoring', 'completed', 'failed'"


class PracticeSession(Base):
    __tablename__ = "practice_sessions"
    __table_args__ = (
        CheckConstraint(f"practice_type IN ({PRACTICE_SESSION_TYPES})", name="practice_type_valid"),
        CheckConstraint(f"source IN ({PRACTICE_SOURCES})", name="source_valid"),
        CheckConstraint(f"status IN ({PRACTICE_SESSION_STATUSES})", name="status_valid"),
        CheckConstraint(
            "difficulty IS NULL OR difficulty IN ("
            "'GAOKAO', 'CET4', 'CET6', 'POSTGRAD', 'IELTS', 'TOEFL')",
            name="difficulty_valid",
        ),
        CheckConstraint(
            "question_count >= 1 AND question_count <= 20", name="question_count_range"
        ),
        CheckConstraint("generation_number >= 1", name="generation_number_positive"),
        CheckConstraint("draft_version >= 0", name="draft_version_nonnegative"),
        CheckConstraint("score IS NULL OR (score >= 0 AND score <= 100)", name="score_range"),
        CheckConstraint(
            "correct_count IS NULL OR correct_count >= 0", name="correct_count_nonnegative"
        ),
        CheckConstraint("wrong_count IS NULL OR wrong_count >= 0", name="wrong_count_nonnegative"),
        UniqueConstraint("user_id", "idempotency_key", name="uq_practice_sessions_user_key"),
        Index("ix_practice_sessions_user_status", "user_id", "status"),
        Index("ix_practice_sessions_user_created", "user_id", "created_at"),
        Index("ix_practice_sessions_wordbook", "wordbook_id"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    practice_type: Mapped[str] = mapped_column(String(16), nullable=False)
    source: Mapped[str] = mapped_column(String(24), nullable=False)
    difficulty: Mapped[str | None] = mapped_column(String(16))
    wordbook_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("wordbooks.id", ondelete="CASCADE")
    )
    question_count: Mapped[int] = mapped_column(Integer, nullable=False)
    is_pool: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="generating", server_default=text("'generating'")
    )
    generation_number: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default=text("1")
    )
    current_generation_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    source_context: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    ai_job_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("ai_jobs.id", ondelete="SET NULL")
    )
    draft_answers: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    draft_version: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    score: Mapped[float | None] = mapped_column(Float)
    correct_count: Mapped[int | None] = mapped_column(Integer)
    wrong_count: Mapped[int | None] = mapped_column(Integer)
    error_code: Mapped[str | None] = mapped_column(String(64))
    error_message: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class PracticeGeneration(Base):
    __tablename__ = "practice_generations"
    __table_args__ = (
        CheckConstraint(f"status IN ({PRACTICE_GENERATION_STATUSES})", name="status_valid"),
        CheckConstraint("generation_number >= 1", name="generation_number_positive"),
        CheckConstraint("question_count >= 0", name="question_count_nonnegative"),
        UniqueConstraint(
            "session_id", "generation_number", name="uq_practice_generations_session_number"
        ),
        Index("ix_practice_generations_session_created", "session_id", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    session_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("practice_sessions.id", ondelete="CASCADE"),
        nullable=False,
    )
    generation_number: Mapped[int] = mapped_column(Integer, nullable=False)
    ai_job_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("ai_jobs.id", ondelete="SET NULL")
    )
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="generating", server_default=text("'generating'")
    )
    question_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    error_code: Mapped[str | None] = mapped_column(String(64))
    error_message: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    ready_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class PracticeQuestion(Base):
    __tablename__ = "practice_questions"
    __table_args__ = (
        CheckConstraint("position >= 0", name="position_nonnegative"),
        CheckConstraint(f"question_type IN ({PRACTICE_TYPES})", name="question_type_valid"),
        UniqueConstraint(
            "generation_id", "position", name="uq_practice_questions_generation_position"
        ),
        Index("ix_practice_questions_generation_position", "generation_id", "position"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    generation_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("practice_generations.id", ondelete="CASCADE"),
        nullable=False,
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    question_type: Mapped[str] = mapped_column(String(16), nullable=False)
    public_payload: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    private_payload: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    target_entry_ids: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class PracticeSubmission(Base):
    __tablename__ = "practice_submissions"
    __table_args__ = (
        CheckConstraint(f"status IN ({PRACTICE_SUBMISSION_STATUSES})", name="status_valid"),
        CheckConstraint("score IS NULL OR (score >= 0 AND score <= 100)", name="score_range"),
        CheckConstraint("correct_count >= 0", name="correct_count_nonnegative"),
        CheckConstraint("total_questions >= 1", name="total_questions_positive"),
        CheckConstraint("wrong_count >= 0", name="wrong_count_nonnegative"),
        UniqueConstraint("user_id", "idempotency_key", name="uq_practice_submissions_user_key"),
        Index("ix_practice_submissions_session_created", "session_id", "created_at"),
        Index("ix_practice_submissions_user_status", "user_id", "status"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    session_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("practice_sessions.id", ondelete="CASCADE"),
        nullable=False,
    )
    user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="scoring", server_default=text("'scoring'")
    )
    answers: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    result: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    score: Mapped[float | None] = mapped_column(Float)
    correct_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_questions: Mapped[int] = mapped_column(Integer, nullable=False)
    wrong_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    ai_job_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("ai_jobs.id", ondelete="SET NULL")
    )
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    error_code: Mapped[str | None] = mapped_column(String(64))
    error_message: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class PracticeEvent(Base):
    __tablename__ = "practice_events"
    __table_args__ = (
        Index("ix_practice_events_user_created", "user_id", "created_at"),
        Index("ix_practice_events_session_created", "session_id", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    session_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("practice_sessions.id", ondelete="CASCADE")
    )
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class PracticeDeletion(Base):
    __tablename__ = "practice_deletions"
    __table_args__ = (
        UniqueConstraint("user_id", "idempotency_key", name="uq_practice_deletions_user_key"),
        Index("ix_practice_deletions_user_created", "user_id", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    result: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class PracticePoolItem(Base):
    """A pre-generated practice session waiting to be claimed.

    The row is deleted the moment the learner starts that session; the session
    itself then behaves like any other practice session. ``attempts`` counts how
    many generations this slot has used so a broken provider cannot loop.
    """

    __tablename__ = "practice_pool_items"
    __table_args__ = (
        CheckConstraint(
            "question_count >= 1 AND question_count <= 20", name="question_count_range"
        ),
        CheckConstraint("attempts >= 1", name="attempts_positive"),
        UniqueConstraint("session_id", name="uq_practice_pool_items_session"),
        Index(
            "ix_practice_pool_items_user_type_count",
            "user_id",
            "practice_type",
            "question_count",
        ),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    practice_type: Mapped[str] = mapped_column(String(16), nullable=False)
    question_count: Mapped[int] = mapped_column(Integer, nullable=False)
    session_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("practice_sessions.id", ondelete="CASCADE"),
        nullable=False,
    )
    attempts: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default=text("1")
    )
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
