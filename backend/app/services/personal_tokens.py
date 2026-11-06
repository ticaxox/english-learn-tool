"""Personal access tokens for external MCP clients."""

from __future__ import annotations

import hashlib
import secrets
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.models.identity import PersonalAccessToken, User
from app.services.auth import utcnow

TOKEN_PREFIX = "elt_"
TOKEN_BYTES = 32
DEFAULT_TOKEN_NAME = "网页默认令牌"


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _new_secret() -> str:
    return f"{TOKEN_PREFIX}{secrets.token_urlsafe(TOKEN_BYTES)}"


async def ensure_default_token(session: AsyncSession, user: User) -> PersonalAccessToken:
    row = await session.scalar(
        select(PersonalAccessToken).where(
            PersonalAccessToken.user_id == user.id,
            PersonalAccessToken.is_default.is_(True),
        )
    )
    if row is not None:
        return row
    plaintext = _new_secret()
    row = PersonalAccessToken(
        user_id=user.id,
        name=DEFAULT_TOKEN_NAME,
        token_hash=hash_token(plaintext),
        token_prefix=plaintext[:12],
        is_default=True,
    )
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return row


async def create_personal_token(
    session: AsyncSession, user: User, name: str
) -> tuple[PersonalAccessToken, str]:
    await ensure_default_token(session, user)
    plaintext = _new_secret()
    row = PersonalAccessToken(
        user_id=user.id,
        name=name.strip(),
        token_hash=hash_token(plaintext),
        token_prefix=plaintext[:12],
    )
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return row, plaintext


async def list_personal_tokens(session: AsyncSession, user: User) -> list[PersonalAccessToken]:
    await ensure_default_token(session, user)
    rows = await session.scalars(
        select(PersonalAccessToken)
        .where(PersonalAccessToken.user_id == user.id)
        .order_by(PersonalAccessToken.created_at.desc())
    )
    return list(rows.all())


async def delete_personal_token(session: AsyncSession, user: User, token_id: UUID) -> None:
    row = await session.scalar(
        select(PersonalAccessToken).where(
            PersonalAccessToken.id == token_id,
            PersonalAccessToken.user_id == user.id,
        )
    )
    if row is None:
        raise AppError(
            status_code=404,
            code="PERSONAL_TOKEN_NOT_FOUND",
            message="The access token was not found.",
        )
    if row.is_default:
        raise AppError(
            status_code=409,
            code="PERSONAL_TOKEN_DEFAULT",
            message="The default token cannot be deleted; refresh it instead.",
        )
    await session.delete(row)
    await session.commit()


async def refresh_personal_token(
    session: AsyncSession, user: User, token_id: UUID
) -> tuple[PersonalAccessToken, str]:
    row = await session.scalar(
        select(PersonalAccessToken).where(
            PersonalAccessToken.id == token_id,
            PersonalAccessToken.user_id == user.id,
        )
    )
    if row is None:
        raise AppError(
            status_code=404,
            code="PERSONAL_TOKEN_NOT_FOUND",
            message="The access token was not found.",
        )
    plaintext = _new_secret()
    row.token_hash = hash_token(plaintext)
    row.token_prefix = plaintext[:12]
    row.revoked_at = None
    row.last_used_at = None
    await session.commit()
    await session.refresh(row)
    return row, plaintext


async def authenticate_personal_token(session: AsyncSession, token: str) -> User | None:
    if not token.startswith(TOKEN_PREFIX):
        return None
    row = await session.scalar(
        select(PersonalAccessToken).where(
            PersonalAccessToken.token_hash == hash_token(token),
            PersonalAccessToken.revoked_at.is_(None),
        )
    )
    if row is None:
        return None
    user = await session.get(User, row.user_id)
    if user is None or user.status != "active":
        return None
    row.last_used_at = utcnow()
    await session.commit()
    return user
