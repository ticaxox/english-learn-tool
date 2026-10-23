from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_completed_auth_context
from app.core.config import Settings
from app.db.session import get_db_session
from app.schemas.common import ErrorResponse
from app.schemas.notifications import (
    NotificationListResponse,
    NotificationPreferencesResponse,
    NotificationPreferencesUpdate,
    NotificationReadAllResponse,
    NotificationResponse,
    NotificationUnreadCountResponse,
)
from app.services.auth import AuthContext
from app.services.notifications import (
    get_preferences,
    list_notifications,
    mark_all_notifications_read,
    mark_notification_read,
    unread_notification_count,
    update_preferences,
)

router = APIRouter(prefix="/notifications", tags=["notifications"])

_RESPONSES = {
    401: {"model": ErrorResponse, "description": "Authentication is required."},
    404: {"model": ErrorResponse, "description": "The notification was not found."},
    422: {"model": ErrorResponse, "description": "The request is invalid."},
}


@router.get(
    "",
    response_model=NotificationListResponse,
    responses=_RESPONSES,
    summary="List the caller's notification inbox with cursor pagination",
)
async def list_notifications_endpoint(
    context: Annotated[AuthContext, Depends(get_completed_auth_context)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    cursor: Annotated[str | None, Query(max_length=512)] = None,
    unread_only: Annotated[bool, Query()] = False,
) -> NotificationListResponse:
    return await list_notifications(
        session,
        context.user,
        limit=limit,
        cursor=cursor,
        unread_only=unread_only,
    )


@router.get(
    "/preferences",
    response_model=NotificationPreferencesResponse,
    responses=_RESPONSES,
    summary="Read notification category, DND, daily-limit, and timezone preferences",
)
async def get_preferences_endpoint(
    request: Request,
    context: Annotated[AuthContext, Depends(get_completed_auth_context)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> NotificationPreferencesResponse:
    settings: Settings = request.app.state.settings
    return await get_preferences(session, context.user, settings)


@router.put(
    "/preferences",
    response_model=NotificationPreferencesResponse,
    responses=_RESPONSES,
    summary="Replace notification preferences for future notifications",
)
async def update_preferences_endpoint(
    request: Request,
    payload: NotificationPreferencesUpdate,
    context: Annotated[AuthContext, Depends(get_completed_auth_context)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> NotificationPreferencesResponse:
    settings: Settings = request.app.state.settings
    return await update_preferences(session, context.user, settings, payload)


@router.get(
    "/unread-count",
    response_model=NotificationUnreadCountResponse,
    responses=_RESPONSES,
    summary="Read the caller's unread notification count",
)
async def unread_count_endpoint(
    context: Annotated[AuthContext, Depends(get_completed_auth_context)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> NotificationUnreadCountResponse:
    return await unread_notification_count(session, context.user)


@router.patch(
    "/{notification_id}/read",
    response_model=NotificationResponse,
    responses=_RESPONSES,
    summary="Mark one own notification as read idempotently",
)
async def mark_read_endpoint(
    notification_id: UUID,
    context: Annotated[AuthContext, Depends(get_completed_auth_context)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> NotificationResponse:
    return await mark_notification_read(session, context.user, notification_id)


@router.post(
    "/read-all",
    response_model=NotificationReadAllResponse,
    responses=_RESPONSES,
    summary="Mark all own visible notifications as read",
)
async def read_all_endpoint(
    context: Annotated[AuthContext, Depends(get_completed_auth_context)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> NotificationReadAllResponse:
    return await mark_all_notifications_read(session, context.user)
