from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Header, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_completed_auth_context
from app.core.config import Settings
from app.db.session import get_db_session
from app.schemas.common import ErrorResponse
from app.schemas.learning import (
    HeartbeatRequest,
    HeartbeatResponse,
    LearningEventListResponse,
    LearningProfilePatch,
    LearningProfileResponse,
    LearningStatsResponse,
    TodayResponse,
)
from app.services.auth import AuthContext
from app.services.learning import (
    get_profile,
    learning_stats,
    list_events,
    record_heartbeat,
    today_summary,
    update_profile,
)

router = APIRouter(tags=["learning"])

_AUTH_RESPONSES = {
    401: {"model": ErrorResponse, "description": "Authentication is required."},
    403: {"model": ErrorResponse, "description": "The account may not perform this action."},
}
_CONFLICT = {409: {"model": ErrorResponse, "description": "The current state conflicts."}}


@router.get(
    "/users/me/profile",
    response_model=LearningProfileResponse,
    responses=_AUTH_RESPONSES,
    summary="Read the signed-in member learning profile",
)
async def get_learning_profile_endpoint(
    context: Annotated[AuthContext, Depends(get_completed_auth_context)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> LearningProfileResponse:
    return await get_profile(session, context.user)


@router.patch(
    "/users/me/profile",
    response_model=LearningProfileResponse,
    responses={**_AUTH_RESPONSES, 422: {"model": ErrorResponse}},
    summary="Update the learning profile; targets apply to the next daily plan",
)
async def patch_learning_profile_endpoint(
    payload: LearningProfilePatch,
    request: Request,
    context: Annotated[AuthContext, Depends(get_completed_auth_context)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> LearningProfileResponse:
    settings: Settings = request.app.state.settings
    return await update_profile(session, context.user, payload, settings=settings)


@router.get(
    "/learning/today",
    response_model=TodayResponse,
    responses={**_AUTH_RESPONSES, **_CONFLICT},
    summary="Read today's plan snapshot, progress, and extra due reviews",
)
async def today_endpoint(
    request: Request,
    context: Annotated[AuthContext, Depends(get_completed_auth_context)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> TodayResponse:
    settings: Settings = request.app.state.settings
    return await today_summary(session, context.user, settings=settings)


@router.post(
    "/learning/daily-plan/ensure",
    response_model=TodayResponse,
    responses={**_AUTH_RESPONSES, **_CONFLICT},
    summary="Idempotently create or read the local-date plan snapshot",
)
async def ensure_daily_plan_endpoint(
    request: Request,
    context: Annotated[AuthContext, Depends(get_completed_auth_context)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> TodayResponse:
    settings: Settings = request.app.state.settings
    return await today_summary(session, context.user, settings=settings)


@router.post(
    "/learning/heartbeat",
    response_model=HeartbeatResponse,
    responses={**_AUTH_RESPONSES, 422: {"model": ErrorResponse}},
    summary="Credit at most 30 seconds of server-measured study activity",
)
async def heartbeat_endpoint(
    payload: HeartbeatRequest,
    request: Request,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=1, max_length=128)],
    context: Annotated[AuthContext, Depends(get_completed_auth_context)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> HeartbeatResponse:
    settings: Settings = request.app.state.settings
    return await record_heartbeat(
        session,
        context.user,
        settings=settings,
        idempotency_key=idempotency_key,
    )


@router.get(
    "/learning/stats",
    response_model=LearningStatsResponse,
    responses=_AUTH_RESPONSES,
    summary="Personal study statistics derived from persisted events and heartbeats",
)
async def stats_endpoint(
    request: Request,
    context: Annotated[AuthContext, Depends(get_completed_auth_context)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> LearningStatsResponse:
    settings: Settings = request.app.state.settings
    return await learning_stats(session, context.user, settings=settings)


@router.get(
    "/learning/events",
    response_model=LearningEventListResponse,
    responses={**_AUTH_RESPONSES, 422: {"model": ErrorResponse}},
    summary="Page through only the signed-in member's own learning events",
)
async def events_endpoint(
    context: Annotated[AuthContext, Depends(get_completed_auth_context)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    cursor: Annotated[str | None, Query()] = None,
) -> LearningEventListResponse:
    return await list_events(session, context.user, limit=limit, cursor=cursor)
