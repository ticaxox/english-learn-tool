"""ask the exercise generator for Chinese writing requirements

Revision ID: 20261105_0010
Revises: 20261105_0009
Create Date: 2026-11-05

Writing prompts stay in English for language practice, but the requirement
list is an instruction for a Chinese learner and should read in Chinese.
Existing generated sets keep their stored text until regenerated.
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "20261105_0010"
down_revision = "20261105_0009"
branch_labels = None
depends_on = None

SUFFIX = (
    " For writing practice, write the requirements list in Simplified Chinese; "
    "keep the writing prompt itself in English."
)


def upgrade() -> None:
    op.execute(
        sa.text(
            "UPDATE ai_prompts SET template = template || :suffix "
            "WHERE prompt_key = 'practice_generation' "
            "AND template NOT LIKE '%requirements list in Simplified Chinese%'"
        ).bindparams(suffix=SUFFIX)
    )


def downgrade() -> None:
    op.execute(
        sa.text(
            "UPDATE ai_prompts SET template = replace(template, :suffix, '') "
            "WHERE prompt_key = 'practice_generation'"
        ).bindparams(suffix=SUFFIX)
    )
