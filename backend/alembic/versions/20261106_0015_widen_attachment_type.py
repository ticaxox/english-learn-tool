"""widen coach attachment content type

Revision ID: 20261106_0015
Revises: 20261106_0014
Create Date: 2026-11-06
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20261106_0015"
down_revision: str | Sequence[str] | None = "20261106_0014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # The DOCX media type is 71 characters.
    op.alter_column(
        "coach_attachments",
        "content_type",
        existing_type=sa.String(length=64),
        type_=sa.String(length=128),
        existing_nullable=False,
    )


def downgrade() -> None:
    op.alter_column(
        "coach_attachments",
        "content_type",
        existing_type=sa.String(length=128),
        type_=sa.String(length=64),
        existing_nullable=False,
    )
