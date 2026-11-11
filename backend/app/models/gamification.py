from __future__ import annotations

from datetime import date, datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

XP_SOURCES = "'review', 'practice', 'challenge_node', 'boss', 'quest', 'daily_first'"


class UserGameStats(Base):
    """One row per learner: the counters a game loop needs, kept server-side."""

    __tablename__ = "user_game_stats"
    __table_args__ = (
        CheckConstraint("xp >= 0", name="xp_nonnegative"),
        CheckConstraint("crumbs >= 0", name="crumbs_nonnegative"),
        CheckConstraint("level >= 1", name="level_positive"),
        CheckConstraint("streak >= 0", name="streak_nonnegative"),
        CheckConstraint("streak_best >= 0", name="streak_best_nonnegative"),
        CheckConstraint("freeze_tokens >= 0", name="freeze_tokens_nonnegative"),
    )

    user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    )
    xp: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default=text("0"))
    level: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default=text("1"))
    crumbs: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    streak: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    streak_best: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    # One "护身符" per month lets a missed day keep the streak alive.
    freeze_tokens: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default=text("1")
    )
    freeze_granted_month: Mapped[str | None] = mapped_column(String(7))
    last_active_day: Mapped[date | None] = mapped_column(Date)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class XpEvent(Base):
    """Every award, unique per source so a retried request cannot double-count."""

    __tablename__ = "xp_events"
    __table_args__ = (
        CheckConstraint(f"source_type IN ({XP_SOURCES})", name="source_type_valid"),
        UniqueConstraint("user_id", "source_type", "source_id", name="uq_xp_events_user_source"),
        Index("ix_xp_events_user_day", "user_id", "day"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    source_type: Mapped[str] = mapped_column(String(24), nullable=False)
    source_id: Mapped[str] = mapped_column(String(64), nullable=False)
    xp: Mapped[int] = mapped_column(Integer, nullable=False)
    crumbs: Mapped[int] = mapped_column(Integer, nullable=False)
    day: Mapped[date] = mapped_column(Date, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class DailyQuest(Base):
    """The three daily goals, materialised per learner and local day."""

    __tablename__ = "daily_quests"
    __table_args__ = (
        CheckConstraint("progress >= 0", name="progress_nonnegative"),
        CheckConstraint("target >= 1", name="target_positive"),
    )

    user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    )
    day: Mapped[date] = mapped_column(Date, primary_key=True)
    quest_key: Mapped[str] = mapped_column(String(24), primary_key=True)
    progress: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    target: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default=text("1")
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class UserAchievement(Base):
    """A badge that was earned once and stays earned."""

    __tablename__ = "user_achievements"
    __table_args__ = (Index("ix_user_achievements_user", "user_id", "unlocked_at"),)

    user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    )
    badge_key: Mapped[str] = mapped_column(String(32), primary_key=True)
    unlocked_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
