from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_auth_context, get_completed_auth_context
from app.core.config import Settings
from app.db.session import get_db_session
from app.schemas.common import ErrorResponse
from app.schemas.knowledge import (
    KnowledgeDocumentListResponse,
    KnowledgeDocumentResponse,
    KnowledgeDocumentUpdate,
    KnowledgeImportRequest,
    KnowledgeSearchResponse,
)
from app.services.auth import AuthContext
from app.services.knowledge import (
    archive_document,
    import_document,
    list_documents,
    search_response,
    update_document,
)

admin_router = APIRouter(prefix="/admin/knowledge", tags=["admin knowledge"])
router = APIRouter(prefix="/knowledge", tags=["knowledge"])

_RESPONSES = {
    401: {"model": ErrorResponse, "description": "Authentication failed or session expired."},
    403: {"model": ErrorResponse, "description": "Administrator permission is required."},
    404: {"model": ErrorResponse, "description": "The document does not exist."},
}


@admin_router.get(
    "",
    response_model=KnowledgeDocumentListResponse,
    responses=_RESPONSES,
    summary="List every reference document",
)
async def list_documents_endpoint(
    context: Annotated[AuthContext, Depends(get_completed_auth_context)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> KnowledgeDocumentListResponse:
    items = await list_documents(session, context.user)
    return KnowledgeDocumentListResponse(items=items)


@admin_router.post(
    "",
    response_model=KnowledgeDocumentResponse,
    status_code=status.HTTP_201_CREATED,
    responses=_RESPONSES,
    summary="Import and index one reference document",
)
async def import_document_endpoint(
    payload: KnowledgeImportRequest,
    request: Request,
    context: Annotated[AuthContext, Depends(get_completed_auth_context)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> KnowledgeDocumentResponse:
    settings: Settings = request.app.state.settings
    return await import_document(session, settings, context.user, payload)


@admin_router.patch(
    "/{document_id}",
    response_model=KnowledgeDocumentResponse,
    responses=_RESPONSES,
    summary="Edit, re-index or publish a document",
)
async def update_document_endpoint(
    document_id: UUID,
    payload: KnowledgeDocumentUpdate,
    request: Request,
    context: Annotated[AuthContext, Depends(get_completed_auth_context)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> KnowledgeDocumentResponse:
    settings: Settings = request.app.state.settings
    return await update_document(session, settings, context.user, document_id, payload)


@admin_router.delete(
    "/{document_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses=_RESPONSES,
    summary="Archive a document and drop its chunks",
)
async def archive_document_endpoint(
    document_id: UUID,
    context: Annotated[AuthContext, Depends(get_completed_auth_context)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> None:
    await archive_document(session, context.user, document_id)


@router.get(
    "/search",
    response_model=KnowledgeSearchResponse,
    responses=_RESPONSES,
    summary="Search the reference knowledge base",
)
async def search_endpoint(
    request: Request,
    query: Annotated[str, Query(min_length=1, max_length=500)],
    context: Annotated[AuthContext, Depends(get_auth_context)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    limit: Annotated[int, Query(ge=1, le=20)] = 6,
) -> KnowledgeSearchResponse:
    settings: Settings = request.app.state.settings
    return await search_response(session, settings, context.user, query, limit)
