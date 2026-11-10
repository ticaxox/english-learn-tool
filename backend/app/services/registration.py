"""Self-service registration.

Administrators still create accounts in bulk, but a learner may also register
themselves with a username and a password. The password is hashed with argon2,
the username is unique case-insensitively, and the new account starts as a
member with a finished profile so the first login goes straight to Today.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.core.security import hash_password, normalize_username, validate_password
from app.models.identity import User, UserProfile
from app.services.audit import add_audit_event


async def register_user(session: AsyncSession, *, username: str, password: str) -> User:
    normalized = normalize_username(username)
    validate_password(password)
    existing = await session.scalar(
        select(User.id).where(User.username_normalized == normalized).limit(1)
    )
    if existing is not None:
        raise AppError(
            status_code=409,
            code="USERNAME_TAKEN",
            message="The username is already in use.",
        )
    user = User(
        username=username.strip(),
        username_normalized=normalized,
        display_name=username.strip(),
        role="member",
        status="active",
        password_hash=hash_password(password),
        must_change_password=False,
        profile=UserProfile(),
    )
    session.add(user)
    try:
        await session.flush()
        add_audit_event(
            session,
            actor=user,
            action="auth.register",
            target_type="user",
            target_id=user.id,
            target_username=normalized,
            outcome="success",
        )
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise AppError(
            status_code=409,
            code="USERNAME_TAKEN",
            message="The username is already in use.",
        ) from exc
    await session.refresh(user)
    return user
