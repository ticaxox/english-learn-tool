from __future__ import annotations

from typing import Any

from app.core.config import get_settings
from app.db.session import create_engine, create_session_factory
from app.services.wordbook_storage import LocalFileStorage


async def worker_runtime_startup(ctx: dict[str, Any]) -> None:
    settings = get_settings()
    engine = create_engine(
        settings.database_url,
        pool_size=settings.db_pool_size,
        max_overflow=settings.db_max_overflow,
    )
    ctx["settings"] = settings
    ctx["engine"] = engine
    ctx["session_factory"] = create_session_factory(engine)
    ctx["wordbook_storage"] = LocalFileStorage(settings.wordbook_storage_dir)


async def worker_runtime_shutdown(ctx: dict[str, Any]) -> None:
    engine = ctx.get("engine")
    if engine is not None:
        await engine.dispose()
