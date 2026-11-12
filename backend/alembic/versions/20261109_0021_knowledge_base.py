"""admin-maintained knowledge base with retrieval

Revision ID: 20261109_0021
Revises: 20261109_0020
Create Date: 2026-11-09
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20261109_0021"
down_revision: str | Sequence[str] | None = "20261109_0020"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("ai_providers", sa.Column("embedding_model", sa.String(length=120)))

    op.create_table(
        "knowledge_documents",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "source_type", sa.String(length=16), nullable=False, server_default=sa.text("'exam'")
        ),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column(
            "metadata_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "status", sa.String(length=16), nullable=False, server_default=sa.text("'draft'")
        ),
        sa.Column("chunk_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("embedding_model", sa.String(length=120)),
        sa.Column("error_message", sa.String(length=500)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("source_type IN ('exam', 'wordbook')", name="source_type_valid"),
        sa.CheckConstraint(
            "status IN ('draft', 'indexing', 'ready', 'failed', 'archived')", name="status_valid"
        ),
        sa.CheckConstraint("chunk_count >= 0", name="chunk_count_nonnegative"),
    )
    op.create_index(
        "ix_knowledge_documents_status", "knowledge_documents", ["source_type", "status"]
    )

    op.create_table(
        "knowledge_chunks",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "document_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("knowledge_documents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("embedding", postgresql.ARRAY(sa.Float())),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index("ix_knowledge_chunks_document", "knowledge_chunks", ["document_id", "ordinal"])


def downgrade() -> None:
    op.drop_index("ix_knowledge_chunks_document", table_name="knowledge_chunks")
    op.drop_table("knowledge_chunks")
    op.drop_index("ix_knowledge_documents_status", table_name="knowledge_documents")
    op.drop_table("knowledge_documents")
    op.drop_column("ai_providers", "embedding_model")
