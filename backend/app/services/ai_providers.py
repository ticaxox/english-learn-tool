from __future__ import annotations

import time
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.errors import AppError
from app.models.ai import AiProvider
from app.models.identity import User
from app.schemas.ai import (
    ProviderCreateRequest,
    ProviderListResponse,
    ProviderModelsResponse,
    ProviderPatchRequest,
    ProviderResponse,
    ProviderTestResponse,
)
from app.services.ai_secrets import ApiKeyCipher, mask_api_key
from app.services.ai_security import ProviderHttpClient, ProviderRequestError, validate_provider_url
from app.services.audit import add_audit_event
from app.services.users import require_admin


def _cipher(settings: Settings) -> ApiKeyCipher:
    return ApiKeyCipher(settings.secret_encryption_key.get_secret_value())


def _response(provider: AiProvider) -> ProviderResponse:
    return ProviderResponse(
        id=provider.id,
        name=provider.name,
        base_url=provider.base_url,
        api_key_masked=provider.api_key_mask,
        model_id=provider.model_id,
        priority=provider.priority,
        is_default=provider.is_default,
        timeout_seconds=provider.timeout_seconds,
        enabled=provider.enabled,
        custom_headers=provider.custom_headers,
        last_test_status=provider.last_test_status,
        last_test_error_code=provider.last_test_error_code,
        last_test_at=provider.last_test_at,
        last_test_latency_ms=provider.last_test_latency_ms,
        created_at=provider.created_at,
        updated_at=provider.updated_at,
    )


def _normalize_name(value: str) -> str:
    return " ".join(value.strip().lower().split())


async def _has_default(session: AsyncSession, *, exclude_id: UUID | None = None) -> bool:
    statement = select(AiProvider.id).where(
        AiProvider.is_default.is_(True), AiProvider.enabled.is_(True)
    )
    if exclude_id is not None:
        statement = statement.where(AiProvider.id != exclude_id)
    return await session.scalar(statement) is not None


async def _promote_default(session: AsyncSession, *, exclude_id: UUID | None = None) -> None:
    statement = select(AiProvider).where(AiProvider.enabled.is_(True))
    if exclude_id is not None:
        statement = statement.where(AiProvider.id != exclude_id)
    provider = await session.scalar(
        statement.order_by(AiProvider.priority.asc(), AiProvider.created_at.asc()).limit(1)
    )
    if provider is not None:
        provider.is_default = True


async def list_providers(
    session: AsyncSession, actor: User, *, include_disabled: bool = True
) -> ProviderListResponse:
    require_admin(actor)
    statement = select(AiProvider)
    if not include_disabled:
        statement = statement.where(AiProvider.enabled.is_(True))
    providers = list(
        (
            await session.scalars(
                statement.order_by(AiProvider.priority.asc(), AiProvider.created_at.asc())
            )
        ).all()
    )
    return ProviderListResponse(items=[_response(provider) for provider in providers])


async def create_provider(
    session: AsyncSession,
    actor: User,
    settings: Settings,
    payload: ProviderCreateRequest,
) -> ProviderResponse:
    require_admin(actor)
    base_url = await validate_provider_url(payload.base_url, settings)
    if payload.is_default:
        await session.execute(update(AiProvider).values(is_default=False))
    elif not await _has_default(session):
        payload = payload.model_copy(update={"is_default": payload.enabled})
    provider = AiProvider(
        name=payload.name,
        name_normalized=_normalize_name(payload.name),
        base_url=base_url,
        api_key_ciphertext=_cipher(settings).encrypt(payload.api_key),
        api_key_mask=mask_api_key(payload.api_key),
        model_id=payload.model_id,
        priority=payload.priority,
        is_default=payload.is_default,
        timeout_seconds=payload.timeout_seconds,
        enabled=payload.enabled,
        custom_headers=payload.custom_headers,
        created_by=actor.id,
    )
    session.add(provider)
    try:
        await session.flush()
        add_audit_event(
            session,
            action="ai.provider.created",
            target_type="ai_provider",
            outcome="success",
            actor=actor,
            target_id=provider.id,
            context={"name": provider.name, "is_default": provider.is_default},
        )
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise AppError(
            status_code=409,
            code="AI_PROVIDER_NAME_TAKEN",
            message="A provider with that name already exists.",
        ) from exc
    await session.refresh(provider)
    return _response(provider)


async def update_provider(
    session: AsyncSession,
    actor: User,
    settings: Settings,
    provider_id: UUID,
    payload: ProviderPatchRequest,
) -> ProviderResponse:
    require_admin(actor)
    provider = await session.scalar(
        select(AiProvider).where(AiProvider.id == provider_id).with_for_update()
    )
    if provider is None:
        raise AppError(
            status_code=404, code="AI_PROVIDER_NOT_FOUND", message="The provider was not found."
        )
    was_default = provider.is_default
    if payload.base_url is not None:
        provider.base_url = await validate_provider_url(payload.base_url, settings)
    if payload.name is not None:
        provider.name = payload.name
        provider.name_normalized = _normalize_name(payload.name)
    if payload.api_key is not None:
        provider.api_key_ciphertext = _cipher(settings).encrypt(payload.api_key)
        provider.api_key_mask = mask_api_key(payload.api_key)
    if payload.model_id is not None:
        provider.model_id = payload.model_id
    if payload.priority is not None:
        provider.priority = payload.priority
    if payload.timeout_seconds is not None:
        provider.timeout_seconds = payload.timeout_seconds
    if payload.custom_headers is not None:
        provider.custom_headers = payload.custom_headers
    if payload.enabled is not None:
        provider.enabled = payload.enabled
    if payload.is_default is True:
        await session.execute(
            update(AiProvider).where(AiProvider.id != provider.id).values(is_default=False)
        )
        provider.is_default = True
    elif payload.is_default is False:
        provider.is_default = False
    if not provider.enabled:
        provider.is_default = False
    if (
        not provider.is_default
        and provider.enabled
        and not await _has_default(session, exclude_id=provider.id)
    ):
        provider.is_default = True
    await session.flush()
    if was_default and not provider.enabled:
        await _promote_default(session, exclude_id=provider.id)
    add_audit_event(
        session,
        action="ai.provider.updated",
        target_type="ai_provider",
        outcome="success",
        actor=actor,
        target_id=provider.id,
        context={
            "name": provider.name,
            "enabled": provider.enabled,
            "is_default": provider.is_default,
        },
    )
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise AppError(
            status_code=409,
            code="AI_PROVIDER_CONFLICT",
            message="The provider configuration conflicts with an existing provider.",
        ) from exc
    await session.refresh(provider)
    return _response(provider)


async def delete_provider(session: AsyncSession, actor: User, provider_id: UUID) -> None:
    require_admin(actor)
    provider = await session.scalar(
        select(AiProvider).where(AiProvider.id == provider_id).with_for_update()
    )
    if provider is None:
        raise AppError(
            status_code=404, code="AI_PROVIDER_NOT_FOUND", message="The provider was not found."
        )
    was_default = provider.is_default
    await session.delete(provider)
    await session.flush()
    if was_default:
        await _promote_default(session, exclude_id=provider_id)
    add_audit_event(
        session,
        action="ai.provider.deleted",
        target_type="ai_provider",
        outcome="success",
        actor=actor,
        target_id=provider_id,
        context={"name": provider.name},
    )
    await session.commit()


async def test_provider(
    session: AsyncSession,
    actor: User,
    settings: Settings,
    provider_id: UUID,
) -> ProviderTestResponse:
    require_admin(actor)
    provider = await session.scalar(select(AiProvider).where(AiProvider.id == provider_id))
    if provider is None:
        raise AppError(
            status_code=404, code="AI_PROVIDER_NOT_FOUND", message="The provider was not found."
        )
    started = time.perf_counter()
    client = ProviderHttpClient(settings)
    try:
        models = await client.list_models(
            base_url=provider.base_url,
            api_key=_cipher(settings).decrypt(provider.api_key_ciphertext),
            custom_headers=provider.custom_headers,
            timeout_seconds=provider.timeout_seconds,
        )
    except ProviderRequestError as exc:
        latency = int((time.perf_counter() - started) * 1000)
        provider.last_test_status = "failed"
        provider.last_test_error_code = exc.code
        provider.last_test_at = datetime.now(UTC)
        provider.last_test_latency_ms = latency
        add_audit_event(
            session,
            action="ai.provider.tested",
            target_type="ai_provider",
            outcome="failure",
            actor=actor,
            target_id=provider.id,
            reason_code=exc.code,
            context={"name": provider.name, "latency_ms": latency},
        )
        await session.commit()
        return ProviderTestResponse(
            success=False,
            status="failed",
            latency_ms=latency,
            error_code=exc.code,
            error_message=exc.message,
        )
    latency = int((time.perf_counter() - started) * 1000)
    provider.last_test_status = "succeeded"
    provider.last_test_error_code = None
    provider.last_test_at = datetime.now(UTC)
    provider.last_test_latency_ms = latency
    add_audit_event(
        session,
        action="ai.provider.tested",
        target_type="ai_provider",
        outcome="success",
        actor=actor,
        target_id=provider.id,
        context={"name": provider.name, "latency_ms": latency},
    )
    await session.commit()
    return ProviderTestResponse(
        success=True,
        status="succeeded",
        latency_ms=latency,
        models=models,
    )


async def list_provider_models(
    session: AsyncSession,
    actor: User,
    settings: Settings,
    provider_id: UUID,
) -> ProviderModelsResponse:
    require_admin(actor)
    provider = await session.scalar(select(AiProvider).where(AiProvider.id == provider_id))
    if provider is None:
        raise AppError(
            status_code=404, code="AI_PROVIDER_NOT_FOUND", message="The provider was not found."
        )
    try:
        models = await ProviderHttpClient(settings).list_models(
            base_url=provider.base_url,
            api_key=_cipher(settings).decrypt(provider.api_key_ciphertext),
            custom_headers=provider.custom_headers,
            timeout_seconds=provider.timeout_seconds,
        )
    except ProviderRequestError as exc:
        return ProviderModelsResponse(success=False, error_code=exc.code, error_message=exc.message)
    return ProviderModelsResponse(success=True, models=models)
