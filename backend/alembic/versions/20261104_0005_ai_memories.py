"""add durable AI memories per user

Revision ID: 20261104_0005
Revises: 20261102_0004
Create Date: 2026-11-04
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "20261104_0005"
down_revision = "20261102_0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ai_memories",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("source", sa.String(length=16), server_default=sa.text("'auto'"), nullable=False),
        sa.Column("memory_key", sa.String(length=64), nullable=True),
        sa.Column("pinned", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "kind IN ('profile', 'practice', 'chat', 'preference', 'custom')",
            name="kind_valid",
        ),
        sa.CheckConstraint("source IN ('auto', 'user')", name="source_valid"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "memory_key", name="uq_ai_memories_user_key"),
    )
    op.create_index(
        "ix_ai_memories_user_kind_updated",
        "ai_memories",
        ["user_id", "kind", "updated_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_ai_memories_user_kind_updated", table_name="ai_memories")
    op.drop_table("ai_memories")
