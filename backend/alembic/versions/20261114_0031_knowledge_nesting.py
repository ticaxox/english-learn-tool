"""knowledge shelves nest

A difficulty shelf is a shelf, not the only kind: under 四级 there is 真题,
under that 2023, and a learner's own folder nests the same way. Folders get a
parent, and a difficulty is only allowed on a root — it decides which exam a
whole shelf is for, so it cannot appear halfway down one.

Every existing folder is a root, so the migration only adds the column.

Revision ID: 20261114_0031
Revises: 20261114_0030
Create Date: 2026-11-14
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20261114_0031"
down_revision: str | Sequence[str] | None = "20261114_0030"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "knowledge_folders",
        sa.Column(
            "parent_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("knowledge_folders.id", ondelete="CASCADE"),
            nullable=True,
        ),
    )
    op.create_index("ix_knowledge_folders_parent", "knowledge_folders", ["parent_id"])
    op.create_check_constraint(
        "difficulty_root_only", "knowledge_folders", "parent_id IS NULL OR difficulty IS NULL"
    )


def downgrade() -> None:
    op.drop_constraint("difficulty_root_only", "knowledge_folders", type_="check")
    op.drop_index("ix_knowledge_folders_parent", table_name="knowledge_folders")
    op.drop_column("knowledge_folders", "parent_id")
