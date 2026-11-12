"""add coach attachments

Revision ID: 20261106_0013
Revises: 20261105_0012
Create Date: 2026-11-06
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20261106_0013"
down_revision: str | Sequence[str] | None = "20261105_0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "coach_attachments",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "conversation_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("coach_conversations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "message_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("coach_messages.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("filename", sa.String(length=200), nullable=False),
        sa.Column("content_type", sa.String(length=64), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("storage_path", sa.String(length=500), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("size_bytes > 0", name="size_positive"),
    )
    op.create_index(
        "ix_coach_attachments_conversation_created",
        "coach_attachments",
        ["conversation_id", "created_at"],
    )
    op.create_index(
        "ix_coach_attachments_user_created", "coach_attachments", ["user_id", "created_at"]
    )


def downgrade() -> None:
    op.drop_index("ix_coach_attachments_user_created", table_name="coach_attachments")
    op.drop_index("ix_coach_attachments_conversation_created", table_name="coach_attachments")
    op.drop_table("coach_attachments")
