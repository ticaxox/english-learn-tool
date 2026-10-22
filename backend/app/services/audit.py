import logging
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.request_context import get_request_id
from app.models.identity import AuditLog, User

logger = logging.getLogger(__name__)


def add_audit_event(
    session: AsyncSession,
    *,
    action: str,
    target_type: str,
    outcome: str,
    actor: User | None = None,
    actor_id: UUID | None = None,
    actor_username: str | None = None,
    target_id: UUID | None = None,
    target_username: str | None = None,
    reason_code: str | None = None,
    request_id: str | None = None,
    context: dict[str, Any] | None = None,
) -> AuditLog:
    resolved_actor_id = actor_id or (actor.id if actor is not None else None)
    resolved_actor_username = actor_username or (
        actor.username_normalized if actor is not None else None
    )
    event = AuditLog(
        actor_id=resolved_actor_id,
        actor_username=resolved_actor_username,
        action=action,
        target_type=target_type,
        target_id=target_id,
        target_username=target_username,
        request_id=(request_id or get_request_id())[:128],
        outcome=outcome,
        reason_code=reason_code,
        context=context or {},
    )
    session.add(event)
    logger.info(
        "audit.recorded",
        extra={
            "event": action,
            "user_id": str(resolved_actor_id) if resolved_actor_id else None,
            "target_id": str(target_id) if target_id else None,
            "outcome": outcome,
            "reason_code": reason_code,
        },
    )
    return event


async def commit_failure_audit(
    session: AsyncSession,
    *,
    action: str,
    target_type: str,
    actor: User | None = None,
    target_id: UUID | None = None,
    target_username: str | None = None,
    reason_code: str | None = None,
    request_id: str | None = None,
    context: dict[str, Any] | None = None,
) -> None:
    """Roll back partial writes, persist a sanitized failure event, then raise afterward."""
    captured_actor_id = actor.id if actor is not None else None
    captured_actor_username = actor.username_normalized if actor is not None else None
    await session.rollback()
    add_audit_event(
        session,
        actor_id=captured_actor_id,
        actor_username=captured_actor_username,
        action=action,
        target_type=target_type,
        target_id=target_id,
        target_username=target_username,
        reason_code=reason_code,
        request_id=request_id,
        context=context,
        outcome="failure",
    )
    await session.commit()
