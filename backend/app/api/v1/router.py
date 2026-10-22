from fastapi import APIRouter, Request

from app.api.v1.admin import router as admin_router
from app.api.v1.auth import router as auth_router
from app.api.v1.learning import router as learning_router
from app.api.v1.memory import router as memory_router
from app.api.v1.wordbooks import exports_router as wordbook_exports_router
from app.api.v1.wordbooks import router as wordbooks_router
from app.schemas.system import ServiceInfo

router = APIRouter(tags=["system"])
router.include_router(auth_router)
router.include_router(learning_router)
router.include_router(memory_router)
router.include_router(admin_router)
router.include_router(wordbooks_router)
router.include_router(wordbook_exports_router)


@router.get("", response_model=ServiceInfo, summary="API service metadata")
async def service_info(request: Request) -> ServiceInfo:
    settings = request.app.state.settings
    return ServiceInfo(
        name=settings.app_name,
        version=settings.app_version,
        environment=settings.app_env,
    )
