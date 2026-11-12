"""allow mixed practice sessions

Revision ID: 20261106_0017
Revises: 20261106_0016
Create Date: 2026-11-07
"""

from collections.abc import Sequence

from alembic import op

revision: str = "20261106_0017"
down_revision: str | Sequence[str] | None = "20261106_0016"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TYPES = "'fill_blank', 'reading', 'translation', 'writing', 'mixed'"
_OLD_TYPES = "'fill_blank', 'reading', 'translation', 'writing'"
_SUFFIX = (
    " If practice_type is mixed, include several of fill_blank, reading, translation "
    "and writing in one set and keep the total question count exact."
)


def upgrade() -> None:
    op.execute(
        "ALTER TABLE practice_sessions DROP CONSTRAINT ck_practice_sessions_practice_type_valid"
    )
    op.execute(
        "ALTER TABLE practice_sessions ADD CONSTRAINT "
        "ck_practice_sessions_practice_type_valid "
        f"CHECK (practice_type IN ({_TYPES}))"
    )
    op.execute(
        "UPDATE ai_prompts SET template = template || '"
        + _SUFFIX
        + "' WHERE prompt_key = 'practice_generation'"
        + " AND template NOT LIKE '%practice_type is mixed%'"
    )


def downgrade() -> None:
    op.execute(
        "UPDATE ai_prompts SET template = replace(template, '"
        + _SUFFIX
        + "', '') WHERE prompt_key = 'practice_generation'"
    )
    op.execute(
        "ALTER TABLE practice_sessions DROP CONSTRAINT ck_practice_sessions_practice_type_valid"
    )
    op.execute(
        "ALTER TABLE practice_sessions ADD CONSTRAINT "
        "ck_practice_sessions_practice_type_valid "
        f"CHECK (practice_type IN ({_OLD_TYPES}))"
    )
