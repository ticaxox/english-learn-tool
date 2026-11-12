"""tell the generator which words it must use

Revision ID: 20261107_0019
Revises: 20261107_0018
Create Date: 2026-11-07
"""

from collections.abc import Sequence

from alembic import op

revision: str = "20261107_0019"
down_revision: str | Sequence[str] | None = "20261107_0018"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_OLD = "Make sure each supplied target word appears in its sentence, passage or options."
_NEW = (
    "The headwords behind target_entry_ids are listed in target_words; every item "
    "must use at least one of its own target words verbatim in its text."
)


def upgrade() -> None:
    op.execute(
        "UPDATE ai_prompts SET template = replace(template, '"
        + _OLD
        + "', '"
        + _NEW
        + "') WHERE prompt_key = 'practice_generation'"
    )


def downgrade() -> None:
    op.execute(
        "UPDATE ai_prompts SET template = replace(template, '"
        + _NEW
        + "', '"
        + _OLD
        + "') WHERE prompt_key = 'practice_generation'"
    )
