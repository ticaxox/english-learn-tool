from typing import Literal

from pydantic import BaseModel


class LivenessResponse(BaseModel):
    status: Literal["ok"] = "ok"
    service: str
    version: str


class ComponentHealth(BaseModel):
    status: Literal["ok", "error"]
    latency_ms: float | None = None
    detail: str | None = None


class ReadinessResponse(BaseModel):
    status: Literal["ready"] = "ready"
    components: dict[str, ComponentHealth]
