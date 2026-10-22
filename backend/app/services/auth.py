import hashlib
import hmac
import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from fastapi import Request
from redis.asyncio import Redis
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import Settings
from app.core.errors import AppError
from app.core.security import (
    create_access_token,
    generate_opaque_token,
    hash_csrf_token,
    hash_password,
    hash_refresh_token,
    password_needs_rehash,
    verify_password,
)
from app.models.identity import RefreshToken, User
from app.services.audit import add_audit_event, commit_failure_audit

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class AuthContext:
    user: User
    family_id: UUID
    jti: str
    token_expires_at: datetime


@dataclass(frozen=True)
class IssuedSession:
    user: User
    access_token: str
    expires_in: int
    csrf_token: str
    refresh_token: str


def utcnow() -> datetime:
    return datetime.now(UTC)


def _client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def _user_agent(request: Request) -> str | None:
    value = request.headers.get("user-agent")
    return value[:255] if value else None


def _login_bucket(ip_address: str, normalized_username: str) -> str:
    return hashlib.sha256(f"{ip_address}|{normalized_username}".encode()).hexdigest()


def _attempt_key(ip_address: str, normalized_username: str) -> str:
    return f"auth:login:attempts:{_login_bucket(ip_address, normalized_username)}"


def _lock_key(ip_address: str, normalized_username: str) -> str:
    return f"auth:login:locked:{_login_bucket(ip_address, normalized_username)}"


async def _locked_seconds(redis: Redis, ip_address: str, normalized_username: str) -> int:
    ttl = await redis.ttl(_lock_key(ip_address, normalized_username))
    return max(int(ttl), 0)


async def _record_failure(
    redis: Redis,
    settings: Settings,
    ip_address: str,
    normalized_username: str,
) -> int:
    attempt_key = _attempt_key(ip_address, normalized_username)
    lock_key = _lock_key(ip_address, normalized_username)
    attempts = int(await redis.incr(attempt_key))
    await redis.expire(attempt_key, settings.login_failure_window_seconds)
    if attempts >= settings.login_max_failures:
        await redis.set(lock_key, "1", ex=settings.login_cooldown_seconds)
        await redis.expire(lock_key, settings.login_cooldown_seconds)
    return attempts


async def _clear_failures(redis: Redis, ip_address: str, normalized_username: str) -> None:
    await redis.delete(
        _attempt_key(ip_address, normalized_username),
        _lock_key(ip_address, normalized_username),
    )


async def _audit_login_failure(
    session: AsyncSession,
    *,
    user: User | None,
    normalized_username: str,
    reason_code: str,
    context: dict | None = None,
) -> None:
    await commit_failure_audit(
        session,
        actor=user,
        action="auth.login",
        target_type="session",
        target_id=user.id if user is not None else None,
        target_username=normalized_username,
        reason_code=reason_code,
        context=context,
    )


def _create_refresh_record(
    *,
    user_id: UUID,
    family_id: UUID,
    settings: Settings,
    request: Request,
) -> tuple[RefreshToken, str, str]:
    refresh_token = generate_opaque_token()
    csrf_token = generate_opaque_token(32)
    record = RefreshToken(
        user_id=user_id,
        family_id=family_id,
        token_hash=hash_refresh_token(refresh_token, settings),
        csrf_hash=hash_csrf_token(csrf_token, settings),
        user_agent=_user_agent(request),
        ip_address=_client_ip(request),
        expires_at=utcnow() + timedelta(days=settings.refresh_token_days),
    )
    return record, refresh_token, csrf_token


def _issue_access(user: User, session_record: RefreshToken, settings: Settings) -> tuple[str, int]:
    issued = create_access_token(
        user_id=user.id,
        role=user.role,
        family_id=session_record.family_id,
        settings=settings,
    )
    return issued.token, max(int((issued.expires_at - utcnow()).total_seconds()), 1)


async def login(
    session: AsyncSession,
    redis: Redis,
    settings: Settings,
    *,
    request: Request,
    username: str,
    password: str,
) -> IssuedSession:
    normalized = username.strip().lower()
    ip_address = _client_ip(request)

    locked_for = await _locked_seconds(redis, ip_address, normalized)
    if locked_for > 0:
        await _record_failure(redis, settings, ip_address, normalized)
        await _audit_login_failure(
            session,
            user=None,
            normalized_username=normalized,
            reason_code="AUTH_RATE_LIMITED",
            context={"retry_after_seconds": locked_for},
        )
        raise AppError(
            status_code=429,
            code="AUTH_RATE_LIMITED",
            message="Too many login attempts. Try again later.",
            details={"retry_after_seconds": locked_for},
            headers={"Retry-After": str(locked_for)},
        )

    user = await session.scalar(
        select(User)
        .options(selectinload(User.profile))
        .where(User.username_normalized == normalized)
    )
    password_ok = verify_password(password, user.password_hash if user else None)
    if user is None or not password_ok or user.status != "active":
        await _record_failure(redis, settings, ip_address, normalized)
        logger.warning(
            "security.login_failed",
            extra={
                "event": "auth.login",
                "user_id": str(user.id) if user else None,
                "outcome": "failure",
                "reason_code": "AUTH_INVALID_CREDENTIALS",
            },
        )
        await _audit_login_failure(
            session,
            user=user,
            normalized_username=normalized,
            reason_code="AUTH_INVALID_CREDENTIALS",
        )
        raise AppError(
            status_code=401,
            code="AUTH_INVALID_CREDENTIALS",
            message="Username or password is incorrect.",
        )

    await _clear_failures(redis, ip_address, normalized)
    if password_needs_rehash(user.password_hash):
        user.password_hash = hash_password(password)
    user.last_login_at = utcnow()

    family_id = uuid4()
    record, refresh_token, csrf_token = _create_refresh_record(
        user_id=user.id,
        family_id=family_id,
        settings=settings,
        request=request,
    )
    session.add(record)
    add_audit_event(
        session,
        actor=user,
        action="auth.login",
        target_type="session",
        target_id=record.id,
        target_username=user.username_normalized,
        outcome="success",
        context={"family_id": str(family_id)},
    )
    await session.commit()
    access_token, expires_in = _issue_access(user, record, settings)
    return IssuedSession(
        user=user,
        access_token=access_token,
        expires_in=expires_in,
        csrf_token=csrf_token,
        refresh_token=refresh_token,
    )


def validate_origin(request: Request, settings: Settings) -> None:
    origin = request.headers.get("origin")
    if not origin or origin.rstrip("/") not in settings.cors_origin_list:
        raise AppError(
            status_code=403,
            code="AUTH_ORIGIN_INVALID",
            message="The request origin is not allowed.",
        )


def validate_csrf(
    *,
    header_token: str | None,
    cookie_token: str | None,
    stored_hash: str,
    settings: Settings,
) -> None:
    if not header_token or not cookie_token or not hmac.compare_digest(header_token, cookie_token):
        raise AppError(
            status_code=403,
            code="AUTH_CSRF_FAILED",
            message="CSRF validation failed.",
        )
    if not hmac.compare_digest(hash_csrf_token(header_token, settings), stored_hash):
        raise AppError(
            status_code=403,
            code="AUTH_CSRF_FAILED",
            message="CSRF validation failed.",
        )


async def refresh_session(
    session: AsyncSession,
    settings: Settings,
    *,
    request: Request,
    refresh_token: str | None,
    csrf_header: str | None,
    csrf_cookie: str | None,
) -> IssuedSession:
    try:
        validate_origin(request, settings)
    except AppError as exc:
        await commit_failure_audit(
            session,
            action="auth.refresh",
            target_type="session",
            reason_code=exc.code,
        )
        raise

    if not refresh_token:
        await commit_failure_audit(
            session,
            action="auth.refresh",
            target_type="session",
            reason_code="AUTH_REFRESH_MISSING",
        )
        raise AppError(
            status_code=401,
            code="AUTH_INVALID_REFRESH",
            message="The refresh session is invalid or expired.",
        )

    token_hash = hash_refresh_token(refresh_token, settings)
    record = await session.scalar(
        select(RefreshToken).where(RefreshToken.token_hash == token_hash).with_for_update()
    )
    if record is None:
        await commit_failure_audit(
            session,
            action="auth.refresh",
            target_type="session",
            reason_code="AUTH_INVALID_REFRESH",
        )
        raise AppError(
            status_code=401,
            code="AUTH_INVALID_REFRESH",
            message="The refresh session is invalid or expired.",
        )

    user = await session.get(User, record.user_id)
    if user is None:
        await session.rollback()
        raise AppError(
            status_code=401,
            code="AUTH_INVALID_REFRESH",
            message="The refresh session is invalid or expired.",
        )

    if record.revoked_at is not None:
        await session.execute(
            update(RefreshToken)
            .where(
                RefreshToken.family_id == record.family_id,
                RefreshToken.revoked_at.is_(None),
            )
            .values(revoked_at=utcnow(), revoked_reason="reuse_detected")
        )
        add_audit_event(
            session,
            actor=user,
            action="auth.refresh.reuse",
            target_type="session",
            target_id=record.id,
            target_username=user.username_normalized,
            outcome="failure",
            reason_code="AUTH_TOKEN_REUSED",
            context={"family_id": str(record.family_id)},
        )
        await session.commit()
        logger.warning(
            "security.refresh_reuse",
            extra={
                "event": "auth.refresh.reuse",
                "user_id": str(user.id),
                "target_id": str(record.id),
                "outcome": "failure",
                "reason_code": "AUTH_TOKEN_REUSED",
            },
        )
        raise AppError(
            status_code=401,
            code="AUTH_TOKEN_REUSED",
            message="The refresh token was already used. The session has been revoked.",
        )

    if record.expires_at <= utcnow() or user.status != "active":
        record.revoked_at = utcnow()
        record.revoked_reason = "expired" if record.expires_at <= utcnow() else "account_disabled"
        add_audit_event(
            session,
            actor=user,
            action="auth.refresh",
            target_type="session",
            target_id=record.id,
            target_username=user.username_normalized,
            outcome="failure",
            reason_code="AUTH_INVALID_REFRESH",
            context={"family_id": str(record.family_id)},
        )
        await session.commit()
        raise AppError(
            status_code=401,
            code="AUTH_INVALID_REFRESH",
            message="The refresh session is invalid or expired.",
        )

    try:
        validate_csrf(
            header_token=csrf_header,
            cookie_token=csrf_cookie,
            stored_hash=record.csrf_hash,
            settings=settings,
        )
    except AppError as exc:
        await commit_failure_audit(
            session,
            actor=user,
            action="auth.refresh",
            target_type="session",
            target_id=record.id,
            target_username=user.username_normalized,
            reason_code=exc.code,
            context={"family_id": str(record.family_id)},
        )
        raise

    new_record, new_refresh, new_csrf = _create_refresh_record(
        user_id=user.id,
        family_id=record.family_id,
        settings=settings,
        request=request,
    )
    session.add(new_record)
    await session.flush()
    record.revoked_at = utcnow()
    record.revoked_reason = "rotated"
    record.replaced_by_id = new_record.id
    await session.commit()

    access_token, expires_in = _issue_access(user, new_record, settings)
    return IssuedSession(
        user=user,
        access_token=access_token,
        expires_in=expires_in,
        csrf_token=new_csrf,
        refresh_token=new_refresh,
    )


async def revoke_family(
    session: AsyncSession,
    *,
    user_id: UUID,
    family_id: UUID,
    reason: str,
) -> None:
    await session.execute(
        update(RefreshToken)
        .where(
            RefreshToken.user_id == user_id,
            RefreshToken.family_id == family_id,
            RefreshToken.revoked_at.is_(None),
        )
        .values(revoked_at=utcnow(), revoked_reason=reason)
    )


async def revoke_all_user_tokens(
    session: AsyncSession,
    *,
    user_id: UUID,
    reason: str,
) -> None:
    await session.execute(
        update(RefreshToken)
        .where(RefreshToken.user_id == user_id, RefreshToken.revoked_at.is_(None))
        .values(revoked_at=utcnow(), revoked_reason=reason)
    )


async def logout(
    session: AsyncSession,
    settings: Settings,
    *,
    request: Request,
    context: AuthContext,
    csrf_header: str | None,
    csrf_cookie: str | None,
) -> None:
    try:
        validate_origin(request, settings)
    except AppError as exc:
        await commit_failure_audit(
            session,
            actor=context.user,
            action="auth.logout",
            target_type="session",
            target_id=context.family_id,
            target_username=context.user.username_normalized,
            reason_code=exc.code,
        )
        raise

    active_record = await session.scalar(
        select(RefreshToken)
        .where(
            RefreshToken.user_id == context.user.id,
            RefreshToken.family_id == context.family_id,
            RefreshToken.revoked_at.is_(None),
            RefreshToken.expires_at > utcnow(),
        )
        .limit(1)
    )
    if active_record is None:
        raise AppError(
            status_code=401,
            code="AUTH_INVALID_TOKEN",
            message="The session is no longer active.",
        )

    try:
        validate_csrf(
            header_token=csrf_header,
            cookie_token=csrf_cookie,
            stored_hash=active_record.csrf_hash,
            settings=settings,
        )
    except AppError as exc:
        await commit_failure_audit(
            session,
            actor=context.user,
            action="auth.logout",
            target_type="session",
            target_id=context.family_id,
            target_username=context.user.username_normalized,
            reason_code=exc.code,
        )
        raise

    await revoke_family(
        session,
        user_id=context.user.id,
        family_id=context.family_id,
        reason="logout",
    )
    add_audit_event(
        session,
        actor=context.user,
        action="auth.logout",
        target_type="session",
        target_id=context.family_id,
        target_username=context.user.username_normalized,
        outcome="success",
        context={"family_id": str(context.family_id)},
    )
    await session.commit()


async def change_password(
    session: AsyncSession,
    *,
    context: AuthContext,
    old_password: str,
    new_password: str,
) -> None:
    user = context.user
    if not verify_password(old_password, user.password_hash):
        await commit_failure_audit(
            session,
            actor=user,
            action="auth.password.change",
            target_type="user",
            target_id=user.id,
            target_username=user.username_normalized,
            reason_code="AUTH_INVALID_CREDENTIALS",
        )
        raise AppError(
            status_code=401,
            code="AUTH_INVALID_CREDENTIALS",
            message="The current password is incorrect.",
        )
    if verify_password(new_password, user.password_hash):
        await commit_failure_audit(
            session,
            actor=user,
            action="auth.password.change",
            target_type="user",
            target_id=user.id,
            target_username=user.username_normalized,
            reason_code="PASSWORD_UNCHANGED",
        )
        raise AppError(
            status_code=422,
            code="PASSWORD_UNCHANGED",
            message="The new password must differ from the current password.",
        )

    user.password_hash = hash_password(new_password)
    user.must_change_password = False
    user.password_changed_at = utcnow()
    await revoke_all_user_tokens(session, user_id=user.id, reason="password_changed")
    add_audit_event(
        session,
        actor=user,
        action="auth.password.change",
        target_type="user",
        target_id=user.id,
        target_username=user.username_normalized,
        outcome="success",
    )
    await session.commit()


async def get_authenticated_context(
    session: AsyncSession,
    *,
    claims,
) -> AuthContext:
    user = await session.scalar(
        select(User).options(selectinload(User.profile)).where(User.id == claims.user_id)
    )
    if user is None or user.status != "active":
        raise AppError(
            status_code=401,
            code="AUTH_INVALID_TOKEN",
            message="The access token is invalid or expired.",
        )
    active_session = await session.scalar(
        select(RefreshToken.id)
        .where(
            RefreshToken.user_id == user.id,
            RefreshToken.family_id == claims.family_id,
            RefreshToken.revoked_at.is_(None),
            RefreshToken.expires_at > utcnow(),
        )
        .limit(1)
    )
    if active_session is None:
        raise AppError(
            status_code=401,
            code="AUTH_INVALID_TOKEN",
            message="The access token is invalid or expired.",
        )
    return AuthContext(
        user=user,
        family_id=claims.family_id,
        jti=claims.jti,
        token_expires_at=claims.expires_at,
    )
