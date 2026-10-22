from __future__ import annotations

import asyncio
import csv
import io
import json
from datetime import timedelta
from uuid import UUID, uuid4

import pytest
from fastapi import UploadFile
from sqlalchemy import delete, func, select

from app.core.errors import AppError
from app.core.security import hash_password
from app.models.identity import AuditLog, User, UserProfile
from app.models.wordbooks import (
    Wordbook,
    WordbookActivation,
    WordbookDefinition,
    WordbookEntry,
    WordbookExample,
    WordbookImportPreview,
    WordbookJob,
)
from app.schemas.wordbooks import DeleteWordbookRequest, ImportConfirmRequest, ImportRemapRequest
from app.services.auth import utcnow
from app.services.wordbook_jobs import process_wordbook_job
from app.services.wordbooks import (
    activate_wordbook,
    confirm_wordbook_import,
    create_import_preview,
    remap_import_preview,
    start_delete_wordbook,
)
from tests.conftest import TEST_USER_PASSWORD


def _csv_bytes(headword: str = "harbor") -> bytes:
    output = io.StringIO()
    writer = csv.writer(output, lineterminator="\n")
    writer.writerow(
        [
            "headword",
            "phonetic",
            "part_of_speech",
            "definition_en",
            "definition_zh",
            "example",
            "example_translation",
        ]
    )
    writer.writerow(
        [
            headword,
            "hahr-ber",
            "n.",
            "a place where ships stop",
            "port",
            "The ship entered the harbor.",
            "The ship reached the port.",
        ]
    )
    return output.getvalue().encode("utf-8")


def _json_bytes(headword: str = "harbor") -> bytes:
    return json.dumps(
        [
            {
                "headword": headword,
                "phonetic": "ˈhɑːrbər",
                "part_of_speech": "n.",
                "definition_en": [
                    "a place where ships stop",
                    "a sheltered area for boats",
                ],
                "definition_zh": ["港口", "避风港"],
                "example": ["The ship entered the harbor.", "The boats waited in the harbor."],
                "example_translation": ["船驶入港口。", "船只停在港内。"],
            }
        ],
        ensure_ascii=False,
    ).encode("utf-8")


async def _create_actor(app, *, role: str = "member") -> tuple[User, object]:
    factory = app.state.session_factory.__class__(
        bind=app.state.engine,
        class_=app.state.session_factory.class_,
        expire_on_commit=False,
        autoflush=False,
    )
    username = f"wordbook_{uuid4().hex[:12]}"
    async with factory() as session:
        user = User(
            username=username,
            username_normalized=username.lower(),
            display_name=f"Wordbook {role.title()}",
            role=role,
            status="active",
            password_hash=hash_password(TEST_USER_PASSWORD),
            must_change_password=False,
            profile=UserProfile(department="Learning", learning_group="Core"),
        )
        session.add(user)
        await session.commit()
        user_id = user.id
    async with factory() as session:
        actor = await session.get(User, user_id)
        assert actor is not None
    return actor, factory


async def _cleanup_actor(factory, actor_id: UUID) -> None:
    async with factory() as session:
        await session.execute(delete(AuditLog).where(AuditLog.actor_id == actor_id))
        await session.execute(delete(User).where(User.id == actor_id))
        await session.commit()


async def _create_preview(
    app,
    factory,
    actor: User,
    *,
    headword: str = "harbor",
    raw: bytes | None = None,
    filename: str = "words.csv",
):
    upload = UploadFile(
        filename=filename,
        file=io.BytesIO(raw if raw is not None else _csv_bytes(headword)),
    )
    try:
        async with factory() as session:
            return await create_import_preview(
                session,
                actor,
                settings=app.state.settings,
                storage=app.state.wordbook_storage,
                upload=upload,
                visibility="private",
                name="Concurrent import",
            )
    finally:
        await upload.close()


async def _create_import_job(app, factory, actor: User):
    preview = await _create_preview(app, factory, actor)
    payload = ImportConfirmRequest(
        preview_id=preview.preview_id,
        preview_token=preview.preview_token,
        preview_hash=preview.preview_hash,
        name=preview.requested_name,
        visibility="private",
    )
    async with factory() as session:
        job = await confirm_wordbook_import(
            session,
            actor,
            settings=app.state.settings,
            payload=payload,
            idempotency_key=f"import-{uuid4().hex}",
        )
        return preview, job


def _job_context(app, factory) -> dict:
    return {
        "session_factory": factory,
        "settings": app.state.settings,
        "wordbook_storage": app.state.wordbook_storage,
    }


async def test_concurrent_confirmation_with_distinct_keys_creates_one_job(app) -> None:
    actor, factory = await _create_actor(app)
    try:
        preview = await _create_preview(app, factory, actor)
        payload = ImportConfirmRequest(
            preview_id=preview.preview_id,
            preview_token=preview.preview_token,
            preview_hash=preview.preview_hash,
            name=preview.requested_name,
            visibility="private",
        )
        barrier = asyncio.Barrier(2)

        async def confirm(key: str):
            async with factory() as session:
                await barrier.wait()
                try:
                    return await confirm_wordbook_import(
                        session,
                        actor,
                        settings=app.state.settings,
                        payload=payload,
                        idempotency_key=key,
                    )
                except AppError as exc:
                    return exc

        results = await asyncio.wait_for(
            asyncio.gather(confirm("confirm-a"), confirm("confirm-b")),
            timeout=15,
        )
        jobs = [result for result in results if isinstance(result, WordbookJob)]
        errors = [result for result in results if isinstance(result, AppError)]

        assert len(jobs) == 1
        assert len(errors) == 1
        assert errors[0].status_code == 409
        assert errors[0].code == "WORDBOOK_PREVIEW_ALREADY_USED"

        async with factory() as session:
            job_count = await session.scalar(
                select(func.count(WordbookJob.id)).where(WordbookJob.owner_id == actor.id)
            )
            book_count = await session.scalar(
                select(func.count(Wordbook.id)).where(Wordbook.owner_id == actor.id)
            )
        assert job_count == 1
        assert book_count == 1
    finally:
        await _cleanup_actor(factory, actor.id)


async def test_concurrent_delete_with_distinct_keys_creates_one_active_job(app) -> None:
    actor, factory = await _create_actor(app)
    try:
        async with factory() as session:
            book = Wordbook(
                visibility="private",
                status="ready",
                name="Concurrent delete",
                owner_id=actor.id,
                created_by=actor.id,
                book_metadata={},
            )
            session.add(book)
            await session.commit()
            book_id = book.id

        barrier = asyncio.Barrier(2)

        async def request_delete(key: str):
            async with factory() as session:
                await barrier.wait()
                return await start_delete_wordbook(
                    session,
                    actor,
                    settings=app.state.settings,
                    wordbook_id=book_id,
                    payload=DeleteWordbookRequest(),
                    idempotency_key=key,
                )

        first, second = await asyncio.wait_for(
            asyncio.gather(request_delete("delete-a"), request_delete("delete-b")),
            timeout=15,
        )
        assert first.id == second.id

        async with factory() as session:
            active_count = await session.scalar(
                select(func.count(WordbookJob.id)).where(
                    WordbookJob.wordbook_id == book_id,
                    WordbookJob.kind == "delete",
                    WordbookJob.status.in_(("queued", "running", "succeeded")),
                )
            )
        assert active_count == 1
    finally:
        await _cleanup_actor(factory, actor.id)


async def test_concurrent_activation_keeps_exactly_one_active_wordbook(app) -> None:
    actor, factory = await _create_actor(app)
    try:
        async with factory() as session:
            books = [
                Wordbook(
                    visibility="private",
                    status="ready",
                    name=f"Activation {index}",
                    owner_id=actor.id,
                    created_by=actor.id,
                    book_metadata={},
                )
                for index in range(2)
            ]
            session.add_all(books)
            await session.commit()
            book_ids = [book.id for book in books]

        barrier = asyncio.Barrier(2)

        async def activate(wordbook_id: UUID):
            async with factory() as session:
                await barrier.wait()
                return await activate_wordbook(session, actor, wordbook_id)

        responses = await asyncio.wait_for(
            asyncio.gather(*(activate(book_id) for book_id in book_ids)),
            timeout=15,
        )
        assert {response.wordbook_id for response in responses} == set(book_ids)

        async with factory() as session:
            activations = list(
                (
                    await session.scalars(
                        select(WordbookActivation).where(WordbookActivation.user_id == actor.id)
                    )
                ).all()
            )
        assert len(activations) == 1
        assert activations[0].wordbook_id in book_ids
    finally:
        await _cleanup_actor(factory, actor.id)


async def test_import_worker_replay_is_idempotent(app) -> None:
    actor, factory = await _create_actor(app)
    try:
        _, job = await _create_import_job(app, factory, actor)
        context = _job_context(app, factory)

        first = await process_wordbook_job(context, str(job.id))
        second = await process_wordbook_job(context, str(job.id))

        assert first["entry_count"] == 1
        assert second["entry_count"] == 1
        async with factory() as session:
            entry_count = await session.scalar(
                select(func.count(WordbookEntry.id)).where(
                    WordbookEntry.wordbook_id == job.wordbook_id
                )
            )
            persisted = await session.get(WordbookJob, job.id)
        assert entry_count == 1
        assert persisted is not None
        assert persisted.status == "succeeded"
        assert persisted.attempts == 1
    finally:
        await _cleanup_actor(factory, actor.id)


async def test_import_worker_persists_json_entry_definition_example_fk_chain(app) -> None:
    actor, factory = await _create_actor(app)
    try:
        preview = await _create_preview(
            app,
            factory,
            actor,
            raw=_json_bytes(),
            filename="fk-order.json",
        )
        payload = ImportConfirmRequest(
            preview_id=preview.preview_id,
            preview_token=preview.preview_token,
            preview_hash=preview.preview_hash,
            name=preview.requested_name,
            visibility="private",
        )
        async with factory() as session:
            job = await confirm_wordbook_import(
                session,
                actor,
                settings=app.state.settings,
                payload=payload,
                idempotency_key=f"import-fk-{uuid4().hex}",
            )

        result = await process_wordbook_job(_job_context(app, factory), str(job.id))

        assert result["entry_count"] == 1
        assert result["definition_count"] == 2
        assert result["example_count"] == 4
        assert result["format"] == "json"
        async with factory() as session:
            entries = list(
                (
                    await session.scalars(
                        select(WordbookEntry).where(WordbookEntry.wordbook_id == job.wordbook_id)
                    )
                ).all()
            )
            assert len(entries) == 1
            definitions = list(
                (
                    await session.scalars(
                        select(WordbookDefinition)
                        .where(WordbookDefinition.entry_id == entries[0].id)
                        .order_by(WordbookDefinition.sequence)
                    )
                ).all()
            )
            examples = list(
                (
                    await session.scalars(
                        select(WordbookExample)
                        .where(
                            WordbookExample.definition_id.in_(
                                [definition.id for definition in definitions]
                            )
                        )
                        .order_by(WordbookExample.sequence)
                    )
                ).all()
            )
        assert [definition.definition_zh for definition in definitions] == ["港口", "避风港"]
        assert {example.definition_id for example in examples} == {
            definition.id for definition in definitions
        }
        assert len(examples) == 4
        for definition in definitions:
            definition_examples = [
                example for example in examples if example.definition_id == definition.id
            ]
            assert {example.example_zh for example in definition_examples} == {
                "船驶入港口。",
                "船只停在港内。",
            }
    finally:
        await _cleanup_actor(factory, actor.id)


async def test_import_worker_rolls_back_all_entries_and_exposes_failure(app, monkeypatch) -> None:
    actor, factory = await _create_actor(app)
    try:
        preview, job = await _create_import_job(app, factory, actor)
        async with factory() as session:
            persisted_job = await session.get(WordbookJob, job.id)
            assert persisted_job is not None
            persisted_job.max_attempts = 1
            await session.commit()

        from app.services import wordbook_jobs as jobs_module

        original_add_audit_event = jobs_module.add_audit_event

        def fail_after_rows_are_written(*args, **kwargs):
            if kwargs.get("action") == "wordbook.import.completed":
                raise RuntimeError("forced post-write failure")
            return original_add_audit_event(*args, **kwargs)

        monkeypatch.setattr(jobs_module, "add_audit_event", fail_after_rows_are_written)
        result = await process_wordbook_job(_job_context(app, factory), str(job.id))

        assert result == {"status": "failed", "error_code": "WORDBOOK_JOB_FAILED"}
        async with factory() as session:
            entry_count = await session.scalar(
                select(func.count(WordbookEntry.id)).where(
                    WordbookEntry.wordbook_id == job.wordbook_id
                )
            )
            persisted_job = await session.get(WordbookJob, job.id)
            book = await session.get(Wordbook, job.wordbook_id)
            persisted_preview = await session.get(WordbookImportPreview, preview.preview_id)
        assert entry_count == 0
        assert persisted_job is not None
        assert persisted_job.status == "failed"
        assert book is not None and book.status == "failed"
        assert persisted_preview is not None and persisted_preview.status == "failed"
    finally:
        await _cleanup_actor(factory, actor.id)


async def test_preview_ownership_hash_expiry_and_storage_tamper_are_rejected(app) -> None:
    actor, factory = await _create_actor(app)
    other_actor, other_factory = await _create_actor(app)
    try:
        preview = await _create_preview(app, factory, actor)
        remap = ImportRemapRequest(
            preview_token=preview.preview_token,
            mapping=preview.mapping,
            ignored_columns=preview.ignored_columns,
        )
        async with other_factory() as session:
            with pytest.raises(AppError) as cross_owner:
                await remap_import_preview(
                    session,
                    other_actor,
                    settings=app.state.settings,
                    storage=app.state.wordbook_storage,
                    preview_id=preview.preview_id,
                    payload=remap,
                )
        assert cross_owner.value.status_code == 404
        assert cross_owner.value.code == "WORDBOOK_PREVIEW_NOT_FOUND"

        mismatched = ImportConfirmRequest(
            preview_id=preview.preview_id,
            preview_token=preview.preview_token,
            preview_hash="0" * 64,
        )
        async with factory() as session:
            with pytest.raises(AppError) as hash_error:
                await confirm_wordbook_import(
                    session,
                    actor,
                    settings=app.state.settings,
                    payload=mismatched,
                    idempotency_key=f"bad-hash-{uuid4().hex}",
                )
        assert hash_error.value.status_code == 409
        assert hash_error.value.code == "WORDBOOK_PREVIEW_MISMATCH"

        async with factory() as session:
            record = await session.get(WordbookImportPreview, preview.preview_id)
            assert record is not None
            storage_key = record.storage_key
        artifact = app.state.wordbook_storage.root / storage_key
        artifact.write_bytes(b"tampered artifact")
        async with factory() as session:
            with pytest.raises(AppError) as content_changed:
                await remap_import_preview(
                    session,
                    actor,
                    settings=app.state.settings,
                    storage=app.state.wordbook_storage,
                    preview_id=preview.preview_id,
                    payload=remap,
                )
        assert content_changed.value.status_code == 409
        assert content_changed.value.code == "WORDBOOK_PREVIEW_CONTENT_CHANGED"

        expiring = await _create_preview(app, factory, actor, headword="expires")
        async with factory() as session:
            record = await session.get(WordbookImportPreview, expiring.preview_id)
            assert record is not None
            record.expires_at = utcnow() - timedelta(seconds=1)
            await session.commit()
        expired_payload = ImportConfirmRequest(
            preview_id=expiring.preview_id,
            preview_token=expiring.preview_token,
            preview_hash=expiring.preview_hash,
        )
        async with factory() as session:
            with pytest.raises(AppError) as expired:
                await confirm_wordbook_import(
                    session,
                    actor,
                    settings=app.state.settings,
                    payload=expired_payload,
                    idempotency_key=f"expired-{uuid4().hex}",
                )
        assert expired.value.status_code == 410
        assert expired.value.code == "WORDBOOK_PREVIEW_EXPIRED"
        async with factory() as session:
            expired_record = await session.get(WordbookImportPreview, expiring.preview_id)
        assert expired_record is not None
        assert expired_record.status == "expired"
    finally:
        await _cleanup_actor(other_factory, other_actor.id)
        await _cleanup_actor(factory, actor.id)
