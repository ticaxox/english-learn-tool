"""give the embedding service its own provider

The embedding model used to be a field on the chat provider, which meant a
learner had to find one service that did both. They are different services:
one writes text, one turns text into vectors. A provider now says which it is,
and the retrieval code asks only the embedding ones.

An existing chat provider that named an embedding_model keeps working — the
retrieval code falls back to it when no dedicated provider exists — so an
upgrade does not silently stop indexing.

Revision ID: 20261113_0029
Revises: 20261112_0028
Create Date: 2026-11-13
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261113_0029"
down_revision: str | Sequence[str] | None = "20261112_0028"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "ai_providers",
        sa.Column(
            "kind",
            sa.String(length=16),
            nullable=False,
            server_default=sa.text("'chat'"),
        ),
    )
    op.create_check_constraint(
        "kind_valid", "ai_providers", "kind IN ('chat', 'embedding')"
    )


def downgrade() -> None:
    op.drop_constraint("kind_valid", "ai_providers", type_="check")
    op.drop_column("ai_providers", "kind")
