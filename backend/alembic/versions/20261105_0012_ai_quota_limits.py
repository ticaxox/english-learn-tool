"""allow per-user AI quota limits with an unlimited option

Revision ID: 20261105_0012
Revises: 20261105_0011
Create Date: 2026-11-05
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "20261105_0012"
down_revision = "20261105_0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "user_profiles",
        sa.Column(
            "ai_quota_limits",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("user_profiles", "ai_quota_limits")
