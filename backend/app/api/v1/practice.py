from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_completed_auth_context
from app.core.config import Settings
from app.core.errors import AppError
from app.db.session import get_db_session
from app.schemas.common import ErrorResponse
from app.schemas.practice import (
    PracticeCreateRequest,
    PracticeDeleteRequest,
    PracticeDeleteResponse,
    PracticeDraftRequest,
    PracticeDraftResponse,
    PracticeEventListResponse,
    PracticeRecordDetail,
    PracticeRecordListResponse,
    PracticeResultResponse,
    PracticeSessionResponse,
    PracticeSubmitRequest,
    PracticeSubmitResponse,
)
from app.services.auth import AuthContext
from app.services.practice import (
    create_practice_session,
    delete_practice_records,
    get_practice_record,
    get_practice_result,
    get_practice_session,
    list_practice_events,
    list_practice_records,
    regenerate_practice_session,
    save_practice_draft,
    start_practice_session,
    submit_practice_session,
)

router = APIRouter(prefix="/practice", tags=["practice"])

_RESPONSES = {
    401: {"model": ErrorResponse, "description": "Authentication is required."},
    403: {"model": ErrorResponse, "description": "The account may not use practice."},
    404: {"model": ErrorResponse, "description": "The practice resource was not found."},
    409: {"model": ErrorResponse, "description": "The practice state conflicts."},
    422: {"model": ErrorResponse, "description": "The request is invalid."},
    429: {"model": ErrorResponse, "description": "The AI quota or concurrency limit is exhausted."},
    503: {"model": ErrorResponse, "description": "The AI provider or queue is unavailable."},
}


def _pool(request: Request):
    pool = getattr(request.app.state, "arq", None)
    if pool is None:
        raise AppError(
            status_code=503,
            code="PRACTICE_QUEUE_UNAVAILABLE",
            message="The practice task queue is unavailable.",
        )
    return pool


@router.post(
    "/sessions",
    response_model=PracticeSessionResponse,
    status_code=status.HTTP_202_ACCEPTED,
    responses=_RESPONSES,
    summary="Create a practice session and enqueue structured question generation",
)
async def create_practice_session_endpoint(
    request: Request,
    payload: PracticeCreateRequest,
    context: Annotated[AuthContext, Depends(get_completed_auth_context)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=1, max_length=128)],
) -> PracticeSessionResponse:
    settings: Settings = request.app.state.settings
    return await create_practice_session(
        session,
        _pool(request),
        context.user,
        settings,
        payload,
        idempotency_key=idempotency_key,
    )


@router.get(
    "/sessions/{session_id}",
    response_model=PracticeSessionResponse,
    responses=_RESPONSES,
    summary="Read a practice session with answer-safe questions",
)
async def get_practice_session_endpoint(
    session_id: UUID,
    context: Annotated[AuthContext, Depends(get_completed_auth_context)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> PracticeSessionResponse:
    return await get_practice_session(session, context.user, session_id)


@router.post(
    "/sessions/{session_id}/start",
    response_model=PracticeSessionResponse,
    responses=_RESPONSES,
    summary="Record that the learner started a practice session",
)
async def start_practice_session_endpoint(
    session_id: UUID,
    context: Annotated[AuthContext, Depends(get_completed_auth_context)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> PracticeSessionResponse:
    return await start_practice_session(session, context.user, session_id)


@router.put(
    "/sessions/{session_id}/draft",
    response_model=PracticeDraftResponse,
    responses=_RESPONSES,
    summary="Save a versioned draft for server-side resume",
)
async def save_practice_draft_endpoint(
    session_id: UUID,
    payload: PracticeDraftRequest,
    context: Annotated[AuthContext, Depends(get_completed_auth_context)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> PracticeDraftResponse:
    return await save_practice_draft(session, context.user, session_id, payload)


@router.post(
    "/sessions/{session_id}/regenerate",
    response_model=PracticeSessionResponse,
    status_code=status.HTTP_202_ACCEPTED,
    responses=_RESPONSES,
    summary="Regenerate an unanswered practice set",
)
async def regenerate_practice_session_endpoint(
    request: Request,
    session_id: UUID,
    context: Annotated[AuthContext, Depends(get_completed_auth_context)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=1, max_length=128)],
) -> PracticeSessionResponse:
    settings: Settings = request.app.state.settings
    return await regenerate_practice_session(
        session,
        _pool(request),
        context.user,
        settings,
        session_id,
        idempotency_key=idempotency_key,
    )


@router.post(
    "/sessions/{session_id}/submit",
    response_model=PracticeSubmitResponse,
    status_code=status.HTTP_202_ACCEPTED,
    responses=_RESPONSES,
    summary=(
        "Submit answers; objective sets grade immediately and subjective sets enqueue AI grading"
    ),
)
async def submit_practice_session_endpoint(
    request: Request,
    session_id: UUID,
    payload: PracticeSubmitRequest,
    context: Annotated[AuthContext, Depends(get_completed_auth_context)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=1, max_length=128)],
) -> PracticeSubmitResponse:
    settings: Settings = request.app.state.settings
    return await submit_practice_session(
        session,
        _pool(request),
        context.user,
        settings,
        session_id,
        payload,
        idempotency_key=idempotency_key,
    )


@router.get(
    "/sessions/{session_id}/result",
    response_model=PracticeResultResponse,
    responses=_RESPONSES,
    summary="Read the submitted result; scoring responses contain no partial score",
)
async def get_practice_result_endpoint(
    session_id: UUID,
    context: Annotated[AuthContext, Depends(get_completed_auth_context)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> PracticeResultResponse:
    return await get_practice_result(session, context.user, session_id)


@router.get(
    "/records",
    response_model=PracticeRecordListResponse,
    responses=_RESPONSES,
    summary="List the caller's submitted practice records",
)
async def list_practice_records_endpoint(
    context: Annotated[AuthContext, Depends(get_completed_auth_context)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    practice_type: Annotated[str | None, Query()] = None,
    source: Annotated[str | None, Query()] = None,
    only_mistakes: Annotated[bool, Query()] = False,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> PracticeRecordListResponse:
    return await list_practice_records(
        session,
        context.user,
        practice_type=practice_type,
        source=source,
        only_mistakes=only_mistakes,
        offset=offset,
        limit=limit,
    )


@router.get(
    "/mistakes",
    response_model=PracticeRecordListResponse,
    responses=_RESPONSES,
    summary="List practice records with at least one mistake",
)
async def list_practice_mistakes_endpoint(
    context: Annotated[AuthContext, Depends(get_completed_auth_context)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    practice_type: Annotated[str | None, Query()] = None,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> PracticeRecordListResponse:
    return await list_practice_records(
        session,
        context.user,
        practice_type=practice_type,
        only_mistakes=True,
        offset=offset,
        limit=limit,
    )


@router.get(
    "/records/{session_id}",
    response_model=PracticeRecordDetail,
    responses=_RESPONSES,
    summary="Read one submitted practice record and its answer-safe detail",
)
async def get_practice_record_endpoint(
    session_id: UUID,
    context: Annotated[AuthContext, Depends(get_completed_auth_context)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> PracticeRecordDetail:
    return await get_practice_record(session, context.user, session_id)


@router.delete(
    "/records/bulk",
    response_model=PracticeDeleteResponse,
    responses=_RESPONSES,
    summary="Delete only the caller's practice records",
)
async def delete_practice_records_endpoint(
    payload: PracticeDeleteRequest,
    context: Annotated[AuthContext, Depends(get_completed_auth_context)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=1, max_length=128)],
) -> PracticeDeleteResponse:
    return await delete_practice_records(
        session,
        context.user,
        payload,
        idempotency_key=idempotency_key,
    )


@router.get(
    "/events",
    response_model=PracticeEventListResponse,
    responses=_RESPONSES,
    summary="List the caller's practice learning events",
)
async def list_practice_events_endpoint(
    context: Annotated[AuthContext, Depends(get_completed_auth_context)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> PracticeEventListResponse:
    return await list_practice_events(session, context.user, offset=offset, limit=limit)
