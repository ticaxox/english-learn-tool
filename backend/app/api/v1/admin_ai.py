from __future__ import annotations

from datetime import date
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_completed_auth_context
from app.core.config import Settings
from app.db.session import get_db_session
from app.schemas.ai import (
    AdminAiUsageResponse,
    PromptDetail,
    PromptListResponse,
    PromptUpdateRequest,
    ProviderCreateRequest,
    ProviderListResponse,
    ProviderModelsResponse,
    ProviderPatchRequest,
    ProviderResponse,
    ProviderTestResponse,
)
from app.schemas.common import ErrorResponse
from app.services.ai_prompts import get_prompt, list_prompts, update_prompt
from app.services.ai_providers import (
    create_provider,
    delete_provider,
    list_provider_models,
    list_providers,
    test_provider,
    update_provider,
)
from app.services.ai_usage import admin_usage
from app.services.auth import AuthContext
from app.services.users import require_admin

router = APIRouter(prefix="/admin/ai", tags=["admin ai"])

_ADMIN_RESPONSES = {
    401: {"model": ErrorResponse, "description": "Authentication is required."},
    403: {"model": ErrorResponse, "description": "Administrator permission is required."},
    404: {"model": ErrorResponse, "description": "The AI resource was not found."},
    409: {"model": ErrorResponse, "description": "The AI resource conflicts with current state."},
    422: {"model": ErrorResponse, "description": "The request is invalid."},
}


@router.get(
    "/providers",
    response_model=ProviderListResponse,
    responses=_ADMIN_RESPONSES,
    summary="List encrypted AI providers with masked credentials",
)
async def list_providers_endpoint(
    context: Annotated[AuthContext, Depends(get_completed_auth_context)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> ProviderListResponse:
    require_admin(context.user)
    return await list_providers(session, context.user)


@router.post(
    "/providers",
    response_model=ProviderResponse,
    status_code=status.HTTP_201_CREATED,
    responses=_ADMIN_RESPONSES,
    summary="Create an OpenAI-compatible provider with an encrypted key",
)
async def create_provider_endpoint(
    request: Request,
    payload: ProviderCreateRequest,
    context: Annotated[AuthContext, Depends(get_completed_auth_context)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> ProviderResponse:
    require_admin(context.user)
    settings: Settings = request.app.state.settings
    return await create_provider(session, context.user, settings, payload)


@router.patch(
    "/providers/{provider_id}",
    response_model=ProviderResponse,
    responses=_ADMIN_RESPONSES,
    summary="Update provider configuration while preserving masked keys",
)
async def update_provider_endpoint(
    request: Request,
    provider_id: UUID,
    payload: ProviderPatchRequest,
    context: Annotated[AuthContext, Depends(get_completed_auth_context)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> ProviderResponse:
    require_admin(context.user)
    settings: Settings = request.app.state.settings
    return await update_provider(session, context.user, settings, provider_id, payload)


@router.delete(
    "/providers/{provider_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses=_ADMIN_RESPONSES,
    summary="Delete a provider and promote the next enabled backup",
)
async def delete_provider_endpoint(
    provider_id: UUID,
    context: Annotated[AuthContext, Depends(get_completed_auth_context)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> Response:
    require_admin(context.user)
    await delete_provider(session, context.user, provider_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/providers/{provider_id}/test",
    response_model=ProviderTestResponse,
    responses=_ADMIN_RESPONSES,
    summary="Perform a real provider connection check",
)
async def test_provider_endpoint(
    request: Request,
    provider_id: UUID,
    context: Annotated[AuthContext, Depends(get_completed_auth_context)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> ProviderTestResponse:
    require_admin(context.user)
    settings: Settings = request.app.state.settings
    return await test_provider(session, context.user, settings, provider_id)


@router.post(
    "/providers/{provider_id}/models",
    response_model=ProviderModelsResponse,
    responses=_ADMIN_RESPONSES,
    summary="Fetch the provider model list or return a manual-entry fallback code",
)
async def provider_models_endpoint(
    request: Request,
    provider_id: UUID,
    context: Annotated[AuthContext, Depends(get_completed_auth_context)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> ProviderModelsResponse:
    require_admin(context.user)
    settings: Settings = request.app.state.settings
    return await list_provider_models(session, context.user, settings, provider_id)


@router.get(
    "/prompts",
    response_model=PromptListResponse,
    responses=_ADMIN_RESPONSES,
    summary="List editable AI prompts",
)
async def list_prompts_endpoint(
    context: Annotated[AuthContext, Depends(get_completed_auth_context)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> PromptListResponse:
    return await list_prompts(session, context.user)


@router.get(
    "/prompts/{prompt_key}",
    response_model=PromptDetail,
    responses=_ADMIN_RESPONSES,
    summary="Read one editable AI prompt",
)
async def get_prompt_endpoint(
    prompt_key: str,
    context: Annotated[AuthContext, Depends(get_completed_auth_context)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> PromptDetail:
    return await get_prompt(session, context.user, prompt_key)


@router.put(
    "/prompts/{prompt_key}",
    response_model=PromptDetail,
    responses=_ADMIN_RESPONSES,
    summary="Overwrite an AI prompt for future tasks",
)
async def update_prompt_endpoint(
    prompt_key: str,
    payload: PromptUpdateRequest,
    context: Annotated[AuthContext, Depends(get_completed_auth_context)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> PromptDetail:
    return await update_prompt(session, context.user, prompt_key, payload)


@router.get(
    "/usage",
    response_model=AdminAiUsageResponse,
    responses=_ADMIN_RESPONSES,
    summary="Read privacy-safe aggregate AI usage and task status",
)
async def usage_endpoint(
    request: Request,
    context: Annotated[AuthContext, Depends(get_completed_auth_context)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    date_from: Annotated[date | None, Query()] = None,
    date_to: Annotated[date | None, Query()] = None,
) -> AdminAiUsageResponse:
    settings: Settings = request.app.state.settings
    return await admin_usage(session, context.user, settings, date_from=date_from, date_to=date_to)
