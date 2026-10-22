from sqlalchemy import select

from app.models.system import SystemMetadata

DATABASE_PROBE_KEY = "qa-isolation-regression-database"
REDIS_PROBE_KEY = "qa-isolation-regression-redis"


async def test_01_stateful_probe_writes_are_committed_for_the_current_test(app) -> None:
    async with app.state.session_factory() as session:
        existing = await session.scalar(
            select(SystemMetadata).where(SystemMetadata.key == DATABASE_PROBE_KEY)
        )
        assert existing is None
        session.add(SystemMetadata(key=DATABASE_PROBE_KEY, value={"source": "isolation-test"}))
        await session.commit()

    assert await app.state.redis.get(REDIS_PROBE_KEY) is None
    await app.state.redis.set(REDIS_PROBE_KEY, "written")


async def test_02_next_test_starts_with_clean_database_and_redis(app) -> None:
    async with app.state.session_factory() as session:
        existing = await session.scalar(
            select(SystemMetadata).where(SystemMetadata.key == DATABASE_PROBE_KEY)
        )

    assert existing is None
    assert await app.state.redis.get(REDIS_PROBE_KEY) is None
