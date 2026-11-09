from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_completed_auth_context
from app.db.session import get_db_session
from app.schemas.coach_memory import (
    CoachMemoryCreate,
    CoachMemoryListResponse,
    CoachMemoryResponse,
    CoachMemoryUpdate,
)
from app.schemas.common import ErrorResponse
from app.services.auth import AuthContext
from app.services.coach_memory import (
    create_memory,
    delete_memory,
    list_memories,
    update_memory,
)

router = APIRouter(prefix="/me/memories", tags=["coach memories"])

_RESPONSES = {
    401: {"model": ErrorResponse, "description": "Authentication failed or session expired."},
    404: {"model": ErrorResponse, "description": "The memory does not exist."},
}


@router.get(
    "",
    response_model=CoachMemoryListResponse,
    responses=_RESPONSES,
    summary="List the memories the coach keeps about the caller",
)
async def list_memories_endpoint(
    context: Annotated[AuthContext, Depends(get_completed_auth_context)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    include_history: Annotated[bool, Query()] = False,
) -> CoachMemoryListResponse:
    return await list_memories(session, context.user, include_history=include_history)


@router.post(
    "",
    response_model=CoachMemoryResponse,
    status_code=status.HTTP_201_CREATED,
    responses=_RESPONSES,
    summary="Add a memory for the coach",
)
async def create_memory_endpoint(
    payload: CoachMemoryCreate,
    context: Annotated[AuthContext, Depends(get_completed_auth_context)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> CoachMemoryResponse:
    return await create_memory(session, context.user, payload)


@router.patch(
    "/{memory_id}",
    response_model=CoachMemoryResponse,
    responses=_RESPONSES,
    summary="Edit a memory",
)
async def update_memory_endpoint(
    memory_id: UUID,
    payload: CoachMemoryUpdate,
    context: Annotated[AuthContext, Depends(get_completed_auth_context)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> CoachMemoryResponse:
    return await update_memory(session, context.user, memory_id, payload)


@router.delete(
    "/{memory_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses=_RESPONSES,
    summary="Forget a memory",
)
async def delete_memory_endpoint(
    memory_id: UUID,
    context: Annotated[AuthContext, Depends(get_completed_auth_context)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> None:
    await delete_memory(session, context.user, memory_id)
