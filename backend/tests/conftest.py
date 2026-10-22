import os
import subprocess
import sys
from collections.abc import AsyncIterator
from pathlib import Path

import httpx
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

# Tests must never inherit an application/production database or Redis target.
os.environ["DATABASE_URL"] = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql+asyncpg://postgres:postgres@127.0.0.1:5432/english_learn_test",
)
os.environ["REDIS_URL"] = os.environ.get(
    "TEST_REDIS_URL",
    "redis://127.0.0.1:6379/15",
)
os.environ["APP_ENV"] = "test"
os.environ["CORS_ORIGINS"] = "http://localhost:5173,http://testserver"
os.environ["JWT_SECRET"] = "test-jwt-secret-with-at-least-32-chars"
os.environ["REFRESH_TOKEN_PEPPER"] = "test-refresh-pepper-with-at-least-32-chars"
os.environ["SECRET_ENCRYPTION_KEY"] = "test-encryption-key-with-at-least-32-chars"

from app.core.config import Settings  # noqa: E402
from app.main import create_app  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def migrated_database() -> None:
    backend_dir = Path(__file__).resolve().parents[1]
    completed = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=backend_dir,
        env=os.environ.copy(),
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(
            "Alembic migration failed. Ensure PostgreSQL is available.\n"
            f"stdout:\n{completed.stdout}\nstderr:\n{completed.stderr}"
        )


@pytest_asyncio.fixture
async def app():
    application = create_app(Settings())
    async with application.router.lifespan_context(application):
        yield application


@pytest_asyncio.fixture(autouse=True)
async def isolate_test_state(app) -> AsyncIterator[None]:
    """Roll back database writes and remove Redis state after every test."""
    settings = app.state.settings
    if settings.app_env != "test":
        raise RuntimeError("Test isolation requires APP_ENV=test")

    redis = app.state.redis
    await redis.flushdb()

    original_session_factory = app.state.session_factory
    connection = await app.state.engine.connect()
    transaction = await connection.begin()
    app.state.session_factory = async_sessionmaker(
        bind=connection,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
        join_transaction_mode="create_savepoint",
    )
    try:
        yield
    finally:
        try:
            await transaction.rollback()
        finally:
            await connection.close()
            app.state.session_factory = original_session_factory
            await redis.flushdb()


@pytest_asyncio.fixture
async def client(app) -> AsyncIterator[httpx.AsyncClient]:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as value:
        yield value
