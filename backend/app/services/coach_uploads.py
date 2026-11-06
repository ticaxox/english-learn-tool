"""Attachments for coach messages.

Files live on the shared volume under ``COACH_UPLOAD_DIR``; the database row is
the authority for ownership, and the file name on disk is always the attachment
UUID, never the client's filename. Type is decided from the bytes and the
extension, not from the upload's declared content type.
"""

from __future__ import annotations

import io
import re
import zipfile
from html import unescape
from pathlib import Path
from uuid import uuid4

from fastapi import UploadFile

from app.core.config import Settings
from app.core.errors import AppError
from app.models.coach import CoachAttachment, CoachConversation
from app.models.identity import User

MAX_FILENAME = 200
DOCX_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
TEXT_LIMIT = 2 * 1024 * 1024
TEXT_CHARS = 20_000

# signature -> (content type, extension)
_SIGNATURES: tuple[tuple[bytes, str, str], ...] = (
    (b"\x89PNG\r\n\x1a\n", "image/png", ".png"),
    (b"\xff\xd8\xff", "image/jpeg", ".jpg"),
)


def _detect(payload: bytes, filename: str) -> tuple[str, str] | None:
    for signature, content_type, extension in _SIGNATURES:
        if payload.startswith(signature):
            return content_type, extension
    if payload[:4] == b"RIFF" and payload[8:12] == b"WEBP":
        return "image/webp", ".webp"
    lower = filename.lower()
    if lower.endswith(".docx") and payload[:4] == b"PK\x03\x04":
        return DOCX_TYPE, ".docx"
    if lower.endswith((".txt", ".md")):
        try:
            payload.decode("utf-8")
        except UnicodeDecodeError:
            return None
        return ("text/markdown" if lower.endswith(".md") else "text/plain"), Path(lower).suffix
    return None


def _clean_filename(value: str | None) -> str:
    name = Path((value or "").strip()).name.strip()
    return name[:MAX_FILENAME] or "attachment"


def is_image(content_type: str) -> bool:
    return content_type.startswith("image/")


async def save_coach_attachment(
    settings: Settings,
    user: User,
    conversation: CoachConversation,
    upload: UploadFile,
) -> CoachAttachment:
    payload = await upload.read(settings.coach_upload_max_bytes + 1)
    if not payload:
        raise AppError(
            status_code=422,
            code="COACH_ATTACHMENT_EMPTY",
            message="The attachment is empty.",
        )
    if len(payload) > settings.coach_upload_max_bytes:
        raise AppError(
            status_code=413,
            code="COACH_ATTACHMENT_TOO_LARGE",
            message="The attachment exceeds the upload limit.",
        )
    detected = _detect(payload, upload.filename or "")
    if detected is None:
        raise AppError(
            status_code=415,
            code="COACH_ATTACHMENT_TYPE_UNSUPPORTED",
            message="Only PNG, JPEG, WebP, DOCX, TXT and Markdown files are supported.",
        )
    content_type, extension = detected

    attachment_id = uuid4()
    relative = f"{user.id}/{attachment_id}{extension}"
    target = Path(settings.coach_upload_dir) / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(f"{target.suffix}.part")
    temporary.write_bytes(payload)
    temporary.replace(target)

    return CoachAttachment(
        id=attachment_id,
        user_id=user.id,
        conversation_id=conversation.id,
        filename=_clean_filename(upload.filename),
        content_type=content_type,
        size_bytes=len(payload),
        storage_path=relative,
    )


def attachment_path(settings: Settings, attachment: CoachAttachment) -> Path:
    return Path(settings.coach_upload_dir) / attachment.storage_path


def read_attachment(settings: Settings, attachment: CoachAttachment) -> bytes:
    path = attachment_path(settings, attachment)
    try:
        return path.read_bytes()
    except OSError as exc:
        raise AppError(
            status_code=404,
            code="COACH_ATTACHMENT_MISSING",
            message="The attachment file is no longer available.",
        ) from exc


def attachment_text(settings: Settings, attachment: CoachAttachment) -> str | None:
    """Plain text for a document attachment; images return None."""
    if is_image(attachment.content_type):
        return None
    payload = read_attachment(settings, attachment)
    if attachment.content_type == DOCX_TYPE:
        return _docx_text(payload)
    return payload.decode("utf-8", errors="replace")[:TEXT_CHARS]


def _docx_text(payload: bytes) -> str:
    try:
        with zipfile.ZipFile(io.BytesIO(payload)) as archive:
            # Bounded read: a small archive can still carry a huge XML entry.
            with archive.open("word/document.xml") as document:
                xml = document.read(TEXT_LIMIT).decode("utf-8", errors="replace")
    except (KeyError, OSError, zipfile.BadZipFile):
        return ""
    text = re.sub(r"</w:p>", "\n", xml)
    text = re.sub(r"<w:br\s*/?>", "\n", text)
    text = re.sub(r"<[^>]+>", "", text)
    return re.sub(r"\n{3,}", "\n\n", unescape(text)).strip()[:TEXT_CHARS]


def delete_attachment_files(settings: Settings, attachments: list[CoachAttachment]) -> None:
    for attachment in attachments:
        try:
            attachment_path(settings, attachment).unlink(missing_ok=True)
        except OSError:
            # A missing file must never block deleting the message or conversation.
            continue
