"""allow the gaokao difficulty

Revision ID: 20261110_0023
Revises: 20261109_0022
Create Date: 2026-11-10
"""

from collections.abc import Sequence

from alembic import op

revision: str = "20261110_0023"
down_revision: str | Sequence[str] | None = "20261109_0022"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_OLD = "'CET4', 'CET6', 'POSTGRAD', 'IELTS', 'TOEFL'"
_NEW = "'GAOKAO', " + _OLD

# The exam check was declared on the model but never migrated, so the old
# constraint may be absent; IF EXISTS keeps the upgrade safe either way.
_DROP_EXAM = (
    "ALTER TABLE user_profiles DROP CONSTRAINT IF EXISTS "
    "ck_user_profiles_user_profile_target_exam_valid"
)
_ADD_EXAM = (
    "ALTER TABLE user_profiles ADD CONSTRAINT "
    "ck_user_profiles_user_profile_target_exam_valid "
    "CHECK (target_exam IS NULL OR target_exam IN (%s))"
)
_DROP_DIFFICULTY = (
    "ALTER TABLE practice_sessions DROP CONSTRAINT IF EXISTS ck_practice_sessions_difficulty_valid"
)
_ADD_DIFFICULTY = (
    "ALTER TABLE practice_sessions ADD CONSTRAINT "
    "ck_practice_sessions_difficulty_valid "
    "CHECK (difficulty IS NULL OR difficulty IN (%s))"
)


def upgrade() -> None:
    op.execute(_DROP_EXAM)
    op.execute(_ADD_EXAM % _NEW)
    op.execute(_DROP_DIFFICULTY)
    op.execute(_ADD_DIFFICULTY % _NEW)


def downgrade() -> None:
    op.execute(_DROP_DIFFICULTY)
    op.execute(_ADD_DIFFICULTY % _OLD)
    op.execute(_DROP_EXAM)
    op.execute(_ADD_EXAM % _OLD)
