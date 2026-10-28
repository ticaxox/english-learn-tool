"""move AI providers to per-user ownership

Revision ID: 20261028_0003
Revises: 844c0d89f737
Create Date: 2026-10-28
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "20261028_0003"
down_revision = "844c0d89f737"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_index(
        "uq_ai_providers_single_default",
        table_name="ai_providers",
        postgresql_where=sa.text("is_default"),
    )
    op.drop_constraint("uq_ai_providers_name_normalized", "ai_providers", type_="unique")
    op.drop_index("ix_ai_providers_enabled_priority", table_name="ai_providers")
    op.add_column("ai_providers", sa.Column("owner_id", sa.UUID(), nullable=True))
    op.execute(
        """
        UPDATE ai_providers AS provider
        SET owner_id = provider.created_by
        WHERE provider.owner_id IS NULL
          AND provider.created_by IS NOT NULL
        """
    )
    op.execute(
        """
        UPDATE ai_providers AS provider
        SET owner_id = fallback.id
        FROM (
            SELECT id
            FROM users
            WHERE role = 'admin'
            ORDER BY created_at, id
            LIMIT 1
        ) AS fallback
        WHERE provider.owner_id IS NULL
        """
    )
    # No safe ownership can be inferred for a provider without a creator or administrator.
    op.execute("DELETE FROM ai_providers WHERE owner_id IS NULL")
    op.create_foreign_key(
        "fk_ai_providers_owner_id_users",
        "ai_providers",
        "users",
        ["owner_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.alter_column(
        "ai_providers",
        "owner_id",
        existing_type=sa.UUID(),
        nullable=False,
    )
    op.create_unique_constraint(
        "uq_ai_providers_owner_name",
        "ai_providers",
        ["owner_id", "name_normalized"],
    )
    op.create_index(
        "uq_ai_providers_owner_default",
        "ai_providers",
        ["owner_id"],
        unique=True,
        postgresql_where=sa.text("is_default"),
    )
    op.create_index(
        "ix_ai_providers_owner_enabled_priority",
        "ai_providers",
        ["owner_id", "enabled", "priority", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.execute(
        """
        WITH ranked AS (
            SELECT id, row_number() OVER (ORDER BY created_at, id) AS position
            FROM ai_providers
            WHERE is_default
        )
        UPDATE ai_providers AS provider
        SET is_default = false
        FROM ranked
        WHERE provider.id = ranked.id
          AND ranked.position > 1
        """
    )
    op.execute(
        """
        WITH ranked AS (
            SELECT
                id,
                row_number() OVER (
                    PARTITION BY name_normalized
                    ORDER BY created_at, id
                ) AS position
            FROM ai_providers
        )
        UPDATE ai_providers AS provider
        SET
            name = left(provider.name, 91) || '|' || left(provider.id::text, 8),
            name_normalized = left(provider.name_normalized, 91)
                || '|' || left(provider.id::text, 8)
        FROM ranked
        WHERE provider.id = ranked.id
          AND ranked.position > 1
        """
    )
    op.drop_index("ix_ai_providers_owner_enabled_priority", table_name="ai_providers")
    op.drop_index(
        "uq_ai_providers_owner_default",
        table_name="ai_providers",
        postgresql_where=sa.text("is_default"),
    )
    op.drop_constraint("uq_ai_providers_owner_name", "ai_providers", type_="unique")
    op.drop_constraint("fk_ai_providers_owner_id_users", "ai_providers", type_="foreignkey")
    op.drop_column("ai_providers", "owner_id")
    op.create_unique_constraint(
        "uq_ai_providers_name_normalized",
        "ai_providers",
        ["name_normalized"],
    )
    op.create_index(
        "uq_ai_providers_single_default",
        "ai_providers",
        ["is_default"],
        unique=True,
        postgresql_where=sa.text("is_default"),
    )
    op.create_index(
        "ix_ai_providers_enabled_priority",
        "ai_providers",
        ["enabled", "priority", "created_at"],
        unique=False,
    )
