"""collapse practice pool targets into one inventory value

Revision ID: 20261105_0009
Revises: 20261105_0008
Create Date: 2026-11-05

The pre-generation inventory is now one number applied to every practice type
and question count instead of a per-type/per-count map. Existing maps are
collapsed to their largest configured value (capped at 2).
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "20261105_0009"
down_revision = "20261105_0008"
branch_labels = None
depends_on = None

CONSTRAINT = "ck_user_profiles_practice_pool_target_range"


def upgrade() -> None:
    op.add_column(
        "user_profiles",
        sa.Column(
            "practice_pool_target", sa.Integer(), server_default=sa.text("0"), nullable=False
        ),
    )
    op.execute(
        sa.text(
            """
            UPDATE user_profiles AS profile
            SET practice_pool_target = LEAST(
                2,
                COALESCE(
                    (
                        SELECT MAX(per_count.value::int)
                        FROM jsonb_each(profile.practice_pool_targets) AS per_type,
                             jsonb_each_text(per_type.value) AS per_count
                    ),
                    0
                )
            )
            WHERE profile.practice_pool_targets <> '{}'::jsonb
            """
        )
    )
    op.create_check_constraint(
        op.f(CONSTRAINT),
        "user_profiles",
        "practice_pool_target >= 0 AND practice_pool_target <= 2",
    )
    op.drop_column("user_profiles", "practice_pool_targets")


def downgrade() -> None:
    op.add_column(
        "user_profiles",
        sa.Column(
            "practice_pool_targets",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
    )
    op.drop_constraint(op.f(CONSTRAINT), "user_profiles", type_="check")
    op.drop_column("user_profiles", "practice_pool_target")
