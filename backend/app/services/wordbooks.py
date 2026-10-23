from __future__ import annotations

import hashlib
import hmac
import json
import secrets
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import UUID

from fastapi import UploadFile
from sqlalchemy import and_, func, or_, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.errors import AppError
from app.models.identity import User
from app.models.wordbooks import (
    Wordbook,
    WordbookActivation,
    WordbookDefinition,
    WordbookEntry,
    WordbookExample,
    WordbookImportPreview,
    WordbookJob,
)
from app.schemas.wordbooks import (
    ActivationResponse,
    DeleteWordbookRequest,
    ExportCreateRequest,
    ImportConfirmRequest,
    ImportPreviewResponse,
    ImportRemapRequest,
    WordbookDefinitionResponse,
    WordbookDetailResponse,
    WordbookEntryResponse,
    WordbookExampleResponse,
    WordbookJobResponse,
    WordbookListResponse,
    WordbookPatchRequest,
    WordbookSummary,
)
from app.services.audit import add_audit_event, commit_failure_audit
from app.services.auth import utcnow
from app.services.users import ensure_admin_for_write
from app.services.wordbook_parser import (
    ParseResult,
    WordbookParseError,
    parse_wordbook_bytes,
)
from app.services.wordbook_storage import LocalFileStorage

ACTIVATION_LOCK_BASE = 20261023003


def _is_active_admin(actor: User) -> bool:
    return actor.role == "admin" and actor.status == "active"


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _canonical_hash(*, file_sha256: str, values: dict[str, Any]) -> str:
    payload = json.dumps(
        {"file_sha256": file_sha256, **values},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _preview_hash(
    *,
    file_sha256: str,
    detected_format: str,
    encoding: str,
    delimiter: str | None,
    columns: list[str],
    mapping: dict[str, str | None],
    ignored_columns: list[str],
) -> str:
    return _canonical_hash(
        file_sha256=file_sha256,
        values={
            "format": detected_format,
            "encoding": encoding,
            "delimiter": delimiter,
            "columns": columns,
            "mapping": mapping,
            "ignored_columns": ignored_columns,
        },
    )


def _request_fingerprint(values: dict[str, Any]) -> str:
    payload = json.dumps(values, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _safe_filename(filename: str | None) -> str:
    if not filename:
        raise AppError(
            status_code=422,
            code="WORDBOOK_FILE_NAME_REQUIRED",
            message="A wordbook filename is required.",
        )
    if filename != Path(filename).name or ".." in Path(filename).parts:
        raise AppError(
            status_code=422,
            code="WORDBOOK_FILE_NAME_INVALID",
            message="The wordbook filename is invalid.",
        )
    return filename[:255]


def _default_name(filename: str) -> str:
    return (Path(filename).stem.strip() or "Imported wordbook")[:200]


def _safe_display_text(value: str | None, *, limit: int) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    return normalized[:limit] or None


def _parse_error_to_app_error(exc: WordbookParseError) -> AppError:
    status_code = 422
    if exc.code == "IMPORT_FILE_TOO_LARGE":
        status_code = 413
    elif exc.code in {"IMPORT_FILE_TYPE_UNSUPPORTED", "IMPORT_UNSAFE_CONTENT"}:
        status_code = 415
    return AppError(
        status_code=status_code,
        code=exc.code,
        message=exc.message,
        details=exc.details or None,
    )


async def _load_wordbook(
    session: AsyncSession,
    wordbook_id: UUID,
    *,
    lock: bool = False,
    include_deleted: bool = False,
) -> Wordbook:
    statement = select(Wordbook).where(Wordbook.id == wordbook_id)
    if not include_deleted:
        statement = statement.where(Wordbook.status != "deleted")
    if lock:
        statement = statement.with_for_update()
    book = await session.scalar(statement)
    if book is None:
        raise AppError(
            status_code=404,
            code="WORDBOOK_NOT_FOUND",
            message="The wordbook was not found.",
        )
    return book


def _can_view(book: Wordbook, actor: User) -> bool:
    if book.visibility == "organization":
        return actor.status == "active"
    return book.owner_id == actor.id


def _ensure_can_view(book: Wordbook, actor: User) -> None:
    if not _can_view(book, actor):
        raise AppError(
            status_code=404,
            code="WORDBOOK_NOT_FOUND",
            message="The wordbook was not found.",
        )


async def _ensure_can_write(session: AsyncSession, book: Wordbook, actor: User) -> None:
    if book.visibility == "organization":
        await ensure_admin_for_write(
            session,
            actor,
            action="wordbook.write",
            target_type="wordbook",
            target_id=book.id,
        )
    elif book.owner_id != actor.id:
        raise AppError(
            status_code=404,
            code="WORDBOOK_NOT_FOUND",
            message="The wordbook was not found.",
        )


async def _entry_count(session: AsyncSession, wordbook_id: UUID) -> int:
    return int(
        await session.scalar(
            select(func.count(WordbookEntry.id)).where(WordbookEntry.wordbook_id == wordbook_id)
        )
        or 0
    )


async def _active_wordbook_ids(session: AsyncSession, user_id: UUID) -> set[UUID]:
    return set(
        (
            await session.scalars(
                select(WordbookActivation.wordbook_id).where(WordbookActivation.user_id == user_id)
            )
        ).all()
    )


async def _summary(
    session: AsyncSession,
    book: Wordbook,
    *,
    active_ids: set[UUID] | None = None,
) -> WordbookSummary:
    return WordbookSummary(
        id=book.id,
        visibility=book.visibility,
        status=book.status,
        name=book.name,
        description=book.description,
        owner_id=book.owner_id,
        created_by=book.created_by,
        version=book.version,
        entry_count=await _entry_count(session, book.id),
        is_active=book.id in (active_ids or set()),
        created_at=book.created_at,
        updated_at=book.updated_at,
    )


async def list_wordbooks(
    session: AsyncSession,
    actor: User,
    *,
    offset: int = 0,
    limit: int = 20,
    sort: str = "created_at",
    direction: str = "desc",
) -> WordbookListResponse:
    if actor.status != "active":
        raise AppError(status_code=403, code="FORBIDDEN", message="The account is disabled.")
    visible = or_(
        and_(Wordbook.visibility == "organization", Wordbook.status != "deleted"),
        and_(Wordbook.owner_id == actor.id, Wordbook.status != "deleted"),
    )
    base = select(Wordbook).where(visible)
    total = int(await session.scalar(select(func.count()).select_from(base.subquery())) or 0)
    sort_column = {
        "created_at": Wordbook.created_at,
        "updated_at": Wordbook.updated_at,
        "name": Wordbook.name,
    }.get(sort, Wordbook.created_at)
    order = sort_column.asc() if direction == "asc" else sort_column.desc()
    books = list(
        (
            await session.scalars(
                base.order_by(order, Wordbook.id.asc()).offset(offset).limit(limit)
            )
        ).all()
    )
    active_ids = await _active_wordbook_ids(session, actor.id)
    items = [await _summary(session, book, active_ids=active_ids) for book in books]
    return WordbookListResponse(items=items, total=total, offset=offset, limit=limit)


async def get_wordbook_detail(
    session: AsyncSession,
    actor: User,
    wordbook_id: UUID,
    *,
    offset: int = 0,
    limit: int = 50,
) -> WordbookDetailResponse:
    book = await _load_wordbook(session, wordbook_id)
    _ensure_can_view(book, actor)
    total_entries = await _entry_count(session, book.id)
    entries = list(
        (
            await session.scalars(
                select(WordbookEntry)
                .where(WordbookEntry.wordbook_id == book.id)
                .order_by(WordbookEntry.sequence.asc(), WordbookEntry.id.asc())
                .offset(offset)
                .limit(limit)
            )
        ).all()
    )
    entry_ids = [entry.id for entry in entries]
    definitions_by_entry: dict[UUID, list[WordbookDefinition]] = {entry.id: [] for entry in entries}
    examples_by_definition: dict[UUID, list[WordbookExample]] = {}
    if entry_ids:
        definitions = list(
            (
                await session.scalars(
                    select(WordbookDefinition)
                    .where(WordbookDefinition.entry_id.in_(entry_ids))
                    .order_by(WordbookDefinition.sequence.asc(), WordbookDefinition.id.asc())
                )
            ).all()
        )
        for definition in definitions:
            definitions_by_entry[definition.entry_id].append(definition)
        definition_ids = [definition.id for definition in definitions]
        if definition_ids:
            examples = list(
                (
                    await session.scalars(
                        select(WordbookExample)
                        .where(WordbookExample.definition_id.in_(definition_ids))
                        .order_by(WordbookExample.sequence.asc(), WordbookExample.id.asc())
                    )
                ).all()
            )
            for example in examples:
                examples_by_definition.setdefault(example.definition_id, []).append(example)
    response_entries = [
        WordbookEntryResponse(
            id=entry.id,
            headword=entry.headword,
            normalized_headword=entry.normalized_headword,
            phonetic=entry.phonetic,
            definitions=[
                WordbookDefinitionResponse(
                    part_of_speech=definition.part_of_speech,
                    definition_en=definition.definition_en,
                    definition_zh=definition.definition_zh,
                    examples=[
                        WordbookExampleResponse(
                            example_en=example.example_en,
                            example_zh=example.example_zh,
                        )
                        for example in examples_by_definition.get(definition.id, [])
                    ],
                )
                for definition in definitions_by_entry[entry.id]
            ],
        )
        for entry in entries
    ]
    active_ids = await _active_wordbook_ids(session, actor.id)
    return WordbookDetailResponse(
        wordbook=await _summary(session, book, active_ids=active_ids),
        entries=response_entries,
        total_entries=total_entries,
        offset=offset,
        limit=limit,
    )


def _preview_response(
    preview: WordbookImportPreview, token: str | None = None
) -> ImportPreviewResponse:
    return ImportPreviewResponse(
        preview_id=preview.id,
        preview_token=token or "",
        preview_hash=preview.preview_hash,
        filename=preview.source_filename,
        detected_format=preview.detected_format,
        encoding=preview.encoding,
        delimiter=preview.delimiter,
        columns=preview.columns,
        suggested_mapping=preview.suggested_mapping,
        mapping=preview.mapping,
        ignored_columns=preview.ignored_columns,
        sample_rows=preview.sample_rows,
        total_rows=preview.total_rows,
        valid_rows=preview.valid_rows,
        warning_count=preview.warning_count,
        error_count=preview.error_count,
        warnings=preview.warnings,
        errors=preview.errors,
        expires_at=preview.expires_at,
        status=preview.status,
        requested_name=preview.requested_name,
        requested_description=preview.requested_description,
        requested_visibility=preview.requested_visibility,
    )


def _apply_parse_result(
    preview: WordbookImportPreview,
    result: ParseResult,
    *,
    preview_hash: str,
) -> None:
    preview.detected_format = result.detected_format
    preview.encoding = result.encoding
    preview.delimiter = result.delimiter
    preview.columns = result.columns
    preview.suggested_mapping = result.suggested_mapping
    preview.mapping = result.mapping
    preview.ignored_columns = result.ignored_columns
    preview.sample_rows = result.sample_rows
    preview.warnings = result.warnings
    preview.errors = result.errors
    preview.total_rows = result.total_rows
    preview.valid_rows = result.valid_rows
    preview.warning_count = result.warning_count
    preview.error_count = result.error_count
    preview.preview_hash = preview_hash


async def create_import_preview(
    session: AsyncSession,
    actor: User,
    *,
    settings: Settings,
    storage: LocalFileStorage,
    upload: UploadFile,
    visibility: str = "private",
    name: str | None = None,
    description: str | None = None,
) -> ImportPreviewResponse:
    source_filename = _safe_filename(upload.filename)
    if visibility not in {"private", "organization"}:
        raise AppError(
            status_code=422,
            code="WORDBOOK_VISIBILITY_INVALID",
            message="Unknown visibility.",
        )
    if visibility == "organization":
        await ensure_admin_for_write(
            session,
            actor,
            action="wordbook.import.preview",
            target_type="wordbook",
        )
    raw = await upload.read(settings.wordbook_max_bytes + 1)
    try:
        parsed = parse_wordbook_bytes(
            raw,
            source_filename,
            max_bytes=settings.wordbook_max_bytes,
            max_entries=settings.wordbook_max_entries,
        )
    except WordbookParseError as exc:
        await commit_failure_audit(
            session,
            actor=actor,
            action="wordbook.import.preview",
            target_type="wordbook",
            reason_code=exc.code,
        )
        raise _parse_error_to_app_error(exc) from exc

    storage_key = await storage.save_bytes(
        raw,
        extension=parsed.detected_format,
        prefix="preview",
    )
    token = secrets.token_urlsafe(32)
    file_sha256 = hashlib.sha256(raw).hexdigest()
    preview_hash = _preview_hash(
        file_sha256=file_sha256,
        detected_format=parsed.detected_format,
        encoding=parsed.encoding,
        delimiter=parsed.delimiter,
        columns=parsed.columns,
        mapping=parsed.mapping,
        ignored_columns=parsed.ignored_columns,
    )
    requested_name = _safe_display_text(name, limit=200) or _default_name(source_filename)
    preview = WordbookImportPreview(
        created_by=actor.id,
        storage_key=storage_key,
        source_filename=source_filename,
        file_sha256=file_sha256,
        file_size=len(raw),
        detected_format=parsed.detected_format,
        encoding=parsed.encoding,
        delimiter=parsed.delimiter,
        columns=parsed.columns,
        suggested_mapping=parsed.suggested_mapping,
        mapping=parsed.mapping,
        ignored_columns=parsed.ignored_columns,
        sample_rows=parsed.sample_rows,
        warnings=parsed.warnings,
        errors=parsed.errors,
        total_rows=parsed.total_rows,
        valid_rows=parsed.valid_rows,
        warning_count=parsed.warning_count,
        error_count=parsed.error_count,
        preview_token_hash=_hash_token(token),
        preview_hash=preview_hash,
        requested_name=requested_name,
        requested_description=_safe_display_text(description, limit=4000),
        requested_visibility=visibility,
        status="previewed",
        expires_at=utcnow() + timedelta(minutes=settings.wordbook_preview_ttl_minutes),
    )
    session.add(preview)
    try:
        await session.flush()
        add_audit_event(
            session,
            actor=actor,
            action="wordbook.import.preview",
            target_type="wordbook_preview",
            target_id=preview.id,
            outcome="success",
            context={
                "format": parsed.detected_format,
                "total_rows": parsed.total_rows,
                "valid_rows": parsed.valid_rows,
                "error_count": parsed.error_count,
                "visibility": visibility,
            },
        )
        await session.commit()
    except Exception:
        await session.rollback()
        await storage.delete(storage_key)
        raise
    return _preview_response(preview, token)


async def _owned_preview(
    session: AsyncSession,
    actor: User,
    preview_id: UUID,
    *,
    lock: bool = False,
) -> WordbookImportPreview:
    statement = select(WordbookImportPreview).where(
        WordbookImportPreview.id == preview_id,
        WordbookImportPreview.created_by == actor.id,
    )
    if lock:
        statement = statement.with_for_update()
    preview = await session.scalar(statement)
    if preview is None:
        raise AppError(
            status_code=404,
            code="WORDBOOK_PREVIEW_NOT_FOUND",
            message="The wordbook import preview was not found.",
        )
    return preview


def _verify_preview_token(preview: WordbookImportPreview, token: str) -> None:
    if not hmac.compare_digest(preview.preview_token_hash, _hash_token(token)):
        raise AppError(
            status_code=404,
            code="WORDBOOK_PREVIEW_NOT_FOUND",
            message="The wordbook import preview was not found.",
        )


async def _ensure_preview_usable(
    session: AsyncSession,
    preview: WordbookImportPreview,
    *,
    token: str,
    preview_hash: str | None = None,
) -> None:
    _verify_preview_token(preview, token)
    if preview.status == "expired" or preview.expires_at <= utcnow():
        preview.status = "expired"
        await session.commit()
        raise AppError(
            status_code=410,
            code="WORDBOOK_PREVIEW_EXPIRED",
            message="The wordbook import preview has expired.",
        )
    if preview.status != "previewed":
        raise AppError(
            status_code=409,
            code="WORDBOOK_PREVIEW_ALREADY_USED",
            message="The wordbook import preview has already been used.",
        )
    if preview_hash is not None and not hmac.compare_digest(preview.preview_hash, preview_hash):
        raise AppError(
            status_code=409,
            code="WORDBOOK_PREVIEW_MISMATCH",
            message="The preview hash does not match the current mapping and content.",
        )


async def remap_import_preview(
    session: AsyncSession,
    actor: User,
    *,
    settings: Settings,
    storage: LocalFileStorage,
    preview_id: UUID,
    payload: ImportRemapRequest,
) -> ImportPreviewResponse:
    preview = await _owned_preview(session, actor, preview_id, lock=True)
    await _ensure_preview_usable(session, preview, token=payload.preview_token)
    raw = await storage.read_bytes(preview.storage_key)
    if hashlib.sha256(raw).hexdigest() != preview.file_sha256:
        raise AppError(
            status_code=409,
            code="WORDBOOK_PREVIEW_CONTENT_CHANGED",
            message="The stored upload no longer matches the preview.",
        )
    try:
        parsed = parse_wordbook_bytes(
            raw,
            preview.source_filename,
            mapping=payload.mapping,
            ignored_columns=payload.ignored_columns,
            max_bytes=settings.wordbook_max_bytes,
            max_entries=settings.wordbook_max_entries,
        )
    except WordbookParseError as exc:
        await commit_failure_audit(
            session,
            actor=actor,
            action="wordbook.import.remap",
            target_type="wordbook_preview",
            target_id=preview.id,
            reason_code=exc.code,
        )
        raise _parse_error_to_app_error(exc) from exc
    preview_hash = _preview_hash(
        file_sha256=preview.file_sha256,
        detected_format=parsed.detected_format,
        encoding=parsed.encoding,
        delimiter=parsed.delimiter,
        columns=parsed.columns,
        mapping=parsed.mapping,
        ignored_columns=parsed.ignored_columns,
    )
    _apply_parse_result(preview, parsed, preview_hash=preview_hash)
    add_audit_event(
        session,
        actor=actor,
        action="wordbook.import.remap",
        target_type="wordbook_preview",
        target_id=preview.id,
        outcome="success",
        context={"format": parsed.detected_format, "valid_rows": parsed.valid_rows},
    )
    await session.commit()
    return _preview_response(preview, payload.preview_token)


async def _find_idempotency_job(
    session: AsyncSession,
    *,
    owner_id: UUID,
    kind: str,
    idempotency_key: str,
) -> WordbookJob | None:
    return await session.scalar(
        select(WordbookJob).where(
            WordbookJob.owner_id == owner_id,
            WordbookJob.kind == kind,
            WordbookJob.idempotency_key == idempotency_key,
        )
    )


async def confirm_wordbook_import(
    session: AsyncSession,
    actor: User,
    *,
    settings: Settings,
    payload: ImportConfirmRequest,
    idempotency_key: str,
) -> WordbookJob:
    if len(idempotency_key) > 128:
        raise AppError(
            status_code=422,
            code="IDEMPOTENCY_KEY_INVALID",
            message="Idempotency-Key must be at most 128 characters.",
        )
    preview = await _owned_preview(session, actor, payload.preview_id, lock=True)
    fingerprint = _request_fingerprint(
        {
            "preview_id": str(payload.preview_id),
            "preview_hash": payload.preview_hash,
            "name": payload.name,
            "description": payload.description,
            "visibility": payload.visibility,
        }
    )
    existing = await _find_idempotency_job(
        session,
        owner_id=actor.id,
        kind="import",
        idempotency_key=idempotency_key,
    )
    if existing is not None:
        if existing.request_fingerprint != fingerprint:
            raise AppError(
                status_code=409,
                code="IDEMPOTENCY_CONFLICT",
                message="The idempotency key was already used with a different request.",
            )
        return existing
    await _ensure_preview_usable(
        session,
        preview,
        token=payload.preview_token,
        preview_hash=payload.preview_hash,
    )
    if preview.error_count or preview.valid_rows == 0:
        await commit_failure_audit(
            session,
            actor=actor,
            action="wordbook.import",
            target_type="wordbook_preview",
            target_id=preview.id,
            reason_code="WORDBOOK_PREVIEW_INVALID",
            context={"error_count": preview.error_count, "valid_rows": preview.valid_rows},
        )
        raise AppError(
            status_code=409,
            code="WORDBOOK_PREVIEW_INVALID",
            message="The preview contains errors and cannot be imported.",
        )
    if payload.visibility is not None and payload.visibility != preview.requested_visibility:
        raise AppError(
            status_code=409,
            code="WORDBOOK_VISIBILITY_MISMATCH",
            message="Visibility must match the preview request.",
        )
    if preview.requested_visibility == "organization":
        await ensure_admin_for_write(
            session,
            actor,
            action="wordbook.import",
            target_type="wordbook_preview",
            target_id=preview.id,
        )

    name = payload.name or preview.requested_name
    description = (
        payload.description if payload.description is not None else preview.requested_description
    )
    visibility = preview.requested_visibility
    book = Wordbook(
        visibility=visibility,
        status="importing",
        name=name,
        description=_safe_display_text(description, limit=4000),
        owner_id=actor.id if visibility == "private" else None,
        created_by=actor.id,
        book_metadata={
            "source_filename": preview.source_filename,
            "file_sha256": preview.file_sha256,
            "format": preview.detected_format,
            "encoding": preview.encoding,
        },
    )
    session.add(book)
    await session.flush()
    job = WordbookJob(
        owner_id=actor.id,
        kind="import",
        status="queued",
        idempotency_key=idempotency_key,
        request_fingerprint=fingerprint,
        wordbook_id=book.id,
        preview_id=preview.id,
        format=preview.detected_format,
        options={"mapping": preview.mapping, "ignored_columns": preview.ignored_columns},
        max_attempts=settings.wordbook_job_max_attempts,
    )
    session.add(job)
    preview.wordbook_id = book.id
    preview.status = "queued"
    preview.used_at = utcnow()
    add_audit_event(
        session,
        actor=actor,
        action="wordbook.import",
        target_type="wordbook",
        target_id=book.id,
        outcome="success",
        context={
            "job_id": str(job.id),
            "visibility": visibility,
            "format": preview.detected_format,
            "valid_rows": preview.valid_rows,
        },
    )
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise AppError(
            status_code=409,
            code="IDEMPOTENCY_CONFLICT",
            message="The idempotency key was already used.",
        ) from exc
    return job


async def _job_wordbook(session: AsyncSession, job: WordbookJob) -> Wordbook | None:
    if job.wordbook_id is None:
        return None
    return await session.scalar(select(Wordbook).where(Wordbook.id == job.wordbook_id))


async def _authorize_job(session: AsyncSession, actor: User, job: WordbookJob) -> None:
    if job.owner_id == actor.id:
        return
    if _is_active_admin(actor):
        book = await _job_wordbook(session, job)
        if book is not None and book.visibility == "organization":
            return
    raise AppError(
        status_code=404,
        code="WORDBOOK_JOB_NOT_FOUND",
        message="The wordbook job was not found.",
    )


def _download_url(job: WordbookJob) -> str | None:
    if (
        job.kind == "export"
        and job.status == "succeeded"
        and job.storage_key
        and job.download_expires_at is not None
        and job.download_expires_at > utcnow()
    ):
        return f"/api/v1/exports/{job.id}/download"
    return None


def job_response(job: WordbookJob) -> WordbookJobResponse:
    return WordbookJobResponse(
        job_id=job.id,
        kind=job.kind,
        status=job.status,
        progress=job.progress,
        wordbook_id=job.wordbook_id,
        error_code=job.error_code,
        error_message=job.error_message,
        result=job.result or {},
        download_url=_download_url(job),
        download_expires_at=job.download_expires_at,
        cleanup_status=job.cleanup_status,
        created_at=job.created_at,
        started_at=job.started_at,
        finished_at=job.finished_at,
    )


async def get_wordbook_job(
    session: AsyncSession,
    actor: User,
    job_id: UUID,
) -> WordbookJobResponse:
    job = await session.scalar(select(WordbookJob).where(WordbookJob.id == job_id))
    if job is None:
        raise AppError(
            status_code=404,
            code="WORDBOOK_JOB_NOT_FOUND",
            message="The wordbook job was not found.",
        )
    await _authorize_job(session, actor, job)
    return job_response(job)


async def get_export_job(
    session: AsyncSession,
    actor: User,
    job_id: UUID,
) -> WordbookJobResponse:
    job = await session.scalar(
        select(WordbookJob).where(
            WordbookJob.id == job_id,
            WordbookJob.kind == "export",
        )
    )
    if job is None:
        raise AppError(
            status_code=404,
            code="EXPORT_NOT_FOUND",
            message="The export job was not found.",
        )
    await _authorize_job(session, actor, job)
    return job_response(job)


async def record_wordbook_queue_failure(
    session: AsyncSession,
    *,
    job_id: UUID,
    reason_code: str,
    reason_message: str,
    increment_attempts: bool,
) -> WordbookJob:
    job = await session.scalar(
        select(WordbookJob).where(WordbookJob.id == job_id).with_for_update()
    )
    if job is None:
        await session.rollback()
        raise AppError(
            status_code=404,
            code="WORDBOOK_JOB_NOT_FOUND",
            message="The wordbook job was not found.",
        )
    if job.status in {"succeeded", "failed", "cancelled"}:
        await session.rollback()
        return job
    if increment_attempts:
        job.attempts += 1
    final_failure = job.attempts >= job.max_attempts
    job.status = "failed" if final_failure else "queued"
    job.progress = min(job.progress, 95)
    job.error_code = reason_code
    job.error_message = reason_message
    job.cleanup_status = "failed" if final_failure else "pending"
    job.finished_at = utcnow() if final_failure else None

    if job.wordbook_id is not None and job.kind in {"import", "delete"}:
        book = await _load_wordbook(session, job.wordbook_id, include_deleted=True)
        if job.kind == "import" and book.status == "importing":
            book.status = "failed" if final_failure else "importing"
            book.book_metadata = {
                **(book.book_metadata or {}),
                "import_error_code": reason_code,
            }
        if job.kind == "delete" and final_failure and book.status == "deleting":
            book.status = "ready"
            book.book_metadata = {
                **(book.book_metadata or {}),
                "delete_error_code": reason_code,
            }

    if job.kind == "import" and job.preview_id is not None and final_failure:
        preview = await session.scalar(
            select(WordbookImportPreview)
            .where(WordbookImportPreview.id == job.preview_id)
            .with_for_update()
        )
        if preview is not None:
            preview.status = "failed"

    add_audit_event(
        session,
        actor_id=job.owner_id,
        action=f"wordbook.{job.kind}.queue_failed",
        target_type="wordbook",
        target_id=job.wordbook_id,
        outcome="failure",
        reason_code=reason_code,
        context={
            "job_id": str(job.id),
            "attempt": job.attempts,
            "final": final_failure,
        },
    )
    await session.commit()
    return job


async def create_export_job(
    session: AsyncSession,
    actor: User,
    *,
    settings: Settings,
    wordbook_id: UUID,
    payload: ExportCreateRequest,
    idempotency_key: str,
) -> WordbookJob:
    if len(idempotency_key) > 128:
        raise AppError(
            status_code=422,
            code="IDEMPOTENCY_KEY_INVALID",
            message="Idempotency-Key must be at most 128 characters.",
        )
    book = await _load_wordbook(session, wordbook_id)
    _ensure_can_view(book, actor)
    if book.visibility == "organization":
        await ensure_admin_for_write(
            session,
            actor,
            action="wordbook.export",
            target_type="wordbook",
            target_id=book.id,
        )
    elif book.owner_id != actor.id:
        raise AppError(
            status_code=404,
            code="WORDBOOK_NOT_FOUND",
            message="The wordbook was not found.",
        )
    if book.status != "ready":
        raise AppError(
            status_code=409,
            code="WORDBOOK_NOT_READY",
            message="Only ready wordbooks can be exported.",
        )
    fingerprint = _request_fingerprint(
        {
            "wordbook_id": str(book.id),
            "format": payload.format,
            "page_rows": payload.page_rows,
            "columns": payload.columns,
        }
    )
    existing = await _find_idempotency_job(
        session,
        owner_id=actor.id,
        kind="export",
        idempotency_key=idempotency_key,
    )
    if existing is not None:
        if existing.request_fingerprint != fingerprint:
            raise AppError(
                status_code=409,
                code="IDEMPOTENCY_CONFLICT",
                message="The idempotency key was already used with a different request.",
            )
        return existing
    job = WordbookJob(
        owner_id=actor.id,
        kind="export",
        status="queued",
        idempotency_key=idempotency_key,
        request_fingerprint=fingerprint,
        wordbook_id=book.id,
        format=payload.format,
        options={
            "page_rows": payload.page_rows or settings.wordbook_pdf_page_rows,
            "columns": payload.columns or settings.wordbook_pdf_columns,
        },
        max_attempts=settings.wordbook_job_max_attempts,
    )
    session.add(job)
    await session.flush()
    add_audit_event(
        session,
        actor=actor,
        action="wordbook.export",
        target_type="wordbook",
        target_id=book.id,
        outcome="success",
        context={"job_id": str(job.id), "format": payload.format},
    )
    await session.commit()
    return job


async def start_delete_wordbook(
    session: AsyncSession,
    actor: User,
    *,
    settings: Settings,
    wordbook_id: UUID,
    payload: DeleteWordbookRequest,
    idempotency_key: str,
) -> WordbookJob:
    book = await _load_wordbook(session, wordbook_id, lock=True, include_deleted=True)
    _ensure_can_view(book, actor)
    await _ensure_can_write(session, book, actor)
    existing = await session.scalar(
        select(WordbookJob)
        .where(
            WordbookJob.wordbook_id == book.id,
            WordbookJob.kind == "delete",
            WordbookJob.status.in_(("queued", "running", "succeeded")),
        )
        .order_by(WordbookJob.created_at.desc())
        .limit(1)
    )
    if existing is not None:
        return existing
    if book.status == "deleted":
        raise AppError(
            status_code=404,
            code="WORDBOOK_NOT_FOUND",
            message="The wordbook was not found.",
        )
    if book.status == "importing":
        raise AppError(
            status_code=409,
            code="WORDBOOK_NOT_READY",
            message="An importing wordbook cannot be deleted until the import finishes.",
        )
    if book.visibility == "organization":
        if not payload.confirm_name or payload.confirm_name.strip() != book.name:
            raise AppError(
                status_code=400,
                code="WORDBOOK_NAME_CONFIRMATION_REQUIRED",
                message="The exact organization wordbook name is required.",
            )
    if len(idempotency_key) > 128:
        raise AppError(
            status_code=422,
            code="IDEMPOTENCY_KEY_INVALID",
            message="Idempotency-Key must be at most 128 characters.",
        )
    fingerprint = _request_fingerprint(
        {"wordbook_id": str(book.id), "confirm_name": payload.confirm_name}
    )
    prior = await _find_idempotency_job(
        session,
        owner_id=actor.id,
        kind="delete",
        idempotency_key=idempotency_key,
    )
    if prior is not None:
        if prior.request_fingerprint != fingerprint:
            raise AppError(
                status_code=409,
                code="IDEMPOTENCY_CONFLICT",
                message="The idempotency key was already used with a different request.",
            )
        return prior
    book.status = "deleting"
    job = WordbookJob(
        owner_id=actor.id,
        kind="delete",
        status="queued",
        idempotency_key=idempotency_key,
        request_fingerprint=fingerprint,
        wordbook_id=book.id,
        max_attempts=settings.wordbook_job_max_attempts,
    )
    session.add(job)
    await session.flush()
    add_audit_event(
        session,
        actor=actor,
        action="wordbook.delete",
        target_type="wordbook",
        target_id=book.id,
        outcome="success",
        context={"job_id": str(job.id), "visibility": book.visibility},
    )
    await session.commit()
    return job


async def activate_wordbook(
    session: AsyncSession,
    actor: User,
    wordbook_id: UUID,
) -> ActivationResponse:
    book = await _load_wordbook(session, wordbook_id)
    _ensure_can_view(book, actor)
    if book.status != "ready":
        raise AppError(
            status_code=409,
            code="WORDBOOK_NOT_READY",
            message="Only ready wordbooks can be activated.",
        )
    lock_key = ACTIVATION_LOCK_BASE + (actor.id.int % 2_000_000_000)
    await session.execute(text("SELECT pg_advisory_xact_lock(:lock_key)"), {"lock_key": lock_key})
    activation = await session.scalar(
        select(WordbookActivation).where(WordbookActivation.user_id == actor.id)
    )
    now = utcnow()
    if activation is None:
        activation = WordbookActivation(
            user_id=actor.id,
            wordbook_id=book.id,
            activated_at=now,
        )
        session.add(activation)
    else:
        activation.wordbook_id = book.id
        activation.activated_at = now
    add_audit_event(
        session,
        actor=actor,
        action="wordbook.activate",
        target_type="wordbook",
        target_id=book.id,
        outcome="success",
    )
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise AppError(
            status_code=409,
            code="WORDBOOK_ACTIVATION_CONFLICT",
            message="The active wordbook could not be updated.",
        ) from exc
    return ActivationResponse(wordbook_id=book.id, activated_at=activation.activated_at)


async def update_wordbook(
    session: AsyncSession,
    actor: User,
    *,
    wordbook_id: UUID,
    payload: WordbookPatchRequest,
) -> WordbookSummary:
    book = await _load_wordbook(session, wordbook_id)
    _ensure_can_view(book, actor)
    await _ensure_can_write(session, book, actor)
    if book.status in {"deleting", "deleted"}:
        raise AppError(
            status_code=409,
            code="WORDBOOK_DELETING",
            message="A wordbook being deleted cannot be modified.",
        )
    if payload.name is not None:
        book.name = payload.name
    if "description" in payload.model_fields_set:
        book.description = payload.description
    add_audit_event(
        session,
        actor=actor,
        action="wordbook.update",
        target_type="wordbook",
        target_id=book.id,
        outcome="success",
        context={"visibility": book.visibility},
    )
    await session.commit()
    return await _summary(session, book, active_ids=await _active_wordbook_ids(session, actor.id))


async def download_export(
    session: AsyncSession,
    actor: User,
    *,
    storage: LocalFileStorage,
    job_id: UUID,
) -> tuple[bytes, str, str]:
    job = await session.scalar(select(WordbookJob).where(WordbookJob.id == job_id))
    if job is None:
        raise AppError(
            status_code=404,
            code="EXPORT_NOT_FOUND",
            message="The export job was not found.",
        )
    await _authorize_job(session, actor, job)
    if job.kind != "export" or job.status != "succeeded" or not job.storage_key:
        raise AppError(
            status_code=409,
            code="EXPORT_NOT_READY",
            message="The export is not ready for download.",
        )
    if job.download_expires_at is None or job.download_expires_at <= utcnow():
        raise AppError(
            status_code=410,
            code="EXPORT_DOWNLOAD_EXPIRED",
            message="The export download has expired.",
        )
    book = await _job_wordbook(session, job)
    safe_name = (
        (book.name if book else "wordbook").replace('"', "").replace("\r", "").replace("\n", "")
    )
    filename = f"{safe_name}-{job.id.hex[:8]}.{job.format or 'bin'}"
    content_type = {
        "csv": "text/csv; charset=utf-8",
        "txt": "text/plain; charset=utf-8",
        "pdf": "application/pdf",
    }.get(job.format or "", "application/octet-stream")
    return await storage.read_bytes(job.storage_key), filename, content_type


async def cleanup_expired_wordbook_artifacts(
    session: AsyncSession,
    storage: LocalFileStorage,
    *,
    now: datetime | None = None,
) -> dict[str, int]:
    current = now or utcnow()
    expired_jobs = list(
        (
            await session.scalars(
                select(WordbookJob).where(
                    WordbookJob.storage_key.is_not(None),
                    WordbookJob.download_expires_at.is_not(None),
                    WordbookJob.download_expires_at < current,
                    WordbookJob.cleanup_status != "completed",
                )
            )
        ).all()
    )
    for job in expired_jobs:
        await storage.delete(job.storage_key)
        job.cleanup_status = "completed"
    expired_previews = list(
        (
            await session.scalars(
                select(WordbookImportPreview).where(
                    WordbookImportPreview.expires_at < current,
                    WordbookImportPreview.status == "previewed",
                )
            )
        ).all()
    )
    for preview in expired_previews:
        await storage.delete(preview.storage_key)
        preview.status = "expired"
    await session.commit()
    return {"jobs": len(expired_jobs), "previews": len(expired_previews)}
