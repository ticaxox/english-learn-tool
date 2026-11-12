"""add personal access tokens

Revision ID: 20261106_0014
Revises: 20261106_0013
Create Date: 2026-11-06
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20261106_0014"
down_revision: str | Sequence[str] | None = "20261106_0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "personal_access_tokens",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(length=80), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("token_prefix", sa.String(length=16), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("token_hash", name="uq_personal_access_tokens_hash"),
    )
    op.create_index(
        "ix_personal_access_tokens_user_created",
        "personal_access_tokens",
        ["user_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_personal_access_tokens_user_created", table_name="personal_access_tokens")
    op.drop_table("personal_access_tokens")
