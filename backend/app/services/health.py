import asyncio
from collections.abc import Awaitable, Callable
from time import perf_counter

from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.core.config import Settings
from app.schemas.health import ComponentHealth, ReadinessResponse


async def _measure(
    name: str,
    check: Callable[[], Awaitable[None]],
    timeout_seconds: float,
) -> tuple[str, ComponentHealth]:
    started = perf_counter()
    try:
        await asyncio.wait_for(check(), timeout=timeout_seconds)
    except Exception as exc:  # noqa: BLE001 - health details must not leak exception messages
        return name, ComponentHealth(
            status="error",
            latency_ms=round((perf_counter() - started) * 1000, 2),
            detail=type(exc).__name__,
        )
    return name, ComponentHealth(
        status="ok",
        latency_ms=round((perf_counter() - started) * 1000, 2),
    )


def _check_configuration(settings: Settings) -> ComponentHealth:
    errors = settings.runtime_configuration_errors()
    if errors:
        return ComponentHealth(status="error", detail=", ".join(errors))
    return ComponentHealth(status="ok")


async def evaluate_readiness(
    settings: Settings,
    engine: AsyncEngine,
    redis: Redis,
) -> ReadinessResponse:
    async def check_database() -> None:
        async with engine.connect() as connection:
            await connection.execute(text("SELECT 1"))

    async def check_redis() -> None:
        await redis.ping()

    database_result, redis_result = await asyncio.gather(
        _measure("database", check_database, settings.health_check_timeout_seconds),
        _measure("redis", check_redis, settings.health_check_timeout_seconds),
    )
    components = {
        "configuration": _check_configuration(settings),
        database_result[0]: database_result[1],
        redis_result[0]: redis_result[1],
    }
    return ReadinessResponse(components=components)
