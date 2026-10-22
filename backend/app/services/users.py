import base64
import json
from datetime import datetime, timedelta
from uuid import UUID

from sqlalchemy import and_, distinct, func, or_, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.errors import AppError
from app.core.security import (
    generate_temporary_password,
    hash_password,
    normalize_username,
    validate_password,
)
from app.models.identity import AuditLog, RefreshToken, User, UserProfile
from app.schemas.users import (
    AdminUserCreate,
    AdminUserPatch,
    PasswordResetResponse,
    UserAggregates,
    UserCreateResponse,
    UserDetail,
    UserListResponse,
    UserSummary,
)
from app.services.audit import add_audit_event, commit_failure_audit
from app.services.auth import utcnow

ADMIN_LOCK_KEY = 62100100220261022


def require_admin(actor: User) -> None:
    if actor.role != "admin" or actor.status != "active":
        raise AppError(
            status_code=403,
            code="FORBIDDEN",
            message="Administrator permission is required.",
        )


async def ensure_admin_for_write(
    session: AsyncSession,
    actor: User,
    *,
    action: str,
    target_id: UUID | None = None,
    target_username: str | None = None,
    target_type: str = "user",
) -> None:
    if actor.role == "admin" and actor.status == "active":
        return
    await commit_failure_audit(
        session,
        actor=actor,
        action=action,
        target_type=target_type,
        target_id=target_id,
        target_username=target_username,
        reason_code="FORBIDDEN",
    )
    raise AppError(
        status_code=403,
        code="FORBIDDEN",
        message="Administrator permission is required.",
    )


def user_summary(user: User) -> UserSummary:
    profile = user.profile
    return UserSummary(
        id=user.id,
        username=user.username,
        display_name=user.display_name,
        role=user.role,
        status=user.status,
        must_change_password=user.must_change_password,
        department=profile.department if profile else None,
        learning_group=profile.learning_group if profile else None,
        last_login_at=user.last_login_at,
        created_at=user.created_at,
        updated_at=user.updated_at,
    )


async def _get_user(session: AsyncSession, user_id: UUID, *, lock: bool = False) -> User | None:
    statement = select(User).options(selectinload(User.profile)).where(User.id == user_id)
    if lock:
        statement = statement.with_for_update()
    return await session.scalar(statement)


async def _active_admin_count(session: AsyncSession, excluding: UUID | None = None) -> int:
    statement = select(func.count(User.id)).where(
        User.role == "admin",
        User.status == "active",
    )
    if excluding is not None:
        statement = statement.where(User.id != excluding)
    return int(await session.scalar(statement) or 0)


async def _acquire_admin_lock(session: AsyncSession) -> None:
    await session.execute(
        text("SELECT pg_advisory_xact_lock(:lock_key)"),
        {"lock_key": ADMIN_LOCK_KEY},
    )


async def create_user(
    session: AsyncSession,
    actor: User,
    *,
    payload: AdminUserCreate,
) -> UserCreateResponse:
    normalized = normalize_username(payload.username)
    await ensure_admin_for_write(
        session,
        actor,
        action="admin.user.create",
        target_username=normalized,
    )
    existing = await session.scalar(
        select(User.id).where(User.username_normalized == normalized).limit(1)
    )
    if existing is not None:
        await commit_failure_audit(
            session,
            actor=actor,
            action="admin.user.create",
            target_type="user",
            target_username=normalized,
            reason_code="USERNAME_TAKEN",
        )
        raise AppError(
            status_code=409,
            code="USERNAME_TAKEN",
            message="The username is already in use.",
        )

    temporary_password: str | None = None
    if payload.password is None:
        temporary_password = generate_temporary_password()
        raw_password = temporary_password
    else:
        raw_password = payload.password
    validate_password(raw_password)

    user = User(
        username=payload.username.strip(),
        username_normalized=normalized,
        display_name=payload.display_name,
        role=payload.role,
        status="active",
        password_hash=hash_password(raw_password),
        must_change_password=True,
        profile=UserProfile(
            department=payload.department,
            learning_group=payload.learning_group,
        ),
    )
    session.add(user)
    try:
        await session.flush()
        add_audit_event(
            session,
            actor=actor,
            action="admin.user.create",
            target_type="user",
            target_id=user.id,
            target_username=normalized,
            outcome="success",
            context={"role": user.role},
        )
        await session.commit()
    except IntegrityError as exc:
        await commit_failure_audit(
            session,
            actor=actor,
            action="admin.user.create",
            target_type="user",
            target_username=normalized,
            reason_code="USERNAME_TAKEN",
        )
        raise AppError(
            status_code=409,
            code="USERNAME_TAKEN",
            message="The username is already in use.",
        ) from exc

    return UserCreateResponse(
        user=user_summary(user),
        temporary_password=temporary_password,
    )


def _encode_cursor(user: User) -> str:
    payload = json.dumps(
        {"created_at": user.created_at.isoformat(), "id": str(user.id)},
        separators=(",", ":"),
    ).encode("utf-8")
    return base64.urlsafe_b64encode(payload).decode("ascii").rstrip("=")


def _decode_cursor(cursor: str) -> tuple[datetime, UUID]:
    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        payload = json.loads(base64.urlsafe_b64decode(padded).decode("utf-8"))
        return datetime.fromisoformat(payload["created_at"]), UUID(payload["id"])
    except (ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        raise AppError(
            status_code=422,
            code="INVALID_CURSOR",
            message="The pagination cursor is invalid.",
        ) from exc


async def list_users(
    session: AsyncSession,
    actor: User,
    *,
    limit: int,
    cursor: str | None,
    search: str | None,
    role: str | None,
    status: str | None,
) -> UserListResponse:
    require_admin(actor)
    statement = select(User).options(selectinload(User.profile))
    if search:
        term = f"%{search.strip()}%"
        statement = statement.where(
            or_(User.username_normalized.ilike(term), User.display_name.ilike(term))
        )
    if role:
        statement = statement.where(User.role == role)
    if status:
        statement = statement.where(User.status == status)
    if cursor:
        created_at, last_id = _decode_cursor(cursor)
        statement = statement.where(
            or_(
                User.created_at < created_at,
                and_(User.created_at == created_at, User.id < last_id),
            )
        )
    statement = statement.order_by(User.created_at.desc(), User.id.desc()).limit(limit + 1)
    users = list((await session.scalars(statement)).all())
    has_more = len(users) > limit
    page = users[:limit]
    next_cursor = _encode_cursor(page[-1]) if has_more and page else None
    return UserListResponse(
        items=[user_summary(user) for user in page],
        next_cursor=next_cursor,
        has_more=has_more,
    )


async def get_user_detail(session: AsyncSession, actor: User, user_id: UUID) -> UserDetail:
    require_admin(actor)
    user = await _get_user(session, user_id)
    if user is None:
        raise AppError(status_code=404, code="USER_NOT_FOUND", message="User not found.")
    active_sessions = int(
        await session.scalar(
            select(func.count(distinct(RefreshToken.family_id))).where(
                RefreshToken.user_id == user.id,
                RefreshToken.revoked_at.is_(None),
                RefreshToken.expires_at > utcnow(),
            )
        )
        or 0
    )
    audit_events = int(
        await session.scalar(
            select(func.count(AuditLog.id)).where(
                AuditLog.target_id == user.id,
                AuditLog.created_at >= utcnow() - timedelta(days=30),
            )
        )
        or 0
    )
    return UserDetail(
        account=user_summary(user),
        aggregates=UserAggregates(
            active_sessions=active_sessions,
            audit_events_30d=audit_events,
        ),
    )


async def update_user(
    session: AsyncSession,
    actor: User,
    user_id: UUID,
    payload: AdminUserPatch,
) -> UserSummary:
    await ensure_admin_for_write(
        session,
        actor,
        action="admin.user.update",
        target_id=user_id,
    )
    await _acquire_admin_lock(session)
    target = await _get_user(session, user_id, lock=True)
    if target is None:
        await commit_failure_audit(
            session,
            actor=actor,
            action="admin.user.update",
            target_type="user",
            target_id=user_id,
            reason_code="USER_NOT_FOUND",
        )
        raise AppError(status_code=404, code="USER_NOT_FOUND", message="User not found.")

    prospective_role = payload.role if "role" in payload.model_fields_set else target.role
    prospective_status = payload.status if "status" in payload.model_fields_set else target.status
    if (
        target.role == "admin"
        and target.status == "active"
        and (prospective_role != "admin" or prospective_status != "active")
        and await _active_admin_count(session, excluding=target.id) == 0
    ):
        await commit_failure_audit(
            session,
            actor=actor,
            action="admin.user.update",
            target_type="user",
            target_id=target.id,
            target_username=target.username_normalized,
            reason_code="LAST_ADMIN_PROTECTED",
        )
        raise AppError(
            status_code=409,
            code="LAST_ADMIN_PROTECTED",
            message="The last active administrator cannot be demoted or disabled.",
        )

    if "display_name" in payload.model_fields_set:
        target.display_name = payload.display_name or target.display_name
    if "role" in payload.model_fields_set and payload.role is not None:
        target.role = payload.role
    if "status" in payload.model_fields_set and payload.status is not None:
        target.status = payload.status
    profile = target.profile
    if profile is None:
        profile = UserProfile(user=target)
        target.profile = profile
    if "department" in payload.model_fields_set:
        profile.department = payload.department
    if "learning_group" in payload.model_fields_set:
        profile.learning_group = payload.learning_group

    if target.status == "disabled":
        await session.execute(
            RefreshToken.__table__.update()
            .where(
                RefreshToken.user_id == target.id,
                RefreshToken.revoked_at.is_(None),
            )
            .values(revoked_at=utcnow(), revoked_reason="account_disabled")
        )

    add_audit_event(
        session,
        actor=actor,
        action="admin.user.update",
        target_type="user",
        target_id=target.id,
        target_username=target.username_normalized,
        outcome="success",
        context={
            "fields": sorted(payload.model_fields_set),
            "role": target.role,
            "status": target.status,
        },
    )
    await session.commit()
    return user_summary(target)


async def delete_user(session: AsyncSession, actor: User, user_id: UUID) -> None:
    await ensure_admin_for_write(
        session,
        actor,
        action="admin.user.delete",
        target_id=user_id,
    )
    if actor.id == user_id:
        await commit_failure_audit(
            session,
            actor=actor,
            action="admin.user.delete",
            target_type="user",
            target_id=user_id,
            target_username=actor.username_normalized,
            reason_code="SELF_DELETE_FORBIDDEN",
        )
        raise AppError(
            status_code=409,
            code="SELF_DELETE_FORBIDDEN",
            message="Administrators cannot delete their own account.",
        )
    await _acquire_admin_lock(session)
    target = await _get_user(session, user_id, lock=True)
    if target is None:
        await commit_failure_audit(
            session,
            actor=actor,
            action="admin.user.delete",
            target_type="user",
            target_id=user_id,
            reason_code="USER_NOT_FOUND",
        )
        raise AppError(status_code=404, code="USER_NOT_FOUND", message="User not found.")

    if (
        target.role == "admin"
        and target.status == "active"
        and await _active_admin_count(session, excluding=target.id) == 0
    ):
        await commit_failure_audit(
            session,
            actor=actor,
            action="admin.user.delete",
            target_type="user",
            target_id=target.id,
            target_username=target.username_normalized,
            reason_code="LAST_ADMIN_PROTECTED",
        )
        raise AppError(
            status_code=409,
            code="LAST_ADMIN_PROTECTED",
            message="The last active administrator cannot be deleted.",
        )

    add_audit_event(
        session,
        actor=actor,
        action="admin.user.delete",
        target_type="user",
        target_id=target.id,
        target_username=target.username_normalized,
        outcome="success",
        context={"role": target.role, "status": target.status},
    )
    await session.delete(target)
    await session.commit()


async def reset_password(
    session: AsyncSession,
    actor: User,
    user_id: UUID,
) -> PasswordResetResponse:
    await ensure_admin_for_write(
        session,
        actor,
        action="admin.user.reset_password",
        target_id=user_id,
    )
    target = await _get_user(session, user_id, lock=True)
    if target is None:
        await commit_failure_audit(
            session,
            actor=actor,
            action="admin.user.reset_password",
            target_type="user",
            target_id=user_id,
            reason_code="USER_NOT_FOUND",
        )
        raise AppError(status_code=404, code="USER_NOT_FOUND", message="User not found.")

    temporary_password = generate_temporary_password()
    target.password_hash = hash_password(temporary_password)
    target.must_change_password = True
    target.password_changed_at = utcnow()
    await session.execute(
        RefreshToken.__table__.update()
        .where(
            RefreshToken.user_id == target.id,
            RefreshToken.revoked_at.is_(None),
        )
        .values(revoked_at=utcnow(), revoked_reason="admin_reset")
    )
    add_audit_event(
        session,
        actor=actor,
        action="admin.user.reset_password",
        target_type="user",
        target_id=target.id,
        target_username=target.username_normalized,
        outcome="success",
    )
    await session.commit()
    return PasswordResetResponse(user_id=target.id, temporary_password=temporary_password)


async def bootstrap_admin(
    session: AsyncSession,
    *,
    username: str,
    display_name: str,
    password: str,
) -> User:
    normalized = normalize_username(username)
    if await _active_admin_count(session) > 0:
        raise AppError(
            status_code=409,
            code="ADMIN_ALREADY_EXISTS",
            message="An active administrator already exists.",
        )
    validate_password(password)
    user = User(
        username=username.strip(),
        username_normalized=normalized,
        display_name=display_name.strip(),
        role="admin",
        status="active",
        password_hash=hash_password(password),
        must_change_password=True,
        profile=UserProfile(),
    )
    session.add(user)
    try:
        await session.flush()
        add_audit_event(
            session,
            actor_id=None,
            actor_username="system",
            action="admin.bootstrap",
            target_type="user",
            target_id=user.id,
            target_username=normalized,
            outcome="success",
            context={"source": "cli"},
        )
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise AppError(
            status_code=409,
            code="USERNAME_TAKEN",
            message="The username is already in use.",
        ) from exc
    return user
