from typing import Any

from pydantic import BaseModel, Field


class ErrorResponse(BaseModel):
    code: str = Field(examples=["NOT_FOUND"])
    message: str = Field(examples=["The requested resource was not found."])
    details: Any = None
    request_id: str = Field(examples=["8c73f0e441b54867b42d8fb8081bd077"])
