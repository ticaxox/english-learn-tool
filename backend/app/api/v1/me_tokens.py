from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_completed_auth_context
from app.db.session import get_db_session
from app.schemas.common import ErrorResponse
from app.schemas.tokens import (
    PersonalTokenCreate,
    PersonalTokenCreated,
    PersonalTokenListResponse,
    PersonalTokenResponse,
)
from app.services.auth import AuthContext
from app.services.personal_tokens import (
    create_personal_token,
    delete_personal_token,
    list_personal_tokens,
    refresh_personal_token,
)

router = APIRouter(prefix="/me/tokens", tags=["personal tokens"])

_RESPONSES = {
    401: {"model": ErrorResponse, "description": "Authentication is required."},
    404: {"model": ErrorResponse, "description": "The token was not found."},
    422: {"model": ErrorResponse, "description": "The request is invalid."},
}


def _response(row) -> PersonalTokenResponse:
    return PersonalTokenResponse(
        id=row.id,
        name=row.name,
        prefix=row.token_prefix,
        is_default=row.is_default,
        created_at=row.created_at,
        last_used_at=row.last_used_at,
        revoked_at=row.revoked_at,
    )


@router.get("", response_model=PersonalTokenListResponse, responses=_RESPONSES)
async def list_tokens_endpoint(
    context: Annotated[AuthContext, Depends(get_completed_auth_context)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> PersonalTokenListResponse:
    rows = await list_personal_tokens(session, context.user)
    return PersonalTokenListResponse(items=[_response(row) for row in rows])


@router.post(
    "",
    response_model=PersonalTokenCreated,
    status_code=status.HTTP_201_CREATED,
    responses=_RESPONSES,
)
async def create_token_endpoint(
    payload: PersonalTokenCreate,
    context: Annotated[AuthContext, Depends(get_completed_auth_context)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> PersonalTokenCreated:
    row, plaintext = await create_personal_token(session, context.user, payload.name)
    return PersonalTokenCreated(**_response(row).model_dump(), token=plaintext)


@router.delete("/{token_id}", status_code=status.HTTP_204_NO_CONTENT, responses=_RESPONSES)
async def delete_token_endpoint(
    token_id: UUID,
    context: Annotated[AuthContext, Depends(get_completed_auth_context)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> Response:
    await delete_personal_token(session, context.user, token_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/{token_id}/refresh",
    response_model=PersonalTokenCreated,
    responses=_RESPONSES,
)
async def refresh_token_endpoint(
    token_id: UUID,
    context: Annotated[AuthContext, Depends(get_completed_auth_context)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> PersonalTokenCreated:
    row, plaintext = await refresh_personal_token(session, context.user, token_id)
    return PersonalTokenCreated(**_response(row).model_dump(), token=plaintext)
