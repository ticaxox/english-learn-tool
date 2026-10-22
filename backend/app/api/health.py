from fastapi import APIRouter, Request

from app.core.errors import AppError
from app.schemas.common import ErrorResponse
from app.schemas.health import LivenessResponse, ReadinessResponse
from app.services.health import evaluate_readiness

router = APIRouter(prefix="/health", tags=["health"])


@router.get("/live", response_model=LivenessResponse, summary="Process liveness")
async def liveness(request: Request) -> LivenessResponse:
    settings = request.app.state.settings
    return LivenessResponse(service=settings.app_name, version=settings.app_version)


@router.get(
    "/ready",
    response_model=ReadinessResponse,
    responses={503: {"model": ErrorResponse}},
    summary="Dependency readiness",
)
async def readiness(request: Request) -> ReadinessResponse:
    settings = request.app.state.settings
    result = await evaluate_readiness(
        settings=settings,
        engine=request.app.state.engine,
        redis=request.app.state.redis,
    )
    failures = {
        name: component for name, component in result.components.items() if component.status != "ok"
    }
    if failures:
        raise AppError(
            status_code=503,
            code="SERVICE_NOT_READY",
            message="One or more required dependencies are unavailable.",
            details={
                "components": {
                    name: component.model_dump(exclude_none=True)
                    for name, component in result.components.items()
                }
            },
        )
    return result
