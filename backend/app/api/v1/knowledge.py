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
    KnowledgeDocumentDetail,
    KnowledgeDocumentListResponse,
    KnowledgeDocumentResponse,
    KnowledgeDocumentUpdate,
    KnowledgeFolderCreate,
    KnowledgeFolderListResponse,
    KnowledgeFolderResponse,
    KnowledgeFolderUpdate,
    KnowledgeImportRequest,
    KnowledgeSearchResponse,
)
from app.services.auth import AuthContext
from app.services.knowledge import (
    archive_document,
    create_folder,
    delete_folder,
    document_detail,
    import_document,
    list_documents,
    list_folders,
    rename_folder,
    search_response,
    update_document,
)

admin_router = APIRouter(prefix="/admin/knowledge", tags=["admin knowledge"])
router = APIRouter(prefix="/knowledge", tags=["knowledge"])

_RESPONSES = {
    401: {"model": ErrorResponse, "description": "Authentication failed or session expired."},
    403: {"model": ErrorResponse, "description": "This shelf is read-only for you."},
    404: {"model": ErrorResponse, "description": "The folder or document does not exist."},
}


@router.get(
    "",
    response_model=KnowledgeFolderListResponse,
    responses=_RESPONSES,
    summary="Every knowledge shelf this user can read",
)
async def list_folders_endpoint(
    context: Annotated[AuthContext, Depends(get_auth_context)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> KnowledgeFolderListResponse:
    return KnowledgeFolderListResponse(items=await list_folders(session, context.user))


@router.post(
    "/folders",
    response_model=KnowledgeFolderResponse,
    status_code=status.HTTP_201_CREATED,
    responses=_RESPONSES,
    summary="Create a shelf",
)
async def create_folder_endpoint(
    payload: KnowledgeFolderCreate,
    context: Annotated[AuthContext, Depends(get_completed_auth_context)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> KnowledgeFolderResponse:
    return await create_folder(session, context.user, payload)


@router.patch(
    "/folders/{folder_id}",
    response_model=KnowledgeFolderResponse,
    responses=_RESPONSES,
    summary="Rename a shelf",
)
async def rename_folder_endpoint(
    folder_id: UUID,
    payload: KnowledgeFolderUpdate,
    context: Annotated[AuthContext, Depends(get_completed_auth_context)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> KnowledgeFolderResponse:
    return await rename_folder(session, context.user, folder_id, payload.name)


@router.delete(
    "/folders/{folder_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses=_RESPONSES,
    summary="Delete a shelf; its documents move to the general one",
)
async def delete_folder_endpoint(
    folder_id: UUID,
    context: Annotated[AuthContext, Depends(get_completed_auth_context)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> None:
    await delete_folder(session, context.user, folder_id)


@router.get(
    "/folders/{folder_id}/documents",
    response_model=KnowledgeDocumentListResponse,
    responses=_RESPONSES,
    summary="Documents on one shelf",
)
async def list_folder_documents_endpoint(
    folder_id: UUID,
    context: Annotated[AuthContext, Depends(get_auth_context)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> KnowledgeDocumentListResponse:
    items = await list_documents(session, context.user, folder_id)
    return KnowledgeDocumentListResponse(items=items)


@router.post(
    "/folders/{folder_id}/documents",
    response_model=KnowledgeDocumentResponse,
    status_code=status.HTTP_201_CREATED,
    responses=_RESPONSES,
    summary="Import and index one document onto a shelf",
)
async def import_into_folder_endpoint(
    folder_id: UUID,
    payload: KnowledgeImportRequest,
    request: Request,
    context: Annotated[AuthContext, Depends(get_completed_auth_context)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> KnowledgeDocumentResponse:
    settings: Settings = request.app.state.settings
    return await import_document(
        session, settings, context.user, payload.model_copy(update={"folder_id": folder_id})
    )


@router.get(
    "/documents/{document_id}",
    response_model=KnowledgeDocumentDetail,
    responses=_RESPONSES,
    summary="Read one document",
)
async def document_detail_endpoint(
    document_id: UUID,
    context: Annotated[AuthContext, Depends(get_auth_context)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> KnowledgeDocumentDetail:
    return await document_detail(session, context.user, document_id)


@router.delete(
    "/documents/{document_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses=_RESPONSES,
    summary="Remove a document and drop its chunks",
)
async def delete_document_endpoint(
    document_id: UUID,
    context: Annotated[AuthContext, Depends(get_completed_auth_context)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> None:
    await archive_document(session, context.user, document_id)


@router.get(
    "/search",
    response_model=KnowledgeSearchResponse,
    responses=_RESPONSES,
    summary="Search the shelves this learner may read",
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


# Kept so an administrator's older client, and the tests that describe the old
# shape, still work: the flat list is every shelf, and an import without a
# folder lands on the general one.


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
