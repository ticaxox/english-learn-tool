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

AI_TASK_TYPES = (
    "'practice_generation', 'subjective_grading', 'coach_reply', 'challenge_plan', 'json_repair'"
)
AI_JOB_STATUSES = "'queued', 'running', 'succeeded', 'failed', 'cancelled', 'stale'"
AI_QUOTA_KINDS = "'coach_messages', 'question_generation', 'subjective_grading'"
AI_PROMPT_KEYS = (
    "'practice_generation', 'subjective_grading', 'coach_reply', 'challenge_plan', 'json_repair'"
)


class AiProvider(Base):
    __tablename__ = "ai_providers"
    __table_args__ = (
        CheckConstraint("btrim(name) <> ''", name="name_not_blank"),
        CheckConstraint("btrim(name_normalized) <> ''", name="name_normalized_not_blank"),
        CheckConstraint("priority >= 0", name="priority_nonnegative"),
        CheckConstraint("timeout_seconds >= 1 AND timeout_seconds <= 120", name="timeout_range"),
        CheckConstraint(
            "last_test_status IN ('untested', 'succeeded', 'failed')",
            name="last_test_status_valid",
        ),
        CheckConstraint("NOT is_default OR enabled", name="default_must_be_enabled"),
        UniqueConstraint("owner_id", "name_normalized", name="uq_ai_providers_owner_name"),
        Index(
            "uq_ai_providers_owner_default",
            "owner_id",
            unique=True,
            postgresql_where=text("is_default"),
        ),
        Index(
            "ix_ai_providers_owner_enabled_priority",
            "owner_id",
            "enabled",
            "priority",
            "created_at",
        ),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    owner_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    name_normalized: Mapped[str] = mapped_column(String(100), nullable=False)
    base_url: Mapped[str] = mapped_column(String(500), nullable=False)
    api_key_ciphertext: Mapped[str] = mapped_column(Text, nullable=False)
    api_key_mask: Mapped[str] = mapped_column(String(32), nullable=False)
    model_id: Mapped[str] = mapped_column(String(200), nullable=False)
    priority: Mapped[int] = mapped_column(
        Integer, nullable=False, default=100, server_default=text("100")
    )
    is_default: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    timeout_seconds: Mapped[int] = mapped_column(
        Integer, nullable=False, default=60, server_default=text("60")
    )
    enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("true")
    )
    custom_headers: Mapped[dict[str, str]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    last_test_status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="untested", server_default=text("'untested'")
    )
    last_test_error_code: Mapped[str | None] = mapped_column(String(64))
    last_test_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_test_latency_ms: Mapped[int | None] = mapped_column(Integer)
    created_by: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
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


class AiPrompt(Base):
    __tablename__ = "ai_prompts"
    __table_args__ = (
        CheckConstraint(f"prompt_key IN ({AI_PROMPT_KEYS})", name="prompt_key_valid"),
        CheckConstraint("btrim(name) <> ''", name="name_not_blank"),
        CheckConstraint("btrim(template) <> ''", name="template_not_blank"),
        UniqueConstraint("prompt_key", name="uq_ai_prompts_prompt_key"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    prompt_key: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    summary: Mapped[str] = mapped_column(String(500), nullable=False)
    template: Mapped[str] = mapped_column(Text, nullable=False)
    updated_by: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
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


class AiJob(Base):
    __tablename__ = "ai_jobs"
    __table_args__ = (
        CheckConstraint(f"task_type IN ({AI_TASK_TYPES})", name="task_type_valid"),
        CheckConstraint(f"status IN ({AI_JOB_STATUSES})", name="status_valid"),
        CheckConstraint(
            f"quota_kind IS NULL OR quota_kind IN ({AI_QUOTA_KINDS})",
            name="quota_kind_valid",
        ),
        CheckConstraint("attempt_count >= 0", name="attempt_count_nonnegative"),
        CheckConstraint("repair_count >= 0", name="repair_count_nonnegative"),
        UniqueConstraint("user_id", "idempotency_key", name="uq_ai_jobs_user_idempotency"),
        Index("ix_ai_jobs_user_created", "user_id", "created_at"),
        Index("ix_ai_jobs_status_updated", "status", "updated_at"),
        Index("ix_ai_jobs_provider_created", "provider_id", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    task_type: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="queued", server_default=text("'queued'")
    )
    quota_kind: Mapped[str | None] = mapped_column(String(32))
    provider_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("ai_providers.id", ondelete="SET NULL")
    )
    provider_name: Mapped[str | None] = mapped_column(String(100))
    model_id: Mapped[str | None] = mapped_column(String(200))
    prompt_key: Mapped[str] = mapped_column(String(64), nullable=False)
    prompt_snapshot: Mapped[str] = mapped_column(Text, nullable=False)
    input_context: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    result: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    result_summary: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    repair_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_code: Mapped[str | None] = mapped_column(String(64))
    error_message: Mapped[str | None] = mapped_column(String(500))
    retryable: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
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


class AiUsageLedger(Base):
    __tablename__ = "ai_usage_ledger"
    __table_args__ = (
        CheckConstraint(f"quota_kind IN ({AI_QUOTA_KINDS})", name="quota_kind_valid"),
        CheckConstraint("status IN ('reserved', 'consumed', 'released')", name="status_valid"),
        CheckConstraint("reserved >= 0", name="reserved_nonnegative"),
        CheckConstraint("consumed >= 0", name="consumed_nonnegative"),
        CheckConstraint("released >= 0", name="released_nonnegative"),
        UniqueConstraint("job_id", "quota_item", name="uq_ai_usage_ledger_job_item"),
        Index("ix_ai_usage_ledger_user_date_kind", "user_id", "local_date", "quota_kind"),
        Index("ix_ai_usage_ledger_status_updated", "status", "updated_at"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    job_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("ai_jobs.id", ondelete="CASCADE"), nullable=False
    )
    local_date: Mapped[date] = mapped_column(Date, nullable=False)
    quota_kind: Mapped[str] = mapped_column(String(32), nullable=False)
    quota_item: Mapped[str] = mapped_column(
        String(64), nullable=False, default="job", server_default=text("'job'")
    )
    reserved: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default=text("1")
    )
    consumed: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    released: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="reserved", server_default=text("'reserved'")
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


class AiJobEvent(Base):
    __tablename__ = "ai_job_events"
    __table_args__ = (
        Index("ix_ai_job_events_job_created", "job_id", "created_at"),
        Index("ix_ai_job_events_type_created", "event_type", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    job_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("ai_jobs.id", ondelete="CASCADE"), nullable=False
    )
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str | None] = mapped_column(String(16))
    metadata_json: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
