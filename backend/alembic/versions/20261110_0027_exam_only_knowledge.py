"""exam-only knowledge base, and one head again

The retrieval base holds exam papers and nothing else: wordbooks are SQL
records with their own scheduling, and a coach attachment stays an attachment.
This also merges the two migration heads the challenge and gamification
branches left behind, so `alembic upgrade head` works again.

Revision ID: 20261110_0027
Revises: 20261110_0026, 844c0d89f737
Create Date: 2026-11-10
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20261110_0027"
down_revision: str | Sequence[str] | None = ("20261110_0026", "844c0d89f737")
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Anything that is not an exam paper leaves the corpus. Chunks carry an
    # ON DELETE CASCADE, but the delete is spelled out so the intent is on the
    # page: these rows are dropped, not archived.
    op.execute(
        "DELETE FROM knowledge_chunks WHERE document_id IN "
        "(SELECT id FROM knowledge_documents WHERE source_type <> 'exam')"
    )
    op.execute("DELETE FROM knowledge_documents WHERE source_type <> 'exam'")

    op.drop_constraint("source_type_valid", "knowledge_documents", type_="check")
    op.create_check_constraint(
        "source_type_valid", "knowledge_documents", "source_type IN ('exam')"
    )

    # Nothing is owner-scoped any more, so the column has no reader left.
    op.drop_index("ix_knowledge_documents_owner", table_name="knowledge_documents")
    op.drop_column("knowledge_documents", "owner_id")


def downgrade() -> None:
    """Re-open the schema. The deleted rows are gone and are not restored."""
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
