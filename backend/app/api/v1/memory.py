from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_completed_auth_context
from app.core.config import Settings
from app.db.session import get_db_session
from app.schemas.common import ErrorResponse
from app.schemas.learning import (
    MemoryConfigResponse,
    MemoryModuleConfig,
    MemoryProgressResetResponse,
    MistakeListResponse,
    MistakePriorityRequest,
    MistakeResponse,
    SessionCompleteRequest,
    SessionCreateRequest,
    SessionEventRequest,
    SessionEventResponse,
    SessionResponse,
    WordStateResponse,
)
from app.services.auth import AuthContext
from app.services.memory import (
    complete_session,
    get_config,
    get_session,
    list_mistakes,
    master_word,
    reset_today_progress,
    restore_word,
    set_config,
    set_mistake_priority,
    start_session,
    submit_event,
)

router = APIRouter(prefix="/memory", tags=["memory"])

_AUTH_RESPONSES = {
    401: {"model": ErrorResponse, "description": "Authentication is required."},
    403: {"model": ErrorResponse, "description": "The account may not perform this action."},
}
_NOT_FOUND = {404: {"model": ErrorResponse, "description": "The resource was not found."}}
_CONFLICT = {409: {"model": ErrorResponse, "description": "The current state conflicts."}}


@router.get(
    "/config",
    response_model=MemoryConfigResponse,
    responses=_AUTH_RESPONSES,
    summary="Read the caller's memory module configuration",
)
async def get_config_endpoint(
    context: Annotated[AuthContext, Depends(get_completed_auth_context)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> MemoryConfigResponse:
    return await get_config(session, context.user)


@router.put(
    "/config",
    response_model=MemoryConfigResponse,
    responses={**_AUTH_RESPONSES, 422: {"model": ErrorResponse}},
    summary="Replace the caller's memory module configuration",
)
async def put_config_endpoint(
    payload: MemoryModuleConfig,
    context: Annotated[AuthContext, Depends(get_completed_auth_context)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> MemoryConfigResponse:
    return await set_config(session, context.user, payload)


@router.post(
    "/progress/reset",
    response_model=MemoryProgressResetResponse,
    responses=_AUTH_RESPONSES,
    summary="Reset today's memory progress and put today's words back in the queue",
)
async def reset_progress_endpoint(
    request: Request,
    context: Annotated[AuthContext, Depends(get_completed_auth_context)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> MemoryProgressResetResponse:
    settings: Settings = request.app.state.settings
    return await reset_today_progress(session, context.user, settings)


@router.post(
    "/sessions",
    response_model=SessionResponse,
    status_code=status.HTTP_201_CREATED,
    responses={**_AUTH_RESPONSES, **_CONFLICT, 201: {"model": SessionResponse}},
    summary="Create or resume today's training session for one module",
)
async def create_session_endpoint(
    payload: SessionCreateRequest,
    request: Request,
    context: Annotated[AuthContext, Depends(get_completed_auth_context)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> SessionResponse:
    settings: Settings = request.app.state.settings
    return await start_session(session, context.user, settings=settings, payload=payload)


@router.get(
    "/sessions/{session_id}",
    response_model=SessionResponse,
    responses={**_AUTH_RESPONSES, **_NOT_FOUND},
    summary="Read a session, its next real card, and any correct-answer-free prompt",
)
async def get_session_endpoint(
    session_id: UUID,
    context: Annotated[AuthContext, Depends(get_completed_auth_context)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> SessionResponse:
    return await get_session(session, context.user, session_id)


@router.post(
    "/sessions/{session_id}/events",
    response_model=SessionEventResponse,
    responses={
        **_AUTH_RESPONSES,
        **_NOT_FOUND,
        **_CONFLICT,
        422: {"model": ErrorResponse},
    },
    summary="Submit one card action or answer; replay-safe through Idempotency-Key",
)
async def submit_event_endpoint(
    session_id: UUID,
    payload: SessionEventRequest,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=1, max_length=128)],
    context: Annotated[AuthContext, Depends(get_completed_auth_context)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> SessionEventResponse:
    return await submit_event(
        session,
        context.user,
        session_id,
        payload=payload,
        idempotency_key=idempotency_key,
    )


@router.post(
    "/sessions/{session_id}/complete",
    response_model=SessionResponse,
    responses={**_AUTH_RESPONSES, **_NOT_FOUND},
    summary="Explicitly end a session; unfinished targets stay unfinished",
)
async def complete_session_endpoint(
    session_id: UUID,
    payload: SessionCompleteRequest,
    context: Annotated[AuthContext, Depends(get_completed_auth_context)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> SessionResponse:
    return await complete_session(session, context.user, session_id)


@router.patch(
    "/words/{state_id}/master",
    response_model=WordStateResponse,
    responses={**_AUTH_RESPONSES, **_NOT_FOUND},
    summary="Mark one of the caller's words as mastered",
)
async def master_word_endpoint(
    state_id: UUID,
    context: Annotated[AuthContext, Depends(get_completed_auth_context)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> WordStateResponse:
    return await master_word(session, context.user, state_id)


@router.patch(
    "/words/{state_id}/restore",
    response_model=WordStateResponse,
    responses={**_AUTH_RESPONSES, **_NOT_FOUND},
    summary="Restore a mastered word with a freshly computed safe due time",
)
async def restore_word_endpoint(
    state_id: UUID,
    context: Annotated[AuthContext, Depends(get_completed_auth_context)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> WordStateResponse:
    return await restore_word(session, context.user, state_id)


@router.get(
    "/mistakes",
    response_model=MistakeListResponse,
    responses={**_AUTH_RESPONSES, 422: {"model": ErrorResponse}},
    summary="List the caller's memory mistakes ordered by the most recent Again",
)
async def list_mistakes_endpoint(
    context: Annotated[AuthContext, Depends(get_completed_auth_context)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    cursor: Annotated[str | None, Query()] = None,
) -> MistakeListResponse:
    return await list_mistakes(session, context.user, limit=limit, cursor=cursor)


@router.patch(
    "/mistakes/{entry_id}/priority",
    response_model=MistakeResponse,
    responses={**_AUTH_RESPONSES, **_NOT_FOUND},
    summary="Toggle the review marker without altering recorded events",
)
async def mistake_priority_endpoint(
    entry_id: UUID,
    payload: MistakePriorityRequest,
    context: Annotated[AuthContext, Depends(get_completed_auth_context)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> MistakeResponse:
    return await set_mistake_priority(session, context.user, entry_id, payload)
