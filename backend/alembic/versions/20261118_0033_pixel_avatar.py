"""Remember the pixel avatar chosen in account settings.

Stored as a key, not an image: the eight sprites ship with the frontend, so
the database only has to remember which one the learner picked. Day and night
use the same sprite; the shell swaps its backdrop with the theme.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20261118_0033_pixel_avatar"
down_revision: str | Sequence[str] | None = "20261114_0032"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

AVATARS = (
    "pumpkin",
    "bat",
    "cat",
    "ghost",
    "skull",
    "witch",
    "candle",
    "candy",
)


def upgrade() -> None:
    op.add_column(
        "user_profiles",
        sa.Column(
            "avatar",
            sa.String(length=24),
            nullable=False,
            server_default="pumpkin",
        ),
    )
    op.create_check_constraint(
        "user_profile_avatar_valid",
        "user_profiles",
        "avatar IN (" + ", ".join(f"'{name}'" for name in AVATARS) + ")",
    )


def downgrade() -> None:
    op.drop_constraint("user_profile_avatar_valid", "user_profiles", type_="check")
    op.drop_column("user_profiles", "avatar")
