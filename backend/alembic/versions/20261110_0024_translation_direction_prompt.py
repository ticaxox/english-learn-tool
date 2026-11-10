"""tell the generator to honour the translation direction and essay length

Revision ID: 20261110_0024
Revises: 20261110_0023
Create Date: 2026-11-10
"""

from collections.abc import Sequence

from alembic import op

revision: str = "20261110_0024"
down_revision: str | Sequence[str] | None = "20261110_0023"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_OLD = "item must use at least one of its own target words verbatim in its text. "
_NEW = (
    _OLD
    + "For translation practice, follow translation_direction: en_to_zh means every "
    "source_text is English, zh_to_en means every source_text is Chinese, and mixed "
    "alternates the two. For writing practice, size the prompt for writing_target_words "
    "and say the required length inside the Chinese requirements list. "
)


def upgrade() -> None:
    op.execute(
        "UPDATE ai_prompts SET template = replace(template, '"
        + _OLD
        + "', '"
        + _NEW
        + "') WHERE prompt_key = 'practice_generation' AND template LIKE '%" + _OLD + "%'"
    )


def downgrade() -> None:
    op.execute(
        "UPDATE ai_prompts SET template = replace(template, '"
        + _NEW
        + "', '"
        + _OLD
        + "') WHERE prompt_key = 'practice_generation'"
    )
