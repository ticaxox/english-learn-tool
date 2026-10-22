import csv
import hashlib
import hmac
import io
import json
from datetime import timedelta
from typing import Any
from uuid import UUID

from fastapi import UploadFile
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.errors import AppError
from app.core.security import (
    generate_temporary_password,
    hash_password,
    normalize_username,
    password_policy_error,
    validate_password,
)
from app.models.identity import ImportPreview, User, UserProfile
from app.schemas.imports import (
    ImportAcceptedResponse,
    ImportConfirmRequest,
    ImportCreatedUser,
    ImportedUser,
    ImportPreviewResponse,
    ImportPreviewRow,
    ImportStatusResponse,
)
from app.services.audit import add_audit_event, commit_failure_audit
from app.services.auth import utcnow
from app.services.users import ensure_admin_for_write, require_admin

CSV_FIELDS = ("username", "display_name", "initial_password", "department", "learning_group")


async def _read_csv_rows(upload: UploadFile, settings: Settings) -> list[dict[str, str]]:
    raw = await upload.read(settings.import_max_bytes + 1)
    if len(raw) > settings.import_max_bytes:
        raise AppError(
            status_code=413,
            code="IMPORT_FILE_TOO_LARGE",
            message="The CSV file exceeds the permitted size.",
            details={"max_bytes": settings.import_max_bytes},
        )
    if not raw:
        raise AppError(
            status_code=422,
            code="IMPORT_FILE_EMPTY",
            message="The CSV file is empty.",
        )
    try:
        decoded = raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise AppError(
            status_code=422,
            code="IMPORT_ENCODING_INVALID",
            message="The CSV file must use UTF-8 encoding.",
        ) from exc

    reader = csv.DictReader(io.StringIO(decoded, newline=""))
    if reader.fieldnames is None:
        raise AppError(
            status_code=422,
            code="IMPORT_HEADERS_INVALID",
            message="The CSV file must include a header row.",
        )
    headers = tuple(name.strip() for name in reader.fieldnames)
    missing = [field for field in CSV_FIELDS if field not in headers]
    if missing:
        raise AppError(
            status_code=422,
            code="IMPORT_HEADERS_INVALID",
            message="The CSV header is missing required fields.",
            details={"missing": missing, "required": list(CSV_FIELDS)},
        )

    rows: list[dict[str, str]] = []
    for raw_row in reader:
        normalized_row = {key: (raw_row.get(key) or "").strip() for key in CSV_FIELDS}
        if not any(normalized_row[key] for key in CSV_FIELDS if key != "initial_password"):
            continue
        rows.append(normalized_row)
        if len(rows) > settings.import_max_rows:
            raise AppError(
                status_code=422,
                code="IMPORT_TOO_MANY_ROWS",
                message="The CSV file contains too many rows.",
                details={"max_rows": settings.import_max_rows},
            )
    if not rows:
        raise AppError(
            status_code=422,
            code="IMPORT_FILE_EMPTY",
            message="The CSV file contains no member rows.",
        )
    return rows


def _validate_row(raw: dict[str, str], line_number: int) -> dict[str, Any]:
    errors: list[str] = []
    username = raw["username"]
    display_name = raw["display_name"]
    department = raw["department"] or None
    learning_group = raw["learning_group"] or None
    normalized_username = username.lower()

    try:
        normalized_username = normalize_username(username)
    except ValueError:
        errors.append("username_invalid")

    if not display_name:
        errors.append("display_name_required")
    elif len(display_name) > 100:
        errors.append("display_name_too_long")

    if department is not None and len(department) > 100:
        errors.append("department_too_long")
    if learning_group is not None and len(learning_group) > 100:
        errors.append("learning_group_too_long")

    password_hash: str | None = None
    initial_password = raw["initial_password"]
    if initial_password:
        error = password_policy_error(initial_password)
        if error:
            errors.append("initial_password_invalid")
        else:
            password_hash = hash_password(initial_password)

    return {
        "line_number": line_number,
        "username": username,
        "username_normalized": normalized_username,
        "display_name": display_name,
        "department": department,
        "learning_group": learning_group,
        "password_hash": password_hash,
        "status": "error" if errors else "valid",
        "errors": errors,
    }


def _preview_hash(rows: list[dict[str, Any]]) -> str:
    canonical = json.dumps(rows, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _public_preview_row(row: dict[str, Any]) -> ImportPreviewRow:
    return ImportPreviewRow(
        line_number=row["line_number"],
        username=row["username"],
        display_name=row["display_name"],
        department=row["department"],
        learning_group=row["learning_group"],
        status=row["status"],
        errors=row["errors"],
    )


async def create_import_preview(
    session: AsyncSession,
    actor: User,
    *,
    settings: Settings,
    upload: UploadFile,
) -> ImportPreviewResponse:
    await ensure_admin_for_write(
        session,
        actor,
        action="admin.users.import.preview",
        target_type="import",
    )
    try:
        raw_rows = await _read_csv_rows(upload, settings)
    except AppError as exc:
        await commit_failure_audit(
            session,
            actor=actor,
            action="admin.users.import.preview",
            target_type="import",
            reason_code=exc.code,
        )
        raise

    rows = [_validate_row(raw, index + 2) for index, raw in enumerate(raw_rows)]
    seen: dict[str, int] = {}
    candidate_usernames: set[str] = set()
    for row in rows:
        normalized = row["username_normalized"]
        if row["status"] == "valid":
            candidate_usernames.add(normalized)
        if normalized in seen:
            row["status"] = "conflict"
            row["errors"].append("username_duplicate_in_file")
        else:
            seen[normalized] = row["line_number"]

    if candidate_usernames:
        existing = set(
            (
                await session.scalars(
                    select(User.username_normalized).where(
                        User.username_normalized.in_(candidate_usernames)
                    )
                )
            ).all()
        )
        for row in rows:
            if row["username_normalized"] in existing:
                row["status"] = "conflict"
                row["errors"].append("username_conflict")

    preview_hash = _preview_hash(rows)
    valid_rows = sum(row["status"] == "valid" for row in rows)
    invalid_rows = len(rows) - valid_rows
    summary = {
        "valid_rows": valid_rows,
        "invalid_rows": invalid_rows,
        "created_count": 0,
        "created_users": [],
    }
    preview = ImportPreview(
        created_by=actor.id,
        preview_hash=preview_hash,
        status="previewed",
        rows=rows,
        summary=summary,
        row_count=len(rows),
        expires_at=utcnow() + timedelta(minutes=settings.import_preview_ttl_minutes),
    )
    session.add(preview)
    await session.flush()
    add_audit_event(
        session,
        actor=actor,
        action="admin.users.import.preview",
        target_type="import",
        target_id=preview.id,
        outcome="success",
        context={"row_count": len(rows), "valid_rows": valid_rows, "invalid_rows": invalid_rows},
    )
    await session.commit()
    return ImportPreviewResponse(
        preview_id=preview.id,
        preview_hash=preview_hash,
        expires_at=preview.expires_at,
        total_rows=len(rows),
        valid_rows=valid_rows,
        invalid_rows=invalid_rows,
        rows=[_public_preview_row(row) for row in rows],
    )


async def _find_preview(
    session: AsyncSession,
    *,
    preview_id: UUID,
    actor: User,
    lock: bool = False,
) -> ImportPreview | None:
    statement = select(ImportPreview).where(
        ImportPreview.id == preview_id,
        ImportPreview.created_by == actor.id,
    )
    if lock:
        statement = statement.with_for_update()
    return await session.scalar(statement)


async def confirm_import(
    session: AsyncSession,
    actor: User,
    *,
    payload: ImportConfirmRequest,
) -> ImportAcceptedResponse:
    await ensure_admin_for_write(
        session,
        actor,
        action="admin.users.import",
        target_id=payload.preview_id,
        target_type="import",
    )
    preview = await _find_preview(
        session,
        preview_id=payload.preview_id,
        actor=actor,
        lock=True,
    )
    if preview is None:
        await commit_failure_audit(
            session,
            actor=actor,
            action="admin.users.import",
            target_type="import",
            target_id=payload.preview_id,
            reason_code="IMPORT_PREVIEW_NOT_FOUND",
        )
        raise AppError(
            status_code=404,
            code="IMPORT_PREVIEW_NOT_FOUND",
            message="The import preview was not found.",
        )

    if preview.status == "imported":
        await commit_failure_audit(
            session,
            actor=actor,
            action="admin.users.import",
            target_type="import",
            target_id=preview.id,
            reason_code="IMPORT_ALREADY_COMPLETED",
        )
        raise AppError(
            status_code=409,
            code="IMPORT_ALREADY_COMPLETED",
            message="This import preview has already been completed.",
        )
    if preview.status in {"failed", "expired"} or preview.expires_at <= utcnow():
        preview.status = "expired"
        add_audit_event(
            session,
            actor=actor,
            action="admin.users.import",
            target_type="import",
            target_id=preview.id,
            outcome="failure",
            reason_code="IMPORT_PREVIEW_EXPIRED",
        )
        await session.commit()
        raise AppError(
            status_code=410,
            code="IMPORT_PREVIEW_EXPIRED",
            message="The import preview has expired.",
        )
    if not hmac.compare_digest(preview.preview_hash, payload.preview_hash):
        await commit_failure_audit(
            session,
            actor=actor,
            action="admin.users.import",
            target_type="import",
            target_id=preview.id,
            reason_code="IMPORT_PREVIEW_MISMATCH",
        )
        raise AppError(
            status_code=409,
            code="IMPORT_PREVIEW_MISMATCH",
            message="The import preview does not match the confirmed preview.",
        )
    if any(row["status"] != "valid" for row in preview.rows):
        await commit_failure_audit(
            session,
            actor=actor,
            action="admin.users.import",
            target_type="import",
            target_id=preview.id,
            reason_code="IMPORT_PREVIEW_INVALID",
            context={"invalid_rows": preview.summary.get("invalid_rows", 0)},
        )
        raise AppError(
            status_code=409,
            code="IMPORT_PREVIEW_INVALID",
            message="The preview contains conflicts or invalid rows.",
        )

    usernames = {row["username_normalized"] for row in preview.rows}
    conflicts = set(
        (
            await session.scalars(
                select(User.username_normalized).where(User.username_normalized.in_(usernames))
            )
        ).all()
    )
    if conflicts:
        await commit_failure_audit(
            session,
            actor=actor,
            action="admin.users.import",
            target_type="import",
            target_id=preview.id,
            reason_code="IMPORT_USERNAME_CONFLICT",
            context={"conflict_count": len(conflicts)},
        )
        raise AppError(
            status_code=409,
            code="IMPORT_USERNAME_CONFLICT",
            message="At least one username is already in use.",
        )

    created_users: list[ImportCreatedUser] = []
    for row in preview.rows:
        temporary_password: str | None = None
        password_hash = row.get("password_hash")
        if not password_hash:
            temporary_password = generate_temporary_password()
            validate_password(temporary_password)
            password_hash = hash_password(temporary_password)
        user = User(
            username=row["username"].strip(),
            username_normalized=row["username_normalized"],
            display_name=row["display_name"],
            role="member",
            status="active",
            password_hash=password_hash,
            must_change_password=True,
            profile=UserProfile(
                department=row["department"],
                learning_group=row["learning_group"],
            ),
        )
        session.add(user)
        await session.flush()
        created_users.append(
            ImportCreatedUser(
                id=user.id,
                username=user.username,
                display_name=user.display_name,
                temporary_password=temporary_password,
            )
        )

    preview.status = "imported"
    preview.used_at = utcnow()
    preview.summary = {
        **preview.summary,
        "created_count": len(created_users),
        "created_users": [
            {"id": str(user.id), "username": user.username, "display_name": user.display_name}
            for user in created_users
        ],
    }
    add_audit_event(
        session,
        actor=actor,
        action="admin.users.import",
        target_type="import",
        target_id=preview.id,
        outcome="success",
        context={"created_count": len(created_users), "preview_id": str(preview.id)},
    )
    try:
        await session.commit()
    except IntegrityError as exc:
        await commit_failure_audit(
            session,
            actor=actor,
            action="admin.users.import",
            target_type="import",
            target_id=preview.id,
            reason_code="IMPORT_USERNAME_CONFLICT",
        )
        raise AppError(
            status_code=409,
            code="IMPORT_USERNAME_CONFLICT",
            message="At least one username is already in use.",
        ) from exc
    return ImportAcceptedResponse(
        import_id=preview.id,
        status="imported",
        created_count=len(created_users),
        created_users=created_users,
    )


async def get_import_status(
    session: AsyncSession,
    actor: User,
    preview_id: UUID,
) -> ImportStatusResponse:
    require_admin(actor)
    preview = await _find_preview(session, preview_id=preview_id, actor=actor)
    if preview is None:
        raise AppError(
            status_code=404,
            code="IMPORT_PREVIEW_NOT_FOUND",
            message="The import preview was not found.",
        )
    if preview.status == "previewed" and preview.expires_at <= utcnow():
        preview.status = "expired"
        await session.commit()
    created_users = [ImportedUser(**item) for item in preview.summary.get("created_users", [])]
    return ImportStatusResponse(
        import_id=preview.id,
        status=preview.status,
        created_count=int(preview.summary.get("created_count", 0)),
        created_users=created_users,
        expires_at=preview.expires_at,
        used_at=preview.used_at,
    )
