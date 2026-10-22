from functools import lru_cache
from typing import Literal
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def _has_valid_http_base(value: str) -> bool:
    parsed = urlsplit(value)
    return (
        parsed.scheme in {"http", "https"}
        and bool(parsed.netloc)
        and parsed.username is None
        and parsed.password is None
    )


class Settings(BaseSettings):
    """Runtime configuration loaded from environment values with safe local defaults."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_name: str = "AI English Learning Tool"
    app_version: str = "0.1.0"
    app_env: Literal["development", "test", "production"] = "development"
    app_base_url: str = "http://localhost:8000"
    frontend_base_url: str = "http://localhost:5173"
    app_timezone: str = "Asia/Shanghai"
    api_v1_prefix: str = "/api/v1"

    database_url: str = Field(repr=False)
    redis_url: str

    jwt_secret: SecretStr = Field(min_length=32)
    refresh_token_pepper: SecretStr = Field(min_length=32)
    secret_encryption_key: SecretStr = Field(min_length=32)
    access_token_minutes: int = Field(default=15, gt=0)
    refresh_token_days: int = Field(default=30, gt=0)

    cors_origins: str
    log_level: str = "INFO"
    health_check_timeout_seconds: float = Field(default=2.0, gt=0, le=30)
    db_pool_size: int = Field(default=5, ge=1, le=50)
    db_max_overflow: int = Field(default=5, ge=0, le=50)

    login_max_failures: int = Field(default=5, ge=1, le=20)
    login_failure_window_seconds: int = Field(default=300, ge=30, le=3600)
    login_cooldown_seconds: int = Field(default=900, ge=60, le=86400)
    import_preview_ttl_minutes: int = Field(default=30, ge=5, le=1440)
    import_max_rows: int = Field(default=500, ge=1, le=5000)
    import_max_bytes: int = Field(default=1_000_000, ge=1024, le=20_000_000)

    @field_validator("database_url")
    @classmethod
    def validate_database_url(cls, value: str) -> str:
        if not value.startswith("postgresql+asyncpg://"):
            raise ValueError("DATABASE_URL must use the asyncpg SQLAlchemy driver")
        return value

    @field_validator("redis_url")
    @classmethod
    def validate_redis_url(cls, value: str) -> str:
        if not value.startswith(("redis://", "rediss://")):
            raise ValueError("REDIS_URL must use redis:// or rediss://")
        return value

    @field_validator("app_base_url", "frontend_base_url")
    @classmethod
    def validate_http_url(cls, value: str) -> str:
        if not _has_valid_http_base(value):
            raise ValueError("URL values must be absolute http:// or https:// URLs")
        return value.rstrip("/")

    @field_validator("app_timezone")
    @classmethod
    def validate_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except ZoneInfoNotFoundError as exc:
            raise ValueError("APP_TIMEZONE must be a valid IANA timezone") from exc
        return value

    @field_validator("cors_origins")
    @classmethod
    def validate_cors_origins(cls, value: str) -> str:
        origins = [origin.strip().rstrip("/") for origin in value.split(",") if origin.strip()]
        if not origins:
            raise ValueError("CORS_ORIGINS must contain at least one origin")
        for origin in origins:
            parsed = urlsplit(origin)
            if (
                not _has_valid_http_base(origin)
                or parsed.path not in {"", "/"}
                or parsed.query
                or parsed.fragment
            ):
                raise ValueError("CORS_ORIGINS entries must be absolute HTTP origins")
        return ",".join(origins)

    @field_validator("log_level")
    @classmethod
    def validate_log_level(cls, value: str) -> str:
        normalized = value.upper()
        if normalized not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
            raise ValueError("LOG_LEVEL must be a standard Python logging level")
        return normalized

    @property
    def cors_origin_list(self) -> list[str]:
        return self.cors_origins.split(",")

    @property
    def refresh_cookie_path(self) -> str:
        return f"{self.api_v1_prefix}/auth/refresh"

    @property
    def csrf_cookie_path(self) -> str:
        # The SPA must be able to read the non-HttpOnly token from any application route.
        return "/"

    @property
    def cookie_secure(self) -> bool:
        return self.app_env == "production"

    def runtime_configuration_errors(self) -> list[str]:
        """Return non-secret configuration problems suitable for readiness details."""
        errors: list[str] = []
        if not self.database_url.startswith("postgresql+asyncpg://"):
            errors.append("database driver is not asyncpg")
        if not self.cors_origin_list:
            errors.append("cors allowlist is empty")
        for name, secret in (
            ("jwt_secret", self.jwt_secret),
            ("refresh_token_pepper", self.refresh_token_pepper),
            ("secret_encryption_key", self.secret_encryption_key),
        ):
            if len(secret.get_secret_value()) < 32:
                errors.append(f"{name} is too short")
        return errors


@lru_cache
def get_settings() -> Settings:
    return Settings()
