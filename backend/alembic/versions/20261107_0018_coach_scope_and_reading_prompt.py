"""separate coach histories and tighten the reading prompt

Revision ID: 20261107_0018
Revises: 20261106_0017
Create Date: 2026-11-07
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261107_0018"
down_revision: str | Sequence[str] | None = "20261106_0017"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_SUFFIX = (
    " Give every option a Simplified Chinese gloss in text_zh. For reading practice, "
    "produce exactly one passage that holds every requested question and keep it within "
    "article_min_words to article_max_words; never split one set across several passages. "
    "Make sure each supplied target word appears in its sentence, passage or options."
)


def upgrade() -> None:
    op.add_column(
        "coach_conversations",
        sa.Column(
            "scope", sa.String(length=16), nullable=False, server_default=sa.text("'panel'")
        ),
    )
    op.create_check_constraint(
        "scope_valid", "coach_conversations", "scope IN ('panel', 'page')"
    )
    op.execute(
        "UPDATE ai_prompts SET template = template || '"
        + _SUFFIX
        + "' WHERE prompt_key = 'practice_generation' AND template NOT LIKE '%one passage%'"
    )


def downgrade() -> None:
    op.execute(
        "UPDATE ai_prompts SET template = replace(template, '"
        + _SUFFIX
        + "', '') WHERE prompt_key = 'practice_generation'"
    )
    op.drop_constraint("scope_valid", "coach_conversations", type_="check")
    op.drop_column("coach_conversations", "scope")
