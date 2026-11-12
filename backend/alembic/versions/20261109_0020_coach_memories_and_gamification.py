"""typed coach memories and gamification counters

Revision ID: 20261109_0020
Revises: 20261107_0019
Create Date: 2026-11-09
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20261109_0020"
down_revision: str | Sequence[str] | None = "20261107_0019"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_USER_FK = "users.id"


def upgrade() -> None:
    op.create_table(
        "coach_memories",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey(_USER_FK, ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("subject_key", sa.String(length=64)),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column(
            "source",
            sa.String(length=16),
            nullable=False,
            server_default=sa.text("'user_explicit'"),
        ),
        sa.Column(
            "status", sa.String(length=16), nullable=False, server_default=sa.text("'active'")
        ),
        sa.Column("importance", sa.Integer(), nullable=False, server_default=sa.text("3")),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("last_used_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint(
            "kind IN ('preference', 'goal', 'constraint', 'fact', 'note')", name="kind_valid"
        ),
        sa.CheckConstraint("status IN ('active', 'superseded', 'archived')", name="status_valid"),
        sa.CheckConstraint(
            "source IN ('user_explicit', 'coach_inferred', 'imported')", name="source_valid"
        ),
    )
    op.create_index("ix_coach_memories_user_status", "coach_memories", ["user_id", "status"])
    op.create_index(
        "uq_coach_memories_active_subject",
        "coach_memories",
        ["user_id", "subject_key"],
        unique=True,
        postgresql_where=sa.text("status = 'active' AND subject_key IS NOT NULL"),
    )

    op.create_table(
        "user_game_stats",
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey(_USER_FK, ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("xp", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("level", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.Column("crumbs", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("streak", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("streak_best", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("last_active_day", sa.Date()),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("xp >= 0", name="xp_nonnegative"),
        sa.CheckConstraint("crumbs >= 0", name="crumbs_nonnegative"),
        sa.CheckConstraint("level >= 1", name="level_positive"),
        sa.CheckConstraint("streak >= 0", name="streak_nonnegative"),
        sa.CheckConstraint("streak_best >= 0", name="streak_best_nonnegative"),
    )

    op.create_table(
        "xp_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey(_USER_FK, ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("source_type", sa.String(length=24), nullable=False),
        sa.Column("source_id", sa.String(length=64), nullable=False),
        sa.Column("xp", sa.Integer(), nullable=False),
        sa.Column("crumbs", sa.Integer(), nullable=False),
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "source_type IN ("
            "'review', 'practice', 'challenge_node', 'boss', 'quest', 'daily_first'"
            ")",
            name="source_type_valid",
        ),
        sa.UniqueConstraint("user_id", "source_type", "source_id", name="uq_xp_events_user_source"),
    )
    op.create_index("ix_xp_events_user_day", "xp_events", ["user_id", "day"])

    op.create_table(
        "daily_quests",
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey(_USER_FK, ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("day", sa.Date(), primary_key=True),
        sa.Column("quest_key", sa.String(length=24), primary_key=True),
        sa.Column("progress", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("target", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint("progress >= 0", name="progress_nonnegative"),
        sa.CheckConstraint("target >= 1", name="target_positive"),
    )


def downgrade() -> None:
    op.drop_table("daily_quests")
    op.drop_index("ix_xp_events_user_day", table_name="xp_events")
    op.drop_table("xp_events")
    op.drop_table("user_game_stats")
    op.drop_index("uq_coach_memories_active_subject", table_name="coach_memories")
    op.drop_index("ix_coach_memories_user_status", table_name="coach_memories")
    op.drop_table("coach_memories")
