import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from redis.asyncio import Redis

from app.api.health import router as health_router
from app.api.v1.router import router as api_v1_router
from app.core.config import Settings, get_settings
from app.core.errors import register_exception_handlers
from app.core.logging import configure_logging
from app.core.middleware import RequestIDMiddleware
from app.db.session import create_engine, create_session_factory

logger = logging.getLogger(__name__)


def create_app(settings: Settings | None = None) -> FastAPI:
    runtime_settings = settings or get_settings()
    configure_logging(runtime_settings.log_level)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        logger.info(
            "application.started",
            extra={"environment": runtime_settings.app_env},
        )
        yield
        await app.state.redis.aclose()
        await app.state.engine.dispose()
        logger.info("application.stopped")

    application = FastAPI(
        title=runtime_settings.app_name,
        version=runtime_settings.app_version,
        docs_url=f"{runtime_settings.api_v1_prefix}/docs",
        redoc_url=f"{runtime_settings.api_v1_prefix}/redoc",
        openapi_url=f"{runtime_settings.api_v1_prefix}/openapi.json",
        lifespan=lifespan,
    )
    application.state.settings = runtime_settings
    application.state.engine = create_engine(
        runtime_settings.database_url,
        pool_size=runtime_settings.db_pool_size,
        max_overflow=runtime_settings.db_max_overflow,
    )
    application.state.session_factory = create_session_factory(application.state.engine)
    application.state.redis = Redis.from_url(
        runtime_settings.redis_url,
        encoding="utf-8",
        decode_responses=True,
        socket_connect_timeout=runtime_settings.health_check_timeout_seconds,
        socket_timeout=runtime_settings.health_check_timeout_seconds,
    )

    application.add_middleware(
        CORSMiddleware,
        allow_origins=runtime_settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["X-Request-ID"],
    )
    application.add_middleware(RequestIDMiddleware)

    register_exception_handlers(application)
    application.include_router(health_router)
    application.include_router(api_v1_router, prefix=runtime_settings.api_v1_prefix)
    return application


app = create_app()
