from __future__ import annotations

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_completed_auth_context
from app.core.config import Settings
from app.db.session import get_db_session
from app.schemas.common import ErrorResponse
from app.schemas.dashboard import AdminDashboardResponse
from app.services.auth import AuthContext
from app.services.dashboard import get_admin_dashboard

router = APIRouter(prefix="/admin", tags=["admin-dashboard"])

_RESPONSES = {
    401: {"model": ErrorResponse, "description": "Authentication is required."},
    403: {"model": ErrorResponse, "description": "Administrator permission is required."},
    422: {"model": ErrorResponse, "description": "The dashboard filters are invalid."},
}


@router.get(
    "/dashboard",
    response_model=AdminDashboardResponse,
    responses=_RESPONSES,
    summary="Read organization-level learning aggregates without member content",
)
async def dashboard_endpoint(
    request: Request,
    context: Annotated[AuthContext, Depends(get_completed_auth_context)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    date_from: date | None = None,
    date_to: date | None = None,
    department: Annotated[str | None, Query(max_length=100)] = None,
    learning_group: Annotated[str | None, Query(max_length=100)] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=50)] = 10,
) -> AdminDashboardResponse:
    settings: Settings = request.app.state.settings
    return await get_admin_dashboard(
        session,
        context.user,
        settings,
        date_from=date_from,
        date_to=date_to,
        department=department,
        learning_group=learning_group,
        page=page,
        page_size=page_size,
    )
