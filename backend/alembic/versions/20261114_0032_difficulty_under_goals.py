"""the difficulty shelves live under 学习目标

A learner picks one target exam; the shelves for every exam used to sit beside
each other at the top level as if they were all equally relevant. They now sit
inside a single 学习目标 shelf, so the tree says what the difficulty is for.

That makes a difficulty tag legal on a child, so the root-only constraint goes.
Retrieval prunes a branch whose difficulty is not the learner's instead.

Revision ID: 20261114_0032
Revises: 20261114_0031
Create Date: 2026-11-14
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261114_0032"
down_revision: str | Sequence[str] | None = "20261114_0031"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

GOALS_FOLDER_ID = "00000000-0000-4000-8000-000000000002"


def upgrade() -> None:
    op.drop_constraint("difficulty_root_only", "knowledge_folders", type_="check")

    op.execute(
        sa.text(
            "INSERT INTO knowledge_folders (id, scope, owner_id, difficulty, name) "
            f"VALUES ('{GOALS_FOLDER_ID}', 'global', NULL, NULL, '学习目标')"
        )
    )
    # Every difficulty shelf that was a root moves inside it.
    op.execute(
        sa.text(
            "UPDATE knowledge_folders SET parent_id = "
            f"'{GOALS_FOLDER_ID}' "
            "WHERE scope = 'global' AND difficulty IS NOT NULL AND parent_id IS NULL"
        )
    )


def downgrade() -> None:
    op.execute(
        sa.text(
            f"UPDATE knowledge_folders SET parent_id = NULL WHERE parent_id = '{GOALS_FOLDER_ID}'"
        )
    )
    op.execute(sa.text(f"DELETE FROM knowledge_folders WHERE id = '{GOALS_FOLDER_ID}'"))
    op.create_check_constraint(
        "difficulty_root_only", "knowledge_folders", "parent_id IS NULL OR difficulty IS NULL"
    )
