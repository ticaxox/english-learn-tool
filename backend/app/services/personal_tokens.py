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


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


async def create_personal_token(
    session: AsyncSession, user: User, name: str
) -> tuple[PersonalAccessToken, str]:
    plaintext = f"{TOKEN_PREFIX}{secrets.token_urlsafe(TOKEN_BYTES)}"
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
    rows = await session.scalars(
        select(PersonalAccessToken)
        .where(PersonalAccessToken.user_id == user.id)
        .order_by(PersonalAccessToken.created_at.desc())
    )
    return list(rows.all())


async def revoke_personal_token(
    session: AsyncSession, user: User, token_id: UUID
) -> PersonalAccessToken:
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
    if row.revoked_at is None:
        row.revoked_at = utcnow()
        await session.commit()
    return row


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
