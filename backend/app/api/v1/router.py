from fastapi import APIRouter, Request

from app.schemas.system import ServiceInfo

router = APIRouter(tags=["system"])


@router.get("", response_model=ServiceInfo, summary="API service metadata")
async def service_info(request: Request) -> ServiceInfo:
    settings = request.app.state.settings
    return ServiceInfo(
        name=settings.app_name,
        version=settings.app_version,
        environment=settings.app_env,
    )
