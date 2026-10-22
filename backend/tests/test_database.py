from sqlalchemy import text

IDENTITY_TABLES = (
    "users",
    "user_profiles",
    "refresh_tokens",
    "audit_logs",
    "import_previews",
)


async def test_alembic_baseline_is_applied_and_session_factory_works(app) -> None:
    async with app.state.session_factory() as session:
        revision = await session.scalar(text("SELECT version_num FROM alembic_version"))
        metadata_table = await session.scalar(text("SELECT to_regclass('public.system_metadata')"))
        identity_tables = {
            table_name: await session.scalar(text(f"SELECT to_regclass('public.{table_name}')"))
            for table_name in IDENTITY_TABLES
        }

    assert revision == "20261022_0002"
    assert metadata_table == "system_metadata"
    assert identity_tables == {table_name: table_name for table_name in IDENTITY_TABLES}
