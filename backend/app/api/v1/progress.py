from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_completed_auth_context
from app.core.config import Settings
from app.db.session import get_db_session
from app.schemas.common import ErrorResponse
from app.schemas.gamification import (
    BadgeListResponse,
    GamificationFootprintResponse,
    GamificationProgressResponse,
    GamificationWeeklyResponse,
)
from app.services.auth import AuthContext
from app.services.gamification import footprint, list_badges, progress, weekly

router = APIRouter(prefix="/me/progress", tags=["progress"])

_RESPONSES = {
    401: {"model": ErrorResponse, "description": "Authentication failed or session expired."},
}


@router.get(
    "",
    response_model=GamificationProgressResponse,
    responses=_RESPONSES,
    summary="Read the caller's level, streak and today's quests",
)
async def get_progress_endpoint(
    request: Request,
    context: Annotated[AuthContext, Depends(get_completed_auth_context)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> GamificationProgressResponse:
    settings: Settings = request.app.state.settings
    response = await progress(session, settings, context.user)
    await session.commit()
    return response


@router.get(
    "/weekly",
    response_model=GamificationWeeklyResponse,
    responses=_RESPONSES,
    summary="Read the last seven days of activity",
)
async def get_weekly_endpoint(
    request: Request,
    context: Annotated[AuthContext, Depends(get_completed_auth_context)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> GamificationWeeklyResponse:
    settings: Settings = request.app.state.settings
    response = await weekly(session, settings, context.user)
    await session.commit()
    return response


@router.get(
    "/footprint",
    response_model=GamificationFootprintResponse,
    responses=_RESPONSES,
    summary="Read the calendar month and the spread of the learner's words",
)
async def get_footprint_endpoint(
    request: Request,
    context: Annotated[AuthContext, Depends(get_completed_auth_context)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> GamificationFootprintResponse:
    settings: Settings = request.app.state.settings
    return await footprint(session, settings, context.user)


@router.get(
    "/badges",
    response_model=BadgeListResponse,
    responses=_RESPONSES,
    summary="List the badges and which ones are unlocked",
)
async def list_badges_endpoint(
    context: Annotated[AuthContext, Depends(get_completed_auth_context)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> BadgeListResponse:
    return BadgeListResponse(items=await list_badges(session, context.user))
