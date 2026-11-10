"""badges, node stars and the streak freeze

Revision ID: 20261110_0025
Revises: 20261110_0024
Create Date: 2026-11-10
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20261110_0025"
down_revision: str | Sequence[str] | None = "20261110_0024"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "challenge_node_progress",
        sa.Column("stars", sa.Integer(), nullable=False, server_default=sa.text("0")),
    )
    op.create_check_constraint(
        "stars_range", "challenge_node_progress", "stars >= 0 AND stars <= 3"
    )

    op.add_column(
        "user_game_stats",
        sa.Column("freeze_tokens", sa.Integer(), nullable=False, server_default=sa.text("1")),
    )
    op.add_column("user_game_stats", sa.Column("freeze_granted_month", sa.String(length=7)))
    op.create_check_constraint("freeze_tokens_nonnegative", "user_game_stats", "freeze_tokens >= 0")

    op.create_table(
        "user_achievements",
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("badge_key", sa.String(length=32), primary_key=True),
        sa.Column("unlocked_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_user_achievements_user", "user_achievements", ["user_id", "unlocked_at"])


def downgrade() -> None:
    op.drop_index("ix_user_achievements_user", table_name="user_achievements")
    op.drop_table("user_achievements")
    op.drop_constraint("freeze_tokens_nonnegative", "user_game_stats", type_="check")
    op.drop_column("user_game_stats", "freeze_granted_month")
    op.drop_column("user_game_stats", "freeze_tokens")
    op.drop_constraint("stars_range", "challenge_node_progress", type_="check")
    op.drop_column("challenge_node_progress", "stars")
