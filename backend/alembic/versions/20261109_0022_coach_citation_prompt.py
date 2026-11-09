"""ask the coach to cite retrieved snippets

Revision ID: 20261109_0022
Revises: 20261109_0021
Create Date: 2026-11-09
"""

from collections.abc import Sequence

from alembic import op

revision: str = "20261109_0022"
down_revision: str | Sequence[str] | None = "20261109_0021"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_OLD = "otherwise leave actions empty and answer with text only."
_NEW = (
    "otherwise leave actions empty and answer with text only. When knowledge_snippets "
    "is present, ground the answer in them and cite the bracket number, e.g. [1]; "
    "never cite a number that is not supplied."
)


def upgrade() -> None:
    op.execute(
        "UPDATE ai_prompts SET template = replace(template, '"
        + _OLD
        + "', '"
        + _NEW
        + "') WHERE prompt_key = 'coach_reply'"
    )


def downgrade() -> None:
    op.execute(
        "UPDATE ai_prompts SET template = replace(template, '"
        + _NEW
        + "', '"
        + _OLD
        + "') WHERE prompt_key = 'coach_reply'"
    )
