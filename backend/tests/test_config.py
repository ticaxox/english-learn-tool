from pathlib import Path

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


def test_configuration_rejects_invalid_app_timezone() -> None:
    with pytest.raises(ValidationError):
        Settings(app_timezone="Mars/Olympus")


def test_default_app_timezone_is_shanghai() -> None:
    assert Settings().app_timezone == "Asia/Shanghai"


def test_wordbook_job_stale_window_cannot_precede_worker_timeout() -> None:
    with pytest.raises(ValidationError):
        Settings(wordbook_job_stale_seconds=299)


def test_local_cors_defaults_cover_both_loopback_hosts() -> None:
    repo = Path(__file__).resolve().parents[2]
    expected = "http://localhost:8080,http://127.0.0.1:8080"

    assert Settings(cors_origins=expected).cors_origin_list == expected.split(",")
    assert f"CORS_ORIGINS={expected}" in (repo / ".env.example").read_text(encoding="utf-8")
    compose = (repo / "docker-compose.yml").read_text(encoding="utf-8")
    assert f"${{CORS_ORIGINS:-{expected}}}" in compose
    backend_example = (repo / "backend/.env.example").read_text(encoding="utf-8")
    assert "http://localhost:8080" in backend_example
    assert "http://127.0.0.1:8080" in backend_example


def test_explicit_cors_allowlist_rejects_wildcard() -> None:
    settings = Settings(cors_origins="https://app.example")

    assert settings.cors_origin_list == ["https://app.example"]
    with pytest.raises(ValidationError):
        Settings(cors_origins="*")
