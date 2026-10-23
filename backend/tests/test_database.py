from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import text

IDENTITY_TABLES = (
    "users",
    "user_profiles",
    "refresh_tokens",
    "audit_logs",
    "import_previews",
)
WORDBOOK_TABLES = (
    "wordbooks",
    "wordbook_entries",
    "wordbook_definitions",
    "wordbook_examples",
    "wordbook_activations",
    "wordbook_import_previews",
    "wordbook_jobs",
)
LEARNING_TABLES = (
    "user_word_states",
    "memory_configs",
    "memory_sessions",
    "memory_session_items",
    "memory_events",
    "daily_plans",
    "daily_plan_words",
    "daily_activities",
    "learning_heartbeats",
    "mistake_flags",
)


def _head_revision() -> str:
    backend_dir = Path(__file__).resolve().parents[1]
    config = Config(str(backend_dir / "alembic.ini"))
    config.set_main_option("script_location", str(backend_dir / "alembic"))
    head = ScriptDirectory.from_config(config).get_current_head()
    if head is None:  # pragma: no cover - defensive
        raise AssertionError("The Alembic script directory has no head revision.")
    return head


async def test_alembic_baseline_is_applied_and_session_factory_works(app) -> None:
    tables = IDENTITY_TABLES + WORDBOOK_TABLES + LEARNING_TABLES
    async with app.state.session_factory() as session:
        revision = await session.scalar(text("SELECT version_num FROM alembic_version"))
        metadata_table = await session.scalar(text("SELECT to_regclass('public.system_metadata')"))
        found_tables = {
            table_name: await session.scalar(text(f"SELECT to_regclass('public.{table_name}')"))
            for table_name in tables
        }

    assert revision == _head_revision()
    assert metadata_table == "system_metadata"
    assert found_tables == {table_name: table_name for table_name in tables}
