import os
import shutil
import subprocess
import sys
import tempfile
from collections.abc import AsyncIterator, Awaitable, Callable
from pathlib import Path
from uuid import UUID, uuid4

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import selectinload

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
TEST_WORDBOOK_STORAGE_DIR = Path(tempfile.gettempdir()) / "english-learn-wordbook-tests"
os.environ["WORDBOOK_STORAGE_DIR"] = str(TEST_WORDBOOK_STORAGE_DIR)

from app.core.config import Settings  # noqa: E402
from app.core.security import hash_password  # noqa: E402
from app.main import create_app  # noqa: E402
from app.models.identity import User, UserProfile  # noqa: E402

TEST_USER_PASSWORD = "Valid-Test-Pass-123!"
TEST_NEW_PASSWORD = "Valid-New-Pass-456!"
_TEST_PASSWORD_HASH = hash_password(TEST_USER_PASSWORD)


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
    shutil.rmtree(TEST_WORDBOOK_STORAGE_DIR, ignore_errors=True)
    TEST_WORDBOOK_STORAGE_DIR.mkdir(parents=True, exist_ok=True)

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
            shutil.rmtree(TEST_WORDBOOK_STORAGE_DIR, ignore_errors=True)
            TEST_WORDBOOK_STORAGE_DIR.mkdir(parents=True, exist_ok=True)


@pytest_asyncio.fixture
async def client(app) -> AsyncIterator[httpx.AsyncClient]:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as value:
        yield value


UserFactory = Callable[..., Awaitable[User]]


@pytest_asyncio.fixture
async def user_factory(app) -> UserFactory:
    async def create_user(
        *,
        role: str = "member",
        status: str = "active",
        must_change_password: bool = False,
        username: str | None = None,
        display_name: str | None = None,
        department: str | None = "Engineering",
        learning_group: str | None = "Core",
        password_hash: str | None = None,
    ) -> User:
        suffix = uuid4().hex[:8]
        resolved_username = username or f"{role}_{suffix}"
        user_id: UUID
        async with app.state.session_factory() as session:
            user = User(
                username=resolved_username,
                username_normalized=resolved_username.lower(),
                display_name=display_name or f"Test {resolved_username}",
                role=role,
                status=status,
                password_hash=password_hash or _TEST_PASSWORD_HASH,
                must_change_password=must_change_password,
                profile=UserProfile(
                    department=department,
                    learning_group=learning_group,
                ),
            )
            session.add(user)
            await session.commit()
            user_id = user.id

        async with app.state.session_factory() as session:
            loaded = await session.scalar(
                select(User).options(selectinload(User.profile)).where(User.id == user_id)
            )
        if loaded is None:
            raise RuntimeError("The test user could not be reloaded.")
        return loaded

    return create_user


@pytest_asyncio.fixture
async def admin_user(user_factory: UserFactory) -> User:
    return await user_factory(role="admin", display_name="Test Administrator")


@pytest_asyncio.fixture
async def member_user(user_factory: UserFactory) -> User:
    return await user_factory(role="member", display_name="Test Member")
