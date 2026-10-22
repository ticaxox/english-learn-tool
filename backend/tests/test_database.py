from sqlalchemy import text


async def test_alembic_baseline_is_applied_and_session_factory_works(app) -> None:
    async with app.state.session_factory() as session:
        revision = await session.scalar(text("SELECT version_num FROM alembic_version"))
        table_name = await session.scalar(text("SELECT to_regclass('public.system_metadata')"))

    assert revision == "20261022_0001"
    assert table_name == "system_metadata"
