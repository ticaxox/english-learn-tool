from __future__ import annotations

from datetime import date
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_completed_auth_context
from app.core.config import Settings
from app.core.errors import AppError
from app.db.session import get_db_session
from app.schemas.ai import (
    AiJobAcceptedResponse,
    AiJobCreateRequest,
    AiJobStatusResponse,
    AiUserUsageResponse,
)
from app.schemas.common import ErrorResponse
from app.services.ai_jobs import cancel_user_job, create_ai_job, get_user_job
from app.services.ai_usage import user_usage
from app.services.auth import AuthContext

router = APIRouter(prefix="/ai", tags=["ai"])

_AI_RESPONSES = {
    401: {"model": ErrorResponse, "description": "Authentication is required."},
    403: {"model": ErrorResponse, "description": "The account may not use AI tasks."},
    404: {"model": ErrorResponse, "description": "The AI task was not found."},
    409: {"model": ErrorResponse, "description": "The AI task conflicts with current state."},
    422: {"model": ErrorResponse, "description": "The request is invalid."},
    429: {"model": ErrorResponse, "description": "The AI quota or concurrency limit is exhausted."},
    503: {"model": ErrorResponse, "description": "The AI provider or queue is unavailable."},
}


@router.post(
    "/jobs",
    response_model=AiJobAcceptedResponse,
    status_code=status.HTTP_202_ACCEPTED,
    responses=_AI_RESPONSES,
    summary="Create a durable structured AI generation task",
)
async def create_ai_job_endpoint(
    request: Request,
    payload: AiJobCreateRequest,
    context: Annotated[AuthContext, Depends(get_completed_auth_context)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=1, max_length=128)],
) -> AiJobAcceptedResponse:
    pool = getattr(request.app.state, "arq", None)
    if pool is None:
        raise AppError(
            status_code=503,
            code="AI_QUEUE_UNAVAILABLE",
            message="The AI task queue is unavailable.",
        )
    settings: Settings = request.app.state.settings
    job, replayed = await create_ai_job(
        session,
        pool,
        context.user,
        settings,
        payload,
        idempotency_key=idempotency_key,
    )
    return AiJobAcceptedResponse(
        job_id=job.id,
        status=job.status,
        status_url=f"{settings.api_v1_prefix}/ai/jobs/{job.id}",
        replayed=replayed,
    )


@router.get(
    "/jobs/{job_id}",
    response_model=AiJobStatusResponse,
    responses=_AI_RESPONSES,
    summary="Read the durable status and privacy-safe summary of an AI task",
)
async def get_ai_job_endpoint(
    job_id: UUID,
    context: Annotated[AuthContext, Depends(get_completed_auth_context)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> AiJobStatusResponse:
    return await get_user_job(session, context.user, job_id)


@router.post(
    "/jobs/{job_id}/cancel",
    response_model=AiJobStatusResponse,
    responses=_AI_RESPONSES,
    summary="Cancel a queued or running AI task and release its quota reservation",
)
async def cancel_ai_job_endpoint(
    request: Request,
    job_id: UUID,
    context: Annotated[AuthContext, Depends(get_completed_auth_context)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> AiJobStatusResponse:
    pool = getattr(request.app.state, "arq", None)
    if pool is None:
        raise AppError(
            status_code=503,
            code="AI_QUEUE_UNAVAILABLE",
            message="The AI task queue is unavailable.",
        )
    return await cancel_user_job(session, pool, context.user, job_id)


@router.get(
    "/usage/me",
    response_model=AiUserUsageResponse,
    responses=_AI_RESPONSES,
    summary="Read personal daily AI quotas and concurrency usage",
)
async def my_ai_usage_endpoint(
    request: Request,
    context: Annotated[AuthContext, Depends(get_completed_auth_context)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    local_date: Annotated[date | None, Query()] = None,
) -> AiUserUsageResponse:
    settings: Settings = request.app.state.settings
    return await user_usage(
        session, request.app.state.redis, context.user, settings, local_date=local_date
    )
