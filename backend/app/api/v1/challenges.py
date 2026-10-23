from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_completed_auth_context
from app.core.config import Settings
from app.core.errors import AppError
from app.db.session import get_db_session
from app.schemas.challenge import (
    ChallengeBossSubmitRequest,
    ChallengeBossSubmitResponse,
    ChallengeGenerateResponse,
    ChallengeHistoryResponse,
    ChallengeJobResponse,
    ChallengeNodeDetailResponse,
    ChallengePlanResponse,
    ChallengeStartResponse,
)
from app.schemas.common import ErrorResponse
from app.services.auth import AuthContext
from app.services.challenge import (
    generate_today,
    get_challenge,
    get_challenge_job,
    get_history,
    get_node_detail,
    get_today,
    start_node,
    submit_boss,
)

router = APIRouter(prefix="/challenges", tags=["challenges"])

_RESPONSES = {
    401: {"model": ErrorResponse, "description": "Authentication is required."},
    403: {"model": ErrorResponse, "description": "The account may not use challenges."},
    404: {"model": ErrorResponse, "description": "The challenge resource was not found."},
    409: {"model": ErrorResponse, "description": "The challenge state conflicts."},
    422: {"model": ErrorResponse, "description": "The request is invalid."},
    429: {"model": ErrorResponse, "description": "The AI quota or concurrency limit is exhausted."},
    503: {"model": ErrorResponse, "description": "The AI provider or queue is unavailable."},
}


def _pool(request: Request):
    pool = getattr(request.app.state, "arq", None)
    if pool is None:
        raise AppError(
            status_code=503,
            code="CHALLENGE_QUEUE_UNAVAILABLE",
            message="The challenge task queue is unavailable.",
        )
    return pool


@router.get(
    "/today",
    response_model=ChallengePlanResponse,
    responses=_RESPONSES,
    summary="Read today's daily challenge map",
)
async def today_endpoint(
    request: Request,
    context: Annotated[AuthContext, Depends(get_completed_auth_context)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> ChallengePlanResponse:
    settings: Settings = request.app.state.settings
    return await get_today(session, context.user, settings)


@router.post(
    "/today/generate",
    response_model=ChallengeGenerateResponse,
    status_code=status.HTTP_202_ACCEPTED,
    responses=_RESPONSES,
    summary="Generate today's challenge map idempotently",
)
async def generate_today_endpoint(
    request: Request,
    context: Annotated[AuthContext, Depends(get_completed_auth_context)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> ChallengeGenerateResponse:
    settings: Settings = request.app.state.settings
    return await generate_today(session, _pool(request), context.user, settings)


@router.get(
    "/history",
    response_model=ChallengeHistoryResponse,
    responses=_RESPONSES,
    summary="List the caller's challenge history",
)
async def history_endpoint(
    request: Request,
    context: Annotated[AuthContext, Depends(get_completed_auth_context)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> ChallengeHistoryResponse:
    settings: Settings = request.app.state.settings
    return await get_history(session, context.user, settings, limit=limit, offset=offset)


@router.get(
    "/jobs/{job_id}",
    response_model=ChallengeJobResponse,
    responses=_RESPONSES,
    summary="Read a challenge generation job status",
)
async def job_endpoint(
    job_id: UUID,
    context: Annotated[AuthContext, Depends(get_completed_auth_context)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> ChallengeJobResponse:
    return await get_challenge_job(session, context.user, job_id)


@router.get(
    "/{challenge_id}",
    response_model=ChallengePlanResponse,
    responses=_RESPONSES,
    summary="Read a challenge map and node progress",
)
async def challenge_endpoint(
    request: Request,
    challenge_id: UUID,
    context: Annotated[AuthContext, Depends(get_completed_auth_context)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> ChallengePlanResponse:
    settings: Settings = request.app.state.settings
    return await get_challenge(session, context.user, settings, challenge_id)


@router.get(
    "/{challenge_id}/nodes/{node_id}",
    response_model=ChallengeNodeDetailResponse,
    responses=_RESPONSES,
    summary="Read a challenge node and its legal actions",
)
async def node_detail_endpoint(
    request: Request,
    challenge_id: UUID,
    node_id: UUID,
    context: Annotated[AuthContext, Depends(get_completed_auth_context)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> ChallengeNodeDetailResponse:
    settings: Settings = request.app.state.settings
    return await get_node_detail(session, context.user, settings, challenge_id, node_id)


@router.post(
    "/{challenge_id}/nodes/{node_id}/start",
    response_model=ChallengeStartResponse,
    responses=_RESPONSES,
    summary="Start or resume a challenge node task",
)
async def start_node_endpoint(
    request: Request,
    challenge_id: UUID,
    node_id: UUID,
    context: Annotated[AuthContext, Depends(get_completed_auth_context)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> ChallengeStartResponse:
    settings: Settings = request.app.state.settings
    return await start_node(session, _pool(request), context.user, settings, challenge_id, node_id)


@router.post(
    "/{challenge_id}/nodes/{node_id}/boss-submit",
    response_model=ChallengeBossSubmitResponse,
    responses=_RESPONSES,
    summary="Submit the final challenge answers idempotently",
)
async def boss_submit_endpoint(
    request: Request,
    challenge_id: UUID,
    node_id: UUID,
    payload: ChallengeBossSubmitRequest,
    context: Annotated[AuthContext, Depends(get_completed_auth_context)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=1, max_length=128)],
) -> ChallengeBossSubmitResponse:
    settings: Settings = request.app.state.settings
    return await submit_boss(
        session,
        _pool(request),
        context.user,
        settings,
        challenge_id,
        node_id,
        payload.answers,
        idempotency_key=idempotency_key,
    )
