from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query, Request, Response, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_completed_auth_context
from app.core.config import Settings
from app.core.errors import AppError
from app.db.session import get_db_session
from app.models.coach import CoachMessage, CoachStreamEvent
from app.schemas.coach import (
    CoachAcceptedResponse,
    CoachActionReceiptResponse,
    CoachConversationCreate,
    CoachConversationListResponse,
    CoachConversationPatch,
    CoachConversationResponse,
    CoachMessageCreate,
    CoachMessageListResponse,
    CoachMessageResponse,
    CoachStreamEventResponse,
    CoachUndoResponse,
)
from app.schemas.common import ErrorResponse
from app.services.auth import AuthContext
from app.services.coach import (
    create_coach_message,
    create_conversation,
    delete_or_clear_conversation,
    get_action_receipt,
    get_message,
    list_conversations,
    list_messages,
    list_stream_events,
    rename_conversation,
    undo_action,
)

router = APIRouter(prefix="/coach", tags=["coach"])

_RESPONSES = {
    401: {"model": ErrorResponse, "description": "Authentication is required."},
    403: {"model": ErrorResponse, "description": "The account may not use the coach."},
    404: {"model": ErrorResponse, "description": "The coach resource was not found."},
    409: {"model": ErrorResponse, "description": "The coach action or message state conflicts."},
    422: {"model": ErrorResponse, "description": "The request is invalid."},
    429: {"model": ErrorResponse, "description": "The AI quota or concurrency limit is exhausted."},
    503: {"model": ErrorResponse, "description": "The AI provider or queue is unavailable."},
}


def _pool(request: Request):
    pool = getattr(request.app.state, "arq", None)
    if pool is None:
        raise AppError(
            status_code=503,
            code="COACH_QUEUE_UNAVAILABLE",
            message="The coach task queue is unavailable.",
        )
    return pool


def _format_sse(sequence: int, event_type: str, data: dict[str, object]) -> str:
    return (
        f"id: {sequence}\n"
        f"event: {event_type}\n"
        f"data: {json.dumps(data, ensure_ascii=False, separators=(',', ':'))}\n\n"
    )


async def _stream_events(
    request: Request,
    message_id: UUID,
    *,
    after: int,
) -> AsyncIterator[str]:
    factory = request.app.state.session_factory
    while True:
        async with factory() as session:
            message = await session.get(CoachMessage, message_id)
            rows = list(
                (
                    await session.scalars(
                        select(CoachStreamEvent)
                        .where(
                            CoachStreamEvent.message_id == message_id,
                            CoachStreamEvent.sequence > after,
                        )
                        .order_by(CoachStreamEvent.sequence.asc())
                        .limit(200)
                    )
                ).all()
            )
        for row in rows:
            after = row.sequence
            yield _format_sse(row.sequence, row.event_type, row.data)
        if message is None:
            return
        if message.status in {"completed", "failed"} and not rows:
            return
        if await request.is_disconnected():
            return
        await asyncio.sleep(0.2)


@router.get(
    "/conversations",
    response_model=CoachConversationListResponse,
    responses=_RESPONSES,
    summary="List the caller's active coach conversations",
)
async def list_conversations_endpoint(
    context: Annotated[AuthContext, Depends(get_completed_auth_context)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    cursor: str | None = None,
) -> CoachConversationListResponse:
    return await list_conversations(session, context.user, limit=limit, cursor=cursor)


@router.post(
    "/conversations",
    response_model=CoachConversationResponse,
    status_code=status.HTTP_201_CREATED,
    responses=_RESPONSES,
    summary="Create a long-lived coach conversation",
)
async def create_conversation_endpoint(
    payload: CoachConversationCreate,
    context: Annotated[AuthContext, Depends(get_completed_auth_context)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> CoachConversationResponse:
    return await create_conversation(session, context.user, payload)


@router.patch(
    "/conversations/{conversation_id}",
    response_model=CoachConversationResponse,
    responses=_RESPONSES,
    summary="Rename an own coach conversation",
)
async def rename_conversation_endpoint(
    conversation_id: UUID,
    payload: CoachConversationPatch,
    context: Annotated[AuthContext, Depends(get_completed_auth_context)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> CoachConversationResponse:
    return await rename_conversation(session, context.user, conversation_id, payload)


@router.delete(
    "/conversations/{conversation_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses=_RESPONSES,
    summary="Delete or clear an own coach conversation",
)
async def delete_conversation_endpoint(
    conversation_id: UUID,
    context: Annotated[AuthContext, Depends(get_completed_auth_context)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    clear: Annotated[bool, Query()] = False,
) -> Response:
    await delete_or_clear_conversation(session, context.user, conversation_id, clear_only=clear)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/conversations/{conversation_id}/messages",
    response_model=CoachMessageListResponse,
    responses=_RESPONSES,
    summary="List paginated messages in an own coach conversation",
)
async def list_messages_endpoint(
    conversation_id: UUID,
    context: Annotated[AuthContext, Depends(get_completed_auth_context)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    cursor: str | None = None,
) -> CoachMessageListResponse:
    return await list_messages(session, context.user, conversation_id, limit=limit, cursor=cursor)


@router.post(
    "/conversations/{conversation_id}/messages",
    response_model=CoachAcceptedResponse,
    status_code=status.HTTP_202_ACCEPTED,
    responses=_RESPONSES,
    summary="Create a coach message and enqueue a structured reply",
)
async def create_message_endpoint(
    request: Request,
    conversation_id: UUID,
    payload: CoachMessageCreate,
    context: Annotated[AuthContext, Depends(get_completed_auth_context)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=1, max_length=128)],
) -> CoachAcceptedResponse:
    settings: Settings = request.app.state.settings
    return await create_coach_message(
        session,
        _pool(request),
        context.user,
        settings,
        conversation_id,
        payload,
        idempotency_key=idempotency_key,
    )


@router.get(
    "/messages/{message_id}",
    response_model=CoachMessageResponse,
    responses=_RESPONSES,
    summary="Read the final coach message and its action receipts",
)
async def get_message_endpoint(
    message_id: UUID,
    context: Annotated[AuthContext, Depends(get_completed_auth_context)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> CoachMessageResponse:
    return await get_message(session, context.user, message_id)


@router.get(
    "/action-receipts/{receipt_id}",
    response_model=CoachActionReceiptResponse,
    responses=_RESPONSES,
    summary="Read an own coach action receipt",
)
async def get_action_receipt_endpoint(
    receipt_id: UUID,
    context: Annotated[AuthContext, Depends(get_completed_auth_context)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> CoachActionReceiptResponse:
    return await get_action_receipt(session, context.user, receipt_id)


@router.post(
    "/action-receipts/{receipt_id}/undo",
    response_model=CoachUndoResponse,
    responses=_RESPONSES,
    summary="Undo an applied coach action within its 24-hour window",
)
async def undo_action_endpoint(
    request: Request,
    receipt_id: UUID,
    context: Annotated[AuthContext, Depends(get_completed_auth_context)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> CoachUndoResponse:
    return await undo_action(
        session, context.user, receipt_id, pool=getattr(request.app.state, "arq", None)
    )


@router.get(
    "/messages/{message_id}/events",
    response_model=list[CoachStreamEventResponse],
    responses=_RESPONSES,
    summary="Read persisted coach stream events for refresh and reconnect recovery",
)
async def list_message_events_endpoint(
    message_id: UUID,
    context: Annotated[AuthContext, Depends(get_completed_auth_context)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    after: Annotated[int, Query(ge=0)] = 0,
) -> list[CoachStreamEventResponse]:
    events = await list_stream_events(session, context.user, message_id, after=after)
    return [
        CoachStreamEventResponse(
            id=event.id,
            message_id=event.message_id,
            sequence=event.sequence,
            event_type=event.event_type,
            data=event.data,
            created_at=event.created_at,
        )
        for event in events
    ]


@router.get(
    "/streams/{message_id}",
    responses={
        200: {
            "description": "Server-sent coach message events.",
            "content": {"text/event-stream": {"schema": {"type": "string"}}},
        },
        **_RESPONSES,
    },
    summary="Stream or replay a coach message with resumable event IDs",
)
async def stream_message_endpoint(
    request: Request,
    message_id: UUID,
    context: Annotated[AuthContext, Depends(get_completed_auth_context)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    after: Annotated[int | None, Query(ge=0)] = None,
    last_event_id: Annotated[str | None, Header(alias="Last-Event-ID")] = None,
) -> StreamingResponse:
    message = await get_message(session, context.user, message_id)
    if message.role != "assistant":
        raise AppError(
            status_code=404,
            code="COACH_MESSAGE_NOT_FOUND",
            message="The coach message was not found.",
        )
    cursor = after
    if cursor is None and last_event_id:
        try:
            cursor = int(last_event_id)
        except ValueError as exc:
            raise AppError(
                status_code=422,
                code="COACH_LAST_EVENT_ID_INVALID",
                message="Last-Event-ID must be a non-negative integer.",
            ) from exc
        if cursor < 0:
            raise AppError(
                status_code=422,
                code="COACH_LAST_EVENT_ID_INVALID",
                message="Last-Event-ID must be a non-negative integer.",
            )
    return StreamingResponse(
        _stream_events(request, message_id, after=cursor or 0),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
