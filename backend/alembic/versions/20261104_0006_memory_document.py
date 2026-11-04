"""merge categorised AI memories into one document per user

Revision ID: 20261104_0006
Revises: 20261104_0005
Create Date: 2026-11-04

The product now keeps one editable memory document instead of categorised
records. Existing rows are merged into that document with their category as a
line prefix; the old rows are then removed. The merge is not reversible: the
downgrade keeps the document because the original split cannot be rebuilt.
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "20261104_0006"
down_revision = "20261104_0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.get_bind().execute(
        sa.text(
            """
            INSERT INTO ai_memories
                (id, user_id, kind, content, source, memory_key, pinned, created_at, updated_at)
            SELECT
                gen_random_uuid(),
                user_id,
                'custom',
                string_agg(
                    CASE kind
                        WHEN 'profile' THEN '用户信息：'
                        WHEN 'preference' THEN '习惯偏好：'
                        WHEN 'practice' THEN '做题：'
                        WHEN 'chat' THEN '对话：'
                        ELSE '用户要求：'
                    END || content,
                    E'\\n'
                    ORDER BY created_at, id
                ),
                'auto',
                'memory_document',
                false,
                now(),
                now()
            FROM ai_memories
            WHERE memory_key IS DISTINCT FROM 'memory_document'
            GROUP BY user_id
            ON CONFLICT (user_id, memory_key) DO NOTHING
            """
        )
    )
    op.get_bind().execute(
        sa.text("DELETE FROM ai_memories WHERE memory_key IS DISTINCT FROM 'memory_document'")
    )


def downgrade() -> None:
    # The merged document is kept: the original per-kind rows were removed and
    # cannot be reconstructed without guessing which line came from where.
    pass
