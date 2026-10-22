import pytest
from pydantic import ValidationError

from app.core.config import Settings


def test_configuration_rejects_short_secrets() -> None:
    with pytest.raises(ValidationError):
        Settings(
            database_url="postgresql+asyncpg://user:pass@localhost:5432/db",
            jwt_secret="short",
        )


def test_configuration_rejects_non_async_database_driver() -> None:
    with pytest.raises(ValidationError):
        Settings(database_url="postgresql://user:pass@localhost:5432/db")


def test_cors_origins_are_normalized() -> None:
    settings = Settings(cors_origins="https://one.example/, https://two.example")

    assert settings.cors_origin_list == ["https://one.example", "https://two.example"]


def test_configuration_rejects_cors_paths() -> None:
    with pytest.raises(ValidationError):
        Settings(cors_origins="https://example.test/not-an-origin")


def test_wordbook_job_stale_window_cannot_precede_worker_timeout() -> None:
    with pytest.raises(ValidationError):
        Settings(wordbook_job_stale_seconds=299)
