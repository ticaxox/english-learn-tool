"""allow provider timeouts up to 300 seconds

Revision ID: 20261105_0007
Revises: 20261104_0006
Create Date: 2026-11-05

Long practice generators (200-word reading passages) routinely need more than
two minutes with some OpenAI-compatible providers. The API now accepts 1–300
seconds; the stored value is unchanged for existing rows.

Downgrade note: reverting clamps any provider above 120 seconds back to 120 so
the narrower check can be restored.
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "20261105_0007"
down_revision = "20261104_0006"
branch_labels = None
depends_on = None

CONSTRAINT = "ck_ai_providers_timeout_range"


def upgrade() -> None:
    op.drop_constraint(op.f(CONSTRAINT), "ai_providers", type_="check")
    op.create_check_constraint(
        op.f(CONSTRAINT), "ai_providers", "timeout_seconds >= 1 AND timeout_seconds <= 300"
    )


def downgrade() -> None:
    op.execute(sa.text("UPDATE ai_providers SET timeout_seconds = 120 WHERE timeout_seconds > 120"))
    op.drop_constraint(op.f(CONSTRAINT), "ai_providers", type_="check")
    op.create_check_constraint(
        op.f(CONSTRAINT), "ai_providers", "timeout_seconds >= 1 AND timeout_seconds <= 120"
    )
