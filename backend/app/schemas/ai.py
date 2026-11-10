from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.schemas.ai_tasks import AiJobCreateRequest

AiProviderTestStatus = Literal["untested", "succeeded", "failed"]
AiTaskType = Literal[
    "practice_generation",
    "subjective_grading",
    "coach_reply",
    "challenge_plan",
    "json_repair",
]
AiJobStatus = Literal["queued", "running", "succeeded", "failed", "cancelled", "stale"]
AiQuotaKind = Literal["coach_messages", "question_generation", "subjective_grading"]
AiPromptKey = Literal[
    "practice_generation",
    "subjective_grading",
    "coach_reply",
    "challenge_plan",
    "json_repair",
]


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ProviderCreateRequest(_StrictModel):
    name: str = Field(min_length=1, max_length=100)
    base_url: str = Field(min_length=8, max_length=500)
    api_key: str = Field(min_length=8, max_length=4_096, repr=False)
    model_id: str = Field(min_length=1, max_length=200)
    priority: int = Field(default=100, ge=0, le=10_000)
    is_default: bool = False
    timeout_seconds: int = Field(default=60, ge=1, le=300)
    enabled: bool = True
    custom_headers: dict[str, str] = Field(default_factory=dict)
    # Optional: the model used for /embeddings on this provider.
    embedding_model: str | None = Field(default=None, max_length=120)

    @field_validator("name", "model_id")
    @classmethod
    def not_blank(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("value must not be blank")
        return normalized

    @field_validator("base_url")
    @classmethod
    def trim_url(cls, value: str) -> str:
        return value.strip().rstrip("/")

    @field_validator("custom_headers")
    @classmethod
    def validate_headers(cls, value: dict[str, str]) -> dict[str, str]:
        if len(value) > 10:
            raise ValueError("at most 10 custom headers are allowed")
        forbidden = {
            "authorization",
            "host",
            "content-length",
            "transfer-encoding",
            "connection",
            "cookie",
            "proxy-authorization",
            "x-forwarded-for",
            "x-forwarded-host",
            "x-real-ip",
        }
        cleaned: dict[str, str] = {}
        for raw_name, raw_value in value.items():
            name = raw_name.strip()
            header_value = raw_value.strip()
            if not name or len(name) > 64 or not name.replace("-", "").isalnum():
                raise ValueError("custom header names must be safe HTTP tokens")
            if name.lower() in forbidden:
                raise ValueError(f"custom header {name} is not allowed")
            if "\r" in header_value or "\n" in header_value or len(header_value) > 512:
                raise ValueError("custom header values are invalid")
            cleaned[name] = header_value
        return cleaned

    @model_validator(mode="after")
    def default_must_be_enabled(self) -> ProviderCreateRequest:
        if self.is_default and not self.enabled:
            raise ValueError("a default provider must be enabled")
        return self


class ProviderPatchRequest(_StrictModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    base_url: str | None = Field(default=None, min_length=8, max_length=500)
    api_key: str | None = Field(default=None, min_length=8, max_length=4_096, repr=False)
    model_id: str | None = Field(default=None, min_length=1, max_length=200)
    priority: int | None = Field(default=None, ge=0, le=10_000)
    is_default: bool | None = None
    timeout_seconds: int | None = Field(default=None, ge=1, le=300)
    enabled: bool | None = None
    custom_headers: dict[str, str] | None = None
    embedding_model: str | None = Field(default=None, max_length=120)

    @field_validator("name", "model_id")
    @classmethod
    def not_blank(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            raise ValueError("value must not be blank")
        return normalized

    @field_validator("base_url")
    @classmethod
    def trim_url(cls, value: str | None) -> str | None:
        return value.strip().rstrip("/") if value is not None else None

    @field_validator("api_key", mode="before")
    @classmethod
    def blank_api_key_keeps_existing(cls, value: object) -> object:
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @field_validator("custom_headers")
    @classmethod
    def validate_headers(cls, value: dict[str, str] | None) -> dict[str, str] | None:
        if value is None:
            return None
        return ProviderCreateRequest.validate_headers(value)

    @model_validator(mode="after")
    def validate_patch(self) -> ProviderPatchRequest:
        if not self.model_fields_set:
            raise ValueError("at least one field must be supplied")
        if self.is_default is True and self.enabled is False:
            raise ValueError("a default provider must be enabled")
        return self


class ProviderProbeRequest(_StrictModel):
    """Check a provider configuration that has not been saved yet.

    The editor can test a brand-new provider before creating it. When the key is
    already stored, the client sends only ``provider_id`` so the secret never
    leaves the server again.
    """

    base_url: str = Field(min_length=8, max_length=500)
    api_key: str | None = Field(default=None, min_length=8, max_length=4_096, repr=False)
    provider_id: UUID | None = None
    timeout_seconds: int = Field(default=60, ge=1, le=300)
    custom_headers: dict[str, str] = Field(default_factory=dict)

    @field_validator("base_url")
    @classmethod
    def trim_url(cls, value: str) -> str:
        return value.strip().rstrip("/")

    @field_validator("api_key", mode="before")
    @classmethod
    def blank_api_key_uses_stored(cls, value: object) -> object:
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @field_validator("custom_headers")
    @classmethod
    def validate_headers(cls, value: dict[str, str]) -> dict[str, str]:
        return ProviderCreateRequest.validate_headers(value)


class ProviderResponse(BaseModel):
    id: UUID
    name: str
    base_url: str
    api_key_masked: str
    model_id: str
    priority: int
    is_default: bool
    timeout_seconds: int
    enabled: bool
    custom_headers: dict[str, str]
    embedding_model: str | None = None
    last_test_status: AiProviderTestStatus
    last_test_error_code: str | None = None
    last_test_at: datetime | None = None
    last_test_latency_ms: int | None = None
    created_at: datetime
    updated_at: datetime


class ProviderListResponse(BaseModel):
    items: list[ProviderResponse]


class ProviderTestResponse(BaseModel):
    success: bool
    status: AiProviderTestStatus
    latency_ms: int | None = None
    error_code: str | None = None
    error_message: str | None = None
    models: list[str] = Field(default_factory=list)


class ProviderModelsResponse(BaseModel):
    success: bool
    models: list[str] = Field(default_factory=list)
    error_code: str | None = None
    error_message: str | None = None


class PromptSummary(BaseModel):
    key: AiPromptKey
    name: str
    summary: str
    updated_at: datetime


class PromptListResponse(BaseModel):
    items: list[PromptSummary]


class PromptDetail(PromptSummary):
    template: str


class PromptUpdateRequest(_StrictModel):
    name: str = Field(min_length=1, max_length=100)
    summary: str = Field(min_length=1, max_length=500)
    template: str = Field(min_length=1, max_length=100_000)

    @field_validator("name", "summary", "template")
    @classmethod
    def not_blank(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("value must not be blank")
        return normalized


class AiErrorDetail(BaseModel):
    code: str
    message: str
    retryable: bool = False


class AiJobStatusResponse(BaseModel):
    id: UUID
    task_type: AiTaskType
    status: AiJobStatus
    quota_kind: AiQuotaKind | None = None
    provider_id: UUID | None = None
    provider_name: str | None = None
    model_id: str | None = None
    attempt_count: int
    repair_count: int
    result_summary: dict[str, Any] = Field(default_factory=dict)
    error: AiErrorDetail | None = None
    created_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None


class AiJobAcceptedResponse(BaseModel):
    job_id: UUID
    status: AiJobStatus
    status_url: str
    replayed: bool = False


class DailyQuotaUsage(BaseModel):
    quota_kind: AiQuotaKind
    limit: int
    used: int
    reserved: int
    remaining: int


class ConcurrencyUsage(BaseModel):
    limit: int
    in_use: int


class AiUserUsageResponse(BaseModel):
    local_date: date
    quotas: list[DailyQuotaUsage]
    concurrency: ConcurrencyUsage


class AdminQuotaAggregate(BaseModel):
    quota_kind: AiQuotaKind
    limit_per_user: int
    users_with_usage: int
    consumed: int
    reserved: int
    released: int


class AdminTaskAggregate(BaseModel):
    task_type: AiTaskType
    status: AiJobStatus
    count: int


class AdminProviderAggregate(BaseModel):
    provider_id: UUID | None = None
    provider_name: str
    jobs: int
    succeeded: int
    failed: int


class AdminAiUsageResponse(BaseModel):
    date_from: date
    date_to: date
    total_jobs: int
    active_jobs: int
    quotas: list[AdminQuotaAggregate]
    tasks: list[AdminTaskAggregate]
    providers: list[AdminProviderAggregate]


__all__ = [
    "AdminAiUsageResponse",
    "AiJobAcceptedResponse",
    "AiJobCreateRequest",
    "AiJobStatusResponse",
    "AiUserUsageResponse",
    "PromptDetail",
    "PromptListResponse",
    "PromptUpdateRequest",
    "ProviderCreateRequest",
    "ProviderListResponse",
    "ProviderModelsResponse",
    "ProviderPatchRequest",
    "ProviderResponse",
    "ProviderTestResponse",
]
