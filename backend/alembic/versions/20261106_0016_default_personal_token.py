"""add default flag to personal access tokens

Revision ID: 20261106_0016
Revises: 20261106_0015
Create Date: 2026-11-06
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261106_0016"
down_revision: str | Sequence[str] | None = "20261106_0015"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "personal_access_tokens",
        sa.Column("is_default", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )


def downgrade() -> None:
    op.drop_column("personal_access_tokens", "is_default")
