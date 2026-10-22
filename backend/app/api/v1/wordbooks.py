from __future__ import annotations

from typing import Annotated, Literal
from urllib.parse import quote
from uuid import UUID

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    Header,
    Query,
    Request,
    Response,
    UploadFile,
    status,
)
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_completed_auth_context
from app.core.config import Settings
from app.core.errors import AppError
from app.db.session import get_db_session
from app.schemas.common import ErrorResponse
from app.schemas.wordbooks import (
    ActivationResponse,
    DeleteWordbookRequest,
    ExportCreateRequest,
    ImportConfirmRequest,
    ImportPreviewResponse,
    ImportRemapRequest,
    WordbookDetailResponse,
    WordbookJobResponse,
    WordbookListResponse,
    WordbookPatchRequest,
    WordbookSummary,
)
from app.services.auth import AuthContext
from app.services.wordbook_jobs import arq_job_id
from app.services.wordbooks import (
    activate_wordbook,
    confirm_wordbook_import,
    create_export_job,
    create_import_preview,
    download_export,
    get_export_job,
    get_wordbook_detail,
    get_wordbook_job,
    job_response,
    list_wordbooks,
    mark_wordbook_job_enqueue_failed,
    remap_import_preview,
    start_delete_wordbook,
    update_wordbook,
)

router = APIRouter(prefix="/wordbooks", tags=["wordbooks"])
exports_router = APIRouter(prefix="/exports", tags=["wordbook exports"])

_AUTH_RESPONSES = {
    401: {"model": ErrorResponse, "description": "Authentication is required."},
    403: {"model": ErrorResponse, "description": "The account may not perform this action."},
}
_NOT_FOUND = {404: {"model": ErrorResponse, "description": "The resource was not found."}}
_CONFLICT = {409: {"model": ErrorResponse, "description": "The current state conflicts."}}
_VALIDATION = {422: {"model": ErrorResponse, "description": "The request is invalid."}}


async def _enqueue_wordbook_job(
    request: Request,
    session: AsyncSession,
    *,
    actor: AuthContext,
    job: object,
) -> None:
    from app.models.wordbooks import WordbookJob

    if not isinstance(job, WordbookJob) or job.status != "queued":
        return
    pool = getattr(request.app.state, "arq", None)
    if pool is None:
        await mark_wordbook_job_enqueue_failed(session, actor=actor.user, job=job)
        raise AppError(
            status_code=503,
            code="WORDBOOK_QUEUE_UNAVAILABLE",
            message="The background queue is unavailable.",
        )
    try:
        await pool.enqueue_job(
            "process_wordbook_job",
            str(job.id),
            _job_id=arq_job_id(job.id),
        )
    except Exception as exc:
        await mark_wordbook_job_enqueue_failed(session, actor=actor.user, job=job)
        raise AppError(
            status_code=503,
            code="WORDBOOK_QUEUE_UNAVAILABLE",
            message="The background queue is unavailable.",
            headers={"Retry-After": "5"},
        ) from exc


@router.get(
    "",
    response_model=WordbookListResponse,
    responses={**_AUTH_RESPONSES, **_VALIDATION},
    summary="List visible organization and private wordbooks",
)
async def list_wordbooks_endpoint(
    context: Annotated[AuthContext, Depends(get_completed_auth_context)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    sort: Annotated[Literal["created_at", "updated_at", "name"], Query()] = "created_at",
    direction: Annotated[Literal["asc", "desc"], Query()] = "desc",
) -> WordbookListResponse:
    return await list_wordbooks(
        session,
        context.user,
        offset=offset,
        limit=limit,
        sort=sort,
        direction=direction,
    )


@router.post(
    "/import/preview",
    response_model=ImportPreviewResponse,
    status_code=status.HTTP_201_CREATED,
    responses={
        **_AUTH_RESPONSES,
        413: {"model": ErrorResponse, "description": "The upload exceeds 10 MiB."},
        415: {"model": ErrorResponse, "description": "The upload type or content is unsafe."},
        **_VALIDATION,
    },
    summary="Parse and persist a 24-hour wordbook import preview",
)
async def preview_wordbook_import_endpoint(
    request: Request,
    context: Annotated[AuthContext, Depends(get_completed_auth_context)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    file: Annotated[UploadFile, File(description="CSV, JSON, or TXT wordbook")],
    visibility: Annotated[Literal["organization", "private"], Form()] = "private",
    name: Annotated[str | None, Form(max_length=200)] = None,
    description: Annotated[str | None, Form(max_length=4000)] = None,
) -> ImportPreviewResponse:
    settings: Settings = request.app.state.settings
    return await create_import_preview(
        session,
        context.user,
        settings=settings,
        storage=request.app.state.wordbook_storage,
        upload=file,
        visibility=visibility,
        name=name,
        description=description,
    )


@router.patch(
    "/import/previews/{preview_id}",
    response_model=ImportPreviewResponse,
    responses={**_AUTH_RESPONSES, **_NOT_FOUND, **_CONFLICT, 410: {"model": ErrorResponse}},
    summary="Remap columns in an unexpired import preview",
)
async def remap_wordbook_preview_endpoint(
    preview_id: UUID,
    payload: ImportRemapRequest,
    request: Request,
    context: Annotated[AuthContext, Depends(get_completed_auth_context)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> ImportPreviewResponse:
    settings: Settings = request.app.state.settings
    return await remap_import_preview(
        session,
        context.user,
        settings=settings,
        storage=request.app.state.wordbook_storage,
        preview_id=preview_id,
        payload=payload,
    )


@router.post(
    "/import",
    response_model=WordbookJobResponse,
    status_code=status.HTTP_202_ACCEPTED,
    responses={
        **_AUTH_RESPONSES,
        **_NOT_FOUND,
        **_CONFLICT,
        410: {"model": ErrorResponse},
        503: {"model": ErrorResponse, "description": "The background queue is unavailable."},
    },
    summary="Queue an atomic import from a confirmed preview",
)
async def confirm_wordbook_import_endpoint(
    payload: ImportConfirmRequest,
    request: Request,
    idempotency_key: Annotated[
        str,
        Header(alias="Idempotency-Key", min_length=1, max_length=128),
    ],
    context: Annotated[AuthContext, Depends(get_completed_auth_context)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> WordbookJobResponse:
    settings: Settings = request.app.state.settings
    job = await confirm_wordbook_import(
        session,
        context.user,
        settings=settings,
        payload=payload,
        idempotency_key=idempotency_key,
    )
    await _enqueue_wordbook_job(request, session, actor=context, job=job)
    return job_response(job)


@router.get(
    "/jobs/{job_id}",
    response_model=WordbookJobResponse,
    responses={**_AUTH_RESPONSES, **_NOT_FOUND},
    summary="Poll a persisted import, export, or delete job",
)
async def wordbook_job_endpoint(
    job_id: UUID,
    context: Annotated[AuthContext, Depends(get_completed_auth_context)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> WordbookJobResponse:
    return await get_wordbook_job(session, context.user, job_id)


@router.get(
    "/{wordbook_id}",
    response_model=WordbookDetailResponse,
    responses={**_AUTH_RESPONSES, **_NOT_FOUND, **_VALIDATION},
    summary="Read a visible wordbook and paginated confirmed entries",
)
async def wordbook_detail_endpoint(
    wordbook_id: UUID,
    context: Annotated[AuthContext, Depends(get_completed_auth_context)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> WordbookDetailResponse:
    return await get_wordbook_detail(
        session,
        context.user,
        wordbook_id,
        offset=offset,
        limit=limit,
    )


@router.patch(
    "/{wordbook_id}",
    response_model=WordbookSummary,
    responses={**_AUTH_RESPONSES, **_NOT_FOUND, **_CONFLICT, **_VALIDATION},
    summary="Update wordbook metadata without changing confirmed entries",
)
async def patch_wordbook_endpoint(
    wordbook_id: UUID,
    payload: WordbookPatchRequest,
    context: Annotated[AuthContext, Depends(get_completed_auth_context)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> WordbookSummary:
    return await update_wordbook(
        session,
        context.user,
        wordbook_id=wordbook_id,
        payload=payload,
    )


@router.post(
    "/{wordbook_id}/activate",
    response_model=ActivationResponse,
    responses={**_AUTH_RESPONSES, **_NOT_FOUND, **_CONFLICT},
    summary="Idempotently activate a ready wordbook for the current user",
)
async def activate_wordbook_endpoint(
    wordbook_id: UUID,
    context: Annotated[AuthContext, Depends(get_completed_auth_context)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> ActivationResponse:
    return await activate_wordbook(session, context.user, wordbook_id)


@router.post(
    "/{wordbook_id}/export",
    response_model=WordbookJobResponse,
    status_code=status.HTTP_202_ACCEPTED,
    responses={
        **_AUTH_RESPONSES,
        **_NOT_FOUND,
        **_CONFLICT,
        503: {"model": ErrorResponse, "description": "The background queue is unavailable."},
    },
    summary="Queue a CSV, TXT, or font-complete PDF export",
)
async def create_wordbook_export_endpoint(
    wordbook_id: UUID,
    payload: ExportCreateRequest,
    request: Request,
    idempotency_key: Annotated[
        str,
        Header(alias="Idempotency-Key", min_length=1, max_length=128),
    ],
    context: Annotated[AuthContext, Depends(get_completed_auth_context)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> WordbookJobResponse:
    settings: Settings = request.app.state.settings
    job = await create_export_job(
        session,
        context.user,
        settings=settings,
        wordbook_id=wordbook_id,
        payload=payload,
        idempotency_key=idempotency_key,
    )
    await _enqueue_wordbook_job(request, session, actor=context, job=job)
    return job_response(job)


@router.delete(
    "/{wordbook_id}",
    response_model=WordbookJobResponse,
    status_code=status.HTTP_202_ACCEPTED,
    responses={
        **_AUTH_RESPONSES,
        400: {
            "model": ErrorResponse,
            "description": "WORDBOOK_NAME_CONFIRMATION_REQUIRED for organization wordbooks.",
        },
        **_NOT_FOUND,
        409: {
            "model": ErrorResponse,
            "description": (
                "WORDBOOK_NOT_READY while importing, WORDBOOK_DELETING when a delete "
                "task is already active, or IDEMPOTENCY_CONFLICT for a reused key."
            ),
        },
        503: {"model": ErrorResponse, "description": "The background queue is unavailable."},
    },
    summary="Queue idempotent deletion and immediate entry-visibility blocking",
    description=(
        "Marks the wordbook deleting before returning 202. Organization wordbooks require "
        "confirm_name to exactly match the wordbook name. Repeated requests return the same "
        "persisted delete task when one is queued, running, or complete."
    ),
)
async def delete_wordbook_endpoint(
    wordbook_id: UUID,
    request: Request,
    idempotency_key: Annotated[
        str,
        Header(alias="Idempotency-Key", min_length=1, max_length=128),
    ],
    context: Annotated[AuthContext, Depends(get_completed_auth_context)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    payload: DeleteWordbookRequest | None = None,
) -> WordbookJobResponse:
    settings: Settings = request.app.state.settings
    job = await start_delete_wordbook(
        session,
        context.user,
        settings=settings,
        wordbook_id=wordbook_id,
        payload=payload or DeleteWordbookRequest(),
        idempotency_key=idempotency_key,
    )
    await _enqueue_wordbook_job(request, session, actor=context, job=job)
    return job_response(job)


@exports_router.get(
    "/{job_id}",
    response_model=WordbookJobResponse,
    responses={**_AUTH_RESPONSES, **_NOT_FOUND},
    summary="Read an export job and short-lived download metadata",
)
async def export_job_endpoint(
    job_id: UUID,
    context: Annotated[AuthContext, Depends(get_completed_auth_context)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> WordbookJobResponse:
    return await get_export_job(session, context.user, job_id)


@exports_router.get(
    "/{job_id}/download",
    responses={
        **_AUTH_RESPONSES,
        **_NOT_FOUND,
        409: {"model": ErrorResponse, "description": "The export is not ready."},
        410: {"model": ErrorResponse, "description": "The download has expired."},
    },
    summary="Download an authorized export without exposing storage paths",
)
async def download_export_endpoint(
    job_id: UUID,
    context: Annotated[AuthContext, Depends(get_completed_auth_context)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    request: Request,
) -> Response:
    content, filename, content_type = await download_export(
        session,
        context.user,
        storage=request.app.state.wordbook_storage,
        job_id=job_id,
    )
    suffix = filename.rsplit(".", 1)[-1]
    disposition = f"attachment; filename=wordbook.{suffix}; filename*=UTF-8''{quote(filename)}"
    return Response(
        content=content,
        media_type=content_type,
        headers={
            "Content-Disposition": disposition,
            "Cache-Control": "private, no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )
