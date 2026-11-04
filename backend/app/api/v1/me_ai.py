from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_completed_auth_context
from app.core.config import Settings
from app.db.session import get_db_session
from app.schemas.ai import (
    ProviderCreateRequest,
    ProviderListResponse,
    ProviderModelsResponse,
    ProviderPatchRequest,
    ProviderProbeRequest,
    ProviderResponse,
    ProviderTestResponse,
)
from app.schemas.ai_memory import (
    AiMemoryClearResponse,
    AiMemoryCreateRequest,
    AiMemoryKind,
    AiMemoryListResponse,
    AiMemoryResponse,
    AiMemoryUpdateRequest,
)
from app.schemas.common import ErrorResponse
from app.services.ai_memory import (
    clear_auto_memories,
    create_memory,
    delete_memory,
    list_memories,
    update_memory,
)
from app.services.ai_providers import (
    create_provider,
    delete_provider,
    get_provider,
    list_provider_models,
    list_providers,
    probe_provider,
    probe_provider_models,
    test_provider,
    update_provider,
)
from app.services.auth import AuthContext

router = APIRouter(prefix="/me/ai", tags=["personal ai"])

_RESPONSES = {
    401: {"model": ErrorResponse, "description": "Authentication is required."},
    404: {"model": ErrorResponse, "description": "The AI provider was not found."},
    409: {"model": ErrorResponse, "description": "The AI provider conflicts with current state."},
    422: {"model": ErrorResponse, "description": "The request is invalid."},
}


@router.get(
    "/providers",
    response_model=ProviderListResponse,
    responses=_RESPONSES,
    summary="List the current user's encrypted AI providers with masked keys",
)
async def list_my_providers_endpoint(
    context: Annotated[AuthContext, Depends(get_completed_auth_context)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> ProviderListResponse:
    return await list_providers(session, context.user)


@router.get(
    "/providers/{provider_id}",
    response_model=ProviderResponse,
    responses=_RESPONSES,
    summary="Read one AI provider owned by the current user",
)
async def get_my_provider_endpoint(
    provider_id: UUID,
    context: Annotated[AuthContext, Depends(get_completed_auth_context)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> ProviderResponse:
    return await get_provider(session, context.user, provider_id)


@router.post(
    "/providers",
    response_model=ProviderResponse,
    status_code=status.HTTP_201_CREATED,
    responses=_RESPONSES,
    summary="Create an OpenAI-compatible provider owned by the current user",
)
async def create_my_provider_endpoint(
    request: Request,
    payload: ProviderCreateRequest,
    context: Annotated[AuthContext, Depends(get_completed_auth_context)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> ProviderResponse:
    settings: Settings = request.app.state.settings
    return await create_provider(session, context.user, settings, payload)


@router.post(
    "/providers/probe",
    response_model=ProviderTestResponse,
    responses=_RESPONSES,
    summary="Check a provider configuration before it is saved",
)
async def probe_my_provider_endpoint(
    request: Request,
    payload: ProviderProbeRequest,
    context: Annotated[AuthContext, Depends(get_completed_auth_context)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> ProviderTestResponse:
    settings: Settings = request.app.state.settings
    return await probe_provider(session, context.user, settings, payload)


@router.post(
    "/providers/probe/models",
    response_model=ProviderModelsResponse,
    responses=_RESPONSES,
    summary="List models for a provider configuration before it is saved",
)
async def probe_my_provider_models_endpoint(
    request: Request,
    payload: ProviderProbeRequest,
    context: Annotated[AuthContext, Depends(get_completed_auth_context)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> ProviderModelsResponse:
    settings: Settings = request.app.state.settings
    return await probe_provider_models(session, context.user, settings, payload)


@router.patch(
    "/providers/{provider_id}",
    response_model=ProviderResponse,
    responses=_RESPONSES,
    summary="Update one provider owned by the current user",
)
async def update_my_provider_endpoint(
    request: Request,
    provider_id: UUID,
    payload: ProviderPatchRequest,
    context: Annotated[AuthContext, Depends(get_completed_auth_context)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> ProviderResponse:
    settings: Settings = request.app.state.settings
    return await update_provider(session, context.user, settings, provider_id, payload)


@router.delete(
    "/providers/{provider_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses=_RESPONSES,
    summary="Delete one provider owned by the current user",
)
async def delete_my_provider_endpoint(
    provider_id: UUID,
    context: Annotated[AuthContext, Depends(get_completed_auth_context)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> Response:
    await delete_provider(session, context.user, provider_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/providers/{provider_id}/test",
    response_model=ProviderTestResponse,
    responses=_RESPONSES,
    summary="Perform a real connection check on the current user's provider",
)
async def test_my_provider_endpoint(
    request: Request,
    provider_id: UUID,
    context: Annotated[AuthContext, Depends(get_completed_auth_context)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> ProviderTestResponse:
    settings: Settings = request.app.state.settings
    return await test_provider(session, context.user, settings, provider_id)


@router.post(
    "/providers/{provider_id}/models",
    response_model=ProviderModelsResponse,
    responses=_RESPONSES,
    summary="List models for the current user's provider or allow manual model entry",
)
async def my_provider_models_endpoint(
    request: Request,
    provider_id: UUID,
    context: Annotated[AuthContext, Depends(get_completed_auth_context)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> ProviderModelsResponse:
    settings: Settings = request.app.state.settings
    return await list_provider_models(session, context.user, settings, provider_id)


@router.get(
    "/memories",
    response_model=AiMemoryListResponse,
    responses=_RESPONSES,
    summary="List the AI memories the coach may use for the current user",
)
async def list_my_memories_endpoint(
    context: Annotated[AuthContext, Depends(get_completed_auth_context)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    kind: AiMemoryKind | None = None,
) -> AiMemoryListResponse:
    return await list_memories(session, context.user, kind=kind)


@router.post(
    "/memories",
    response_model=AiMemoryResponse,
    status_code=status.HTTP_201_CREATED,
    responses=_RESPONSES,
    summary="Add a memory the coach must keep for the current user",
)
async def create_my_memory_endpoint(
    payload: AiMemoryCreateRequest,
    context: Annotated[AuthContext, Depends(get_completed_auth_context)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> AiMemoryResponse:
    return await create_memory(session, context.user, payload)


@router.post(
    "/memories/clear-auto",
    response_model=AiMemoryClearResponse,
    responses=_RESPONSES,
    summary="Delete every automatically recorded memory of the current user",
)
async def clear_my_auto_memories_endpoint(
    context: Annotated[AuthContext, Depends(get_completed_auth_context)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> AiMemoryClearResponse:
    return await clear_auto_memories(session, context.user)


@router.patch(
    "/memories/{memory_id}",
    response_model=AiMemoryResponse,
    responses=_RESPONSES,
    summary="Edit one memory owned by the current user",
)
async def update_my_memory_endpoint(
    memory_id: UUID,
    payload: AiMemoryUpdateRequest,
    context: Annotated[AuthContext, Depends(get_completed_auth_context)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> AiMemoryResponse:
    return await update_memory(session, context.user, memory_id, payload)


@router.delete(
    "/memories/{memory_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses=_RESPONSES,
    summary="Delete one memory owned by the current user",
)
async def delete_my_memory_endpoint(
    memory_id: UUID,
    context: Annotated[AuthContext, Depends(get_completed_auth_context)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> Response:
    await delete_memory(session, context.user, memory_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
