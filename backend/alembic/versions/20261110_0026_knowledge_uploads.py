"""private knowledge uploads

Revision ID: 20261110_0026
Revises: 20261110_0025
Create Date: 2026-11-10
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20261110_0026"
down_revision: str | Sequence[str] | None = "20261110_0025"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "knowledge_documents",
        sa.Column(
            "owner_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
        ),
    )
    op.create_index("ix_knowledge_documents_owner", "knowledge_documents", ["owner_id"])
    op.drop_constraint("source_type_valid", "knowledge_documents", type_="check")
    op.create_check_constraint(
        "source_type_valid",
        "knowledge_documents",
        "source_type IN ('exam', 'wordbook', 'upload')",
    )


def downgrade() -> None:
    op.drop_constraint("source_type_valid", "knowledge_documents", type_="check")
    op.create_check_constraint(
        "source_type_valid", "knowledge_documents", "source_type IN ('exam', 'wordbook')"
    )
    op.drop_index("ix_knowledge_documents_owner", table_name="knowledge_documents")
    op.drop_column("knowledge_documents", "owner_id")
