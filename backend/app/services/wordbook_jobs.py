from __future__ import annotations

import hashlib
import logging
from datetime import timedelta
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

from arq import Retry
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Settings
from app.models.wordbooks import (
    Wordbook,
    WordbookActivation,
    WordbookDefinition,
    WordbookEntry,
    WordbookExample,
    WordbookImportPreview,
    WordbookJob,
)
from app.services.audit import add_audit_event
from app.services.auth import utcnow
from app.services.wordbook_exports import (
    DEFAULT_CJK_FONT,
    ExportDefinition,
    ExportEntry,
    ExportExample,
    WordbookExportError,
    render_wordbook_export,
)
from app.services.wordbook_parser import WordbookParseError, parse_wordbook_bytes
from app.services.wordbook_storage import LocalFileStorage, WordbookStorageError

logger = logging.getLogger(__name__)


class WordbookJobError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def _session_factory(ctx: dict[str, Any]) -> async_sessionmaker[AsyncSession]:
    factory = ctx.get("session_factory")
    if factory is None:
        raise WordbookJobError(
            "WORDBOOK_WORKER_NOT_CONFIGURED",
            "The wordbook worker database is not configured.",
        )
    return factory


def _settings(ctx: dict[str, Any]) -> Settings:
    settings = ctx.get("settings")
    if not isinstance(settings, Settings):
        raise WordbookJobError(
            "WORDBOOK_WORKER_NOT_CONFIGURED",
            "The wordbook worker settings are not configured.",
        )
    return settings


def _storage(ctx: dict[str, Any]) -> LocalFileStorage:
    storage = ctx.get("wordbook_storage")
    if not isinstance(storage, LocalFileStorage):
        raise WordbookJobError(
            "WORDBOOK_WORKER_NOT_CONFIGURED",
            "The wordbook worker storage is not configured.",
        )
    return storage


def _safe_error(exc: Exception) -> tuple[str, str]:
    if isinstance(exc, WordbookJobError):
        return exc.code, exc.message
    if isinstance(exc, WordbookParseError):
        return exc.code, exc.message
    if isinstance(exc, WordbookExportError):
        return exc.code, exc.message
    if isinstance(exc, WordbookStorageError):
        return "WORDBOOK_STORAGE_UNAVAILABLE", "The wordbook artifact is unavailable."
    return "WORDBOOK_JOB_FAILED", "The wordbook background job failed."


async def _start_job(
    session: AsyncSession,
    job_id: UUID,
    *,
    stale_after_seconds: int,
) -> tuple[WordbookJob | None, dict[str, Any] | None]:
    job = await session.scalar(
        select(WordbookJob).where(WordbookJob.id == job_id).with_for_update()
    )
    if job is None:
        raise WordbookJobError("WORDBOOK_JOB_NOT_FOUND", "The wordbook job was not found.")
    if job.status in {"succeeded", "failed", "cancelled"}:
        result = dict(job.result or {})
        if job.status != "succeeded":
            result.update({"status": job.status, "error_code": job.error_code})
        await session.rollback()
        return None, result
    if job.status == "running":
        updated_at = job.updated_at
        if updated_at.tzinfo is None:
            updated_at = updated_at.replace(tzinfo=utcnow().tzinfo)
        if updated_at > utcnow() - timedelta(seconds=stale_after_seconds):
            await session.rollback()
            return None, {"status": "running"}
        add_audit_event(
            session,
            actor_id=job.owner_id,
            action=f"wordbook.{job.kind}.worker_interrupted",
            target_type="wordbook",
            target_id=job.wordbook_id,
            outcome="failure",
            reason_code="WORDBOOK_WORKER_INTERRUPTED",
            context={"job_id": str(job.id), "attempt": job.attempts},
        )
    job.attempts += 1
    if job.attempts > job.max_attempts:
        job.status = "failed"
        job.error_code = "WORDBOOK_RETRY_EXHAUSTED"
        job.error_message = "The wordbook job exhausted its retry budget."
        job.finished_at = utcnow()
        await session.commit()
        return None, {"status": "failed", "error_code": job.error_code}
    job.status = "running"
    job.progress = max(job.progress, 5)
    job.started_at = job.started_at or utcnow()
    job.finished_at = None
    job.error_code = None
    job.error_message = None
    await session.commit()
    return job, None


async def _process_import(
    session: AsyncSession,
    *,
    job: WordbookJob,
    settings: Settings,
    storage: LocalFileStorage,
) -> dict[str, Any]:
    if job.wordbook_id is None or job.preview_id is None:
        raise WordbookJobError(
            "WORDBOOK_IMPORT_SOURCE_MISSING",
            "The import source is unavailable.",
        )
    book = await session.scalar(
        select(Wordbook).where(Wordbook.id == job.wordbook_id).with_for_update()
    )
    preview = await session.scalar(
        select(WordbookImportPreview)
        .where(
            WordbookImportPreview.id == job.preview_id,
            WordbookImportPreview.created_by == job.owner_id,
        )
        .with_for_update()
    )
    if book is None or preview is None:
        raise WordbookJobError(
            "WORDBOOK_IMPORT_SOURCE_MISSING",
            "The import source is unavailable.",
        )
    if book.status == "ready" and preview.status == "completed":
        job.status = "succeeded"
        job.progress = 100
        job.result = {**(job.result or {}), "idempotent_replay": True}
        job.finished_at = utcnow()
        await session.commit()
        return job.result
    if book.status != "importing":
        raise WordbookJobError(
            "WORDBOOK_IMPORT_STATE_INVALID",
            "The wordbook is not in an importable state.",
        )
    raw = await storage.read_bytes(preview.storage_key)
    if hashlib.sha256(raw).hexdigest() != preview.file_sha256:
        raise WordbookJobError(
            "WORDBOOK_PREVIEW_CONTENT_CHANGED",
            "The stored import content no longer matches the preview.",
        )
    mapping = job.options.get("mapping") if job.options else None
    ignored_columns = job.options.get("ignored_columns") if job.options else None
    parsed = parse_wordbook_bytes(
        raw,
        preview.source_filename,
        mapping=mapping,
        ignored_columns=ignored_columns,
        max_bytes=settings.wordbook_max_bytes,
        max_entries=settings.wordbook_max_entries,
    )
    if parsed.error_count or not parsed.entries:
        raise WordbookJobError(
            "WORDBOOK_PREVIEW_INVALID",
            "The import preview contains errors and cannot be committed.",
        )

    await session.execute(delete(WordbookEntry).where(WordbookEntry.wordbook_id == book.id))
    entries: list[WordbookEntry] = []
    definitions: list[WordbookDefinition] = []
    examples: list[WordbookExample] = []
    for entry_sequence, parsed_entry in enumerate(parsed.entries):
        entry = WordbookEntry(
            id=uuid4(),
            wordbook_id=book.id,
            headword=parsed_entry.headword,
            normalized_headword=parsed_entry.normalized_headword,
            phonetic=parsed_entry.phonetic,
            sequence=entry_sequence,
        )
        entries.append(entry)
        for definition_sequence, parsed_definition in enumerate(parsed_entry.definitions):
            definition = WordbookDefinition(
                id=uuid4(),
                entry_id=entry.id,
                part_of_speech=parsed_definition.part_of_speech,
                definition_en=parsed_definition.definition_en,
                definition_zh=parsed_definition.definition_zh,
                sequence=definition_sequence,
            )
            definitions.append(definition)
            for example_sequence, parsed_example in enumerate(parsed_definition.examples):
                examples.append(
                    WordbookExample(
                        id=uuid4(),
                        definition_id=definition.id,
                        example_en=parsed_example.example_en,
                        example_zh=parsed_example.example_zh,
                        sequence=example_sequence,
                    )
                )
    session.add_all(entries)
    await session.flush()
    session.add_all(definitions)
    await session.flush()
    session.add_all(examples)
    await session.flush()

    result = {
        "entry_count": len(entries),
        "definition_count": len(definitions),
        "example_count": len(examples),
        "format": parsed.detected_format,
        "encoding": parsed.encoding,
    }
    book.status = "ready"
    book.version = str(int(book.version) + 1) if book.version.isdigit() else "1"
    book.book_metadata = {
        **(book.book_metadata or {}),
        "entry_count": len(entries),
        "definition_count": len(definitions),
        "example_count": len(examples),
        "import_job_id": str(job.id),
    }
    preview.status = "completed"
    job.status = "succeeded"
    job.progress = 100
    job.result = result
    job.error_code = None
    job.error_message = None
    job.cleanup_status = "completed"
    job.finished_at = utcnow()
    add_audit_event(
        session,
        actor_id=job.owner_id,
        action="wordbook.import.completed",
        target_type="wordbook",
        target_id=book.id,
        outcome="success",
        context={"job_id": str(job.id), **result},
    )
    preview_storage_key = preview.storage_key
    await session.commit()
    try:
        await storage.delete(preview_storage_key)
    except WordbookStorageError:
        logger.warning("wordbook.import.preview_cleanup_failed", extra={"job_id": str(job.id)})
    return result


async def _load_export_entries(session: AsyncSession, wordbook_id: UUID) -> tuple[ExportEntry, ...]:
    raw_entries = list(
        (
            await session.scalars(
                select(WordbookEntry)
                .where(WordbookEntry.wordbook_id == wordbook_id)
                .order_by(WordbookEntry.sequence.asc(), WordbookEntry.id.asc())
            )
        ).all()
    )
    if not raw_entries:
        return ()
    entry_ids = [entry.id for entry in raw_entries]
    raw_definitions = list(
        (
            await session.scalars(
                select(WordbookDefinition)
                .where(WordbookDefinition.entry_id.in_(entry_ids))
                .order_by(WordbookDefinition.sequence.asc(), WordbookDefinition.id.asc())
            )
        ).all()
    )
    definition_ids = [definition.id for definition in raw_definitions]
    raw_examples = (
        list(
            (
                await session.scalars(
                    select(WordbookExample)
                    .where(WordbookExample.definition_id.in_(definition_ids))
                    .order_by(WordbookExample.sequence.asc(), WordbookExample.id.asc())
                )
            ).all()
        )
        if definition_ids
        else []
    )
    examples_by_definition: dict[UUID, list[ExportExample]] = {}
    for example in raw_examples:
        examples_by_definition.setdefault(example.definition_id, []).append(
            ExportExample(example_en=example.example_en, example_zh=example.example_zh)
        )
    definitions_by_entry: dict[UUID, list[ExportDefinition]] = {}
    for definition in raw_definitions:
        definitions_by_entry.setdefault(definition.entry_id, []).append(
            ExportDefinition(
                part_of_speech=definition.part_of_speech,
                definition_en=definition.definition_en,
                definition_zh=definition.definition_zh,
                examples=tuple(examples_by_definition.get(definition.id, ())),
            )
        )
    return tuple(
        ExportEntry(
            headword=entry.headword,
            phonetic=entry.phonetic,
            definitions=tuple(definitions_by_entry.get(entry.id, ())),
        )
        for entry in raw_entries
    )


async def _process_export(
    session: AsyncSession,
    *,
    job: WordbookJob,
    settings: Settings,
    storage: LocalFileStorage,
) -> dict[str, Any]:
    if job.wordbook_id is None or job.format not in {"csv", "txt", "pdf"}:
        raise WordbookJobError(
            "WORDBOOK_EXPORT_SOURCE_MISSING",
            "The export source is unavailable.",
        )
    job_id = job.id
    wordbook_id = job.wordbook_id
    export_format = job.format
    options = dict(job.options or {})
    book = await session.scalar(select(Wordbook).where(Wordbook.id == wordbook_id))
    if book is None or book.status != "ready":
        raise WordbookJobError(
            "WORDBOOK_NOT_READY",
            "Only ready wordbooks can be exported.",
        )
    export_entries = await _load_export_entries(session, book.id)
    if not export_entries:
        raise WordbookJobError(
            "WORDBOOK_EXPORT_EMPTY",
            "The wordbook has no entries to export.",
        )
    await session.rollback()

    cjk_font = (
        Path(settings.wordbook_pdf_font_path)
        if settings.wordbook_pdf_font_path
        else DEFAULT_CJK_FONT
    )
    content = render_wordbook_export(
        export_entries,
        export_format=export_format,
        page_rows=int(options.get("page_rows", settings.wordbook_pdf_page_rows)),
        columns=int(options.get("columns", settings.wordbook_pdf_columns)),
        cjk_font=cjk_font,
    )
    storage_key = await storage.save_bytes(
        content,
        extension=export_format,
        prefix="export",
    )
    try:
        job = await session.scalar(
            select(WordbookJob).where(WordbookJob.id == job_id).with_for_update()
        )
        if job is None:
            raise WordbookJobError("WORDBOOK_JOB_NOT_FOUND", "The wordbook job was not found.")
        book = await session.scalar(
            select(Wordbook).where(Wordbook.id == wordbook_id).with_for_update()
        )
        if book is None or book.status != "ready":
            raise WordbookJobError(
                "WORDBOOK_DELETING",
                "The wordbook is no longer available for export.",
            )
        result = {
            "entry_count": len(export_entries),
            "format": export_format,
            "size_bytes": len(content),
        }
        job.status = "succeeded"
        job.progress = 100
        job.storage_key = storage_key
        job.download_expires_at = utcnow() + timedelta(minutes=settings.wordbook_export_ttl_minutes)
        job.result = result
        job.error_code = None
        job.error_message = None
        job.cleanup_status = "pending"
        job.finished_at = utcnow()
        add_audit_event(
            session,
            actor_id=job.owner_id,
            action="wordbook.export.completed",
            target_type="wordbook",
            target_id=book.id,
            outcome="success",
            context={"job_id": str(job.id), **result},
        )
        await session.commit()
        return result
    except Exception:
        await session.rollback()
        await storage.delete(storage_key)
        raise


async def _process_delete(
    session: AsyncSession,
    *,
    job: WordbookJob,
    storage: LocalFileStorage,
) -> dict[str, Any]:
    if job.wordbook_id is None:
        raise WordbookJobError(
            "WORDBOOK_DELETE_SOURCE_MISSING",
            "The wordbook deletion source is unavailable.",
        )
    book = await session.scalar(
        select(Wordbook).where(Wordbook.id == job.wordbook_id).with_for_update()
    )
    if book is None:
        raise WordbookJobError(
            "WORDBOOK_DELETE_SOURCE_MISSING",
            "The wordbook deletion source is unavailable.",
        )
    entry_count = len(
        (
            await session.scalars(
                select(WordbookEntry.id).where(WordbookEntry.wordbook_id == book.id)
            )
        ).all()
    )
    definition_count = int(
        await session.scalar(
            select(func.count(WordbookDefinition.id))
            .join(WordbookEntry, WordbookDefinition.entry_id == WordbookEntry.id)
            .where(WordbookEntry.wordbook_id == book.id)
        )
        or 0
    )
    example_count = int(
        await session.scalar(
            select(func.count(WordbookExample.id))
            .join(WordbookDefinition, WordbookExample.definition_id == WordbookDefinition.id)
            .join(WordbookEntry, WordbookDefinition.entry_id == WordbookEntry.id)
            .where(WordbookEntry.wordbook_id == book.id)
        )
        or 0
    )
    related_jobs = list(
        (
            await session.scalars(
                select(WordbookJob).where(
                    WordbookJob.wordbook_id == book.id,
                    WordbookJob.id != job.id,
                )
            )
        ).all()
    )
    previews = list(
        (
            await session.scalars(
                select(WordbookImportPreview).where(WordbookImportPreview.wordbook_id == book.id)
            )
        ).all()
    )
    storage_keys = {
        key
        for key in [
            *(related.storage_key for related in related_jobs),
            *(preview.storage_key for preview in previews),
        ]
        if key
    }
    for storage_key in storage_keys:
        await storage.delete(storage_key)

    await session.execute(
        delete(WordbookActivation).where(WordbookActivation.wordbook_id == book.id)
    )
    await session.execute(delete(WordbookEntry).where(WordbookEntry.wordbook_id == book.id))
    job.preview_id = None
    await session.execute(
        delete(WordbookJob).where(
            WordbookJob.wordbook_id == book.id,
            WordbookJob.id != job.id,
        )
    )
    await session.execute(
        delete(WordbookImportPreview).where(WordbookImportPreview.wordbook_id == book.id)
    )
    result = {
        "deleted_entries": entry_count,
        "deleted_definitions": definition_count,
        "deleted_examples": example_count,
        "deleted_artifacts": len(storage_keys),
    }
    book.status = "deleted"
    book.description = None
    book.book_metadata = {"deleted": True}
    job.status = "succeeded"
    job.progress = 100
    job.result = result
    job.error_code = None
    job.error_message = None
    job.cleanup_status = "completed"
    job.finished_at = utcnow()
    add_audit_event(
        session,
        actor_id=job.owner_id,
        action="wordbook.delete.completed",
        target_type="wordbook",
        target_id=book.id,
        outcome="success",
        context={"job_id": str(job.id), **result},
    )
    await session.commit()
    return result


async def _record_failure(ctx: dict[str, Any], job_id: UUID, exc: Exception) -> bool:
    code, message = _safe_error(exc)
    factory = _session_factory(ctx)
    async with factory() as session:
        job = await session.scalar(
            select(WordbookJob).where(WordbookJob.id == job_id).with_for_update()
        )
        if job is None or job.status == "succeeded":
            await session.rollback()
            return True
        final_failure = job.attempts >= job.max_attempts
        job.status = "failed" if final_failure else "queued"
        job.progress = min(job.progress, 95)
        job.error_code = code
        job.error_message = message
        job.cleanup_status = "failed" if final_failure else "pending"
        if final_failure:
            job.finished_at = utcnow()
        if job.kind == "import" and job.wordbook_id is not None:
            book = await session.scalar(
                select(Wordbook).where(Wordbook.id == job.wordbook_id).with_for_update()
            )
            if book is not None and book.status == "importing":
                book.status = "failed" if final_failure else "importing"
                book.book_metadata = {
                    **(book.book_metadata or {}),
                    "import_error_code": code,
                }
        if job.kind == "delete" and job.wordbook_id is not None and final_failure:
            book = await session.scalar(
                select(Wordbook).where(Wordbook.id == job.wordbook_id).with_for_update()
            )
            if book is not None and book.status == "deleting":
                book.status = "ready"
                book.book_metadata = {
                    **(book.book_metadata or {}),
                    "delete_error_code": code,
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
            action=f"wordbook.{job.kind}.worker_failed",
            target_type="wordbook",
            target_id=job.wordbook_id,
            outcome="failure",
            reason_code=code,
            context={"job_id": str(job.id), "attempt": job.attempts, "final": final_failure},
        )
        await session.commit()
        return final_failure


async def process_wordbook_job(ctx: dict[str, Any], job_id: str) -> dict[str, Any]:
    parsed_job_id = UUID(job_id)
    factory = _session_factory(ctx)
    async with factory() as session:
        job, completed_result = await _start_job(
            session,
            parsed_job_id,
            stale_after_seconds=_settings(ctx).wordbook_job_stale_seconds,
        )
        if completed_result is not None:
            return completed_result
        assert job is not None
        attempt = job.attempts
        try:
            if job.kind == "import":
                return await _process_import(
                    session,
                    job=job,
                    settings=_settings(ctx),
                    storage=_storage(ctx),
                )
            if job.kind == "export":
                return await _process_export(
                    session,
                    job=job,
                    settings=_settings(ctx),
                    storage=_storage(ctx),
                )
            if job.kind == "delete":
                return await _process_delete(session, job=job, storage=_storage(ctx))
            raise WordbookJobError(
                "WORDBOOK_JOB_KIND_INVALID",
                "The wordbook job kind is unsupported.",
            )
        except Exception as exc:
            await session.rollback()
            logger.exception(
                "wordbook.job.failed",
                extra={"job_id": str(parsed_job_id), "error_code": _safe_error(exc)[0]},
            )
            final_failure = await _record_failure(ctx, parsed_job_id, exc)
            if final_failure:
                return {"status": "failed", "error_code": _safe_error(exc)[0]}
            raise Retry(defer=min(60, 2 ** max(1, attempt))) from exc
