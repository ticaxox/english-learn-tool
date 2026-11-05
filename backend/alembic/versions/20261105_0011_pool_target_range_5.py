"""allow up to five pre-generated sets per combination

Revision ID: 20261105_0011
Revises: 20261105_0010
Create Date: 2026-11-05
"""

from __future__ import annotations

from alembic import op

revision = "20261105_0011"
down_revision = "20261105_0010"
branch_labels = None
depends_on = None

CONSTRAINT = "ck_user_profiles_practice_pool_target_range"


def upgrade() -> None:
    op.drop_constraint(op.f(CONSTRAINT), "user_profiles", type_="check")
    op.create_check_constraint(
        op.f(CONSTRAINT),
        "user_profiles",
        "practice_pool_target >= 0 AND practice_pool_target <= 5",
    )


def downgrade() -> None:
    op.execute("UPDATE user_profiles SET practice_pool_target = 2 WHERE practice_pool_target > 2")
    op.drop_constraint(op.f(CONSTRAINT), "user_profiles", type_="check")
    op.create_check_constraint(
        op.f(CONSTRAINT),
        "user_profiles",
        "practice_pool_target >= 0 AND practice_pool_target <= 2",
    )
