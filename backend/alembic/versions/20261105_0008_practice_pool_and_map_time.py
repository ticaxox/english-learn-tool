"""add pre-generated practice pool and daily map generation time

Revision ID: 20261105_0008
Revises: 20261105_0007
Create Date: 2026-11-05

Adds:
- practice_sessions.is_pool to mark pre-generated sessions;
- practice_pool_items to track the ready/in-flight pool slots and retries;
- user_profiles.practice_pool_targets (per type/count wanted inventory);
- user_profiles.challenge_generation_time ("HH:MM", local day) for the
  scheduled learning-map generation.

Downgrade drops the pool table and the two profile columns. Claimed pool
sessions remain ordinary rows; only unclaimed pool sessions lose their marker.
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "20261105_0008"
down_revision = "20261105_0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "practice_sessions",
        sa.Column("is_pool", sa.Boolean(), server_default=sa.text("false"), nullable=False),
    )
    op.add_column(
        "user_profiles",
        sa.Column(
            "practice_pool_targets",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
    )
    op.add_column(
        "user_profiles",
        sa.Column("challenge_generation_time", sa.String(length=5), nullable=True),
    )
    op.create_table(
        "practice_pool_items",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("practice_type", sa.String(length=16), nullable=False),
        sa.Column("question_count", sa.Integer(), nullable=False),
        sa.Column("session_id", sa.UUID(), nullable=False),
        sa.Column("attempts", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "question_count >= 1 AND question_count <= 20", name="question_count_range"
        ),
        sa.CheckConstraint("attempts >= 1", name="attempts_positive"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["session_id"], ["practice_sessions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("session_id", name="uq_practice_pool_items_session"),
    )
    op.create_index(
        "ix_practice_pool_items_user_type_count",
        "practice_pool_items",
        ["user_id", "practice_type", "question_count"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_practice_pool_items_user_type_count", table_name="practice_pool_items")
    op.drop_table("practice_pool_items")
    op.drop_column("user_profiles", "challenge_generation_time")
    op.drop_column("user_profiles", "practice_pool_targets")
    op.drop_column("practice_sessions", "is_pool")
