"""knowledge documents live on shelves

The corpus was one flat list that only an administrator could write to. A
learner now keeps their own material too, and the reference papers are filed by
difficulty so a CET-4 learner's coach reads the CET-4 papers rather than the
TOEFL ones.

One table covers both scopes: a folder is global (owner_id NULL, maybe a
difficulty) or personal (owner_id set). Everything imported before this
migration lands on the general shelf — the global folder with no difficulty —
so nothing is lost and an administrator can re-file it.

Revision ID: 20261114_0030
Revises: 20261113_0029
Create Date: 2026-11-14
"""

from collections.abc import Sequence
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20261114_0030"
down_revision: str | Sequence[str] | None = "20261113_0029"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

GENERAL_FOLDER_ID = "00000000-0000-4000-8000-000000000001"

# The shelves every deployment ships with. The difficulty ones are the values
# the practice and profile models already accept.
DIFFICULTIES = [
    ("GAOKAO", "高考"),
    ("CET4", "四级"),
    ("CET6", "六级"),
    ("POSTGRAD", "考研"),
    ("IELTS", "雅思"),
    ("TOEFL", "托福"),
]


def upgrade() -> None:
    op.create_table(
        "knowledge_folders",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "scope", sa.String(length=16), nullable=False, server_default=sa.text("'personal'")
        ),
        sa.Column(
            "owner_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("difficulty", sa.String(length=16), nullable=True),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("scope IN ('global', 'personal')", name="scope_valid"),
        sa.CheckConstraint(
            "difficulty IS NULL OR difficulty IN "
            "('GAOKAO', 'CET4', 'CET6', 'POSTGRAD', 'IELTS', 'TOEFL')",
            name="difficulty_valid",
        ),
        sa.CheckConstraint(
            "(scope = 'global' AND owner_id IS NULL) "
            "OR (scope = 'personal' AND owner_id IS NOT NULL)",
            name="scope_owner_valid",
        ),
    )
    op.create_index("ix_knowledge_folders_owner", "knowledge_folders", ["scope", "owner_id"])

    op.add_column(
        "knowledge_documents",
        sa.Column(
            "folder_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("knowledge_folders.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index("ix_knowledge_documents_folder", "knowledge_documents", ["folder_id"])

    folders = sa.table(
        "knowledge_folders",
        sa.column("id", postgresql.UUID(as_uuid=True)),
        sa.column("scope", sa.String),
        sa.column("owner_id", postgresql.UUID(as_uuid=True)),
        sa.column("difficulty", sa.String),
        sa.column("name", sa.String),
    )
    op.bulk_insert(
        folders,
        [
            {
                "id": GENERAL_FOLDER_ID,
                "scope": "global",
                "owner_id": None,
                "difficulty": None,
                "name": "综合",
            },
            *[
                {
                    "id": str(uuid4()),
                    "scope": "global",
                    "owner_id": None,
                    "difficulty": code,
                    "name": label,
                }
                for code, label in DIFFICULTIES
            ],
        ],
    )

    # Everything that existed before shelves did goes on the general one.
    # The id is a literal because a bind parameter arrives as VARCHAR and
    # Postgres will not compare it to a uuid column.
    op.execute(
        sa.text(
            f"UPDATE knowledge_documents SET folder_id = '{GENERAL_FOLDER_ID}' "
            "WHERE folder_id IS NULL"
        )
    )


def downgrade() -> None:
    op.drop_index("ix_knowledge_documents_folder", table_name="knowledge_documents")
    op.drop_column("knowledge_documents", "folder_id")
    op.drop_index("ix_knowledge_folders_owner", table_name="knowledge_folders")
    op.drop_table("knowledge_folders")
