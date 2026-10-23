from __future__ import annotations

import base64
import logging
from datetime import UTC, date, datetime, time, timedelta
from typing import Any
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy import and_, delete, func, or_, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.errors import AppError
from app.models.ai import AiJob
from app.models.identity import User, UserProfile
from app.models.learning import DailyActivity, DailyPlan, DailyPlanWord, MemoryEvent, UserWordState
from app.models.notifications import Notification, NotificationOutbox
from app.schemas.ai_tasks import plain_text
from app.schemas.notifications import (
    NotificationCategoryPreferences,
    NotificationListResponse,
    NotificationPreferencesResponse,
    NotificationPreferencesUpdate,
    NotificationReadAllResponse,
    NotificationResponse,
    NotificationUnreadCountResponse,
)
from app.services.auth import utcnow

logger = logging.getLogger(__name__)

DEFAULT_CATEGORIES = NotificationCategoryPreferences().model_dump()
AI_CATEGORIES = {"ai_completed", "ai_failed", "plan_adjusted", "ai_action"}
DEFAULT_DND_START = "22:00"
DEFAULT_DND_END = "08:00"


def _default_preferences(settings: Settings) -> NotificationPreferencesResponse:
    return NotificationPreferencesResponse(
        categories=NotificationCategoryPreferences(**DEFAULT_CATEGORIES),
        dnd_start=DEFAULT_DND_START,
        dnd_end=DEFAULT_DND_END,
        daily_limit=settings.notification_daily_limit,
        timezone=settings.app_timezone,
    )


def _preferences_for_user(user: User, settings: Settings) -> NotificationPreferencesResponse:
    default = _default_preferences(settings)
    raw = user.profile.notification_preferences if user.profile else {}
    if not isinstance(raw, dict):
        return default
    try:
        categories = NotificationCategoryPreferences(
            **{**DEFAULT_CATEGORIES, **raw.get("categories", {})}
        )
        return NotificationPreferencesResponse(
            categories=categories,
            dnd_start=raw.get("dnd_start", default.dnd_start),
            dnd_end=raw.get("dnd_end", default.dnd_end),
            daily_limit=raw.get("daily_limit", default.daily_limit),
            timezone=raw.get("timezone", default.timezone),
        )
    except Exception:
        logger.warning("notification.preferences_invalid", extra={"user_id": str(user.id)})
        return default


async def get_preferences(
    session: AsyncSession, user: User, settings: Settings
) -> NotificationPreferencesResponse:
    return _preferences_for_user(user, settings)


async def update_preferences(
    session: AsyncSession,
    user: User,
    settings: Settings,
    payload: NotificationPreferencesUpdate,
) -> NotificationPreferencesResponse:
    profile = user.profile
    if profile is None:
        profile = UserProfile(user_id=user.id)
        session.add(profile)
        user.profile = profile
    profile.notification_preferences = payload.model_dump(mode="json")
    await session.commit()
    await session.refresh(profile)
    return _preferences_for_user(user, settings)


def _clock_minutes(value: str) -> int:
    hour, minute = (int(part) for part in value.split(":"))
    return hour * 60 + minute


def _is_dnd(local_now: datetime, start: str, end: str) -> bool:
    minute = local_now.hour * 60 + local_now.minute
    start_minute = _clock_minutes(start)
    end_minute = _clock_minutes(end)
    if start_minute == end_minute:
        return False
    if start_minute < end_minute:
        return start_minute <= minute < end_minute
    return minute >= start_minute or minute < end_minute


def _local_now(user: User, settings: Settings, now: datetime | None = None) -> datetime:
    zone = ZoneInfo(user.profile.timezone if user.profile else settings.app_timezone)
    return (now or utcnow()).astimezone(zone)


def _day_bounds_utc(local_day: date, zone_name: str) -> tuple[datetime, datetime]:
    zone = ZoneInfo(zone_name)
    start = datetime.combine(local_day, time.min, tzinfo=zone).astimezone(UTC)
    end = datetime.combine(local_day + timedelta(days=1), time.min, tzinfo=zone).astimezone(UTC)
    return start, end


def _safe_text(value: Any, limit: int) -> str:
    return plain_text(str(value))[:limit]


def _response(notification: Notification) -> NotificationResponse:
    return NotificationResponse(
        id=notification.id,
        category=notification.category,
        title=notification.title,
        body=notification.body,
        status=notification.status,
        dedupe_key=notification.dedupe_key,
        business_ref_type=notification.business_ref_type,
        business_ref_id=notification.business_ref_id,
        metadata=notification.notification_metadata,
        scheduled_at=notification.scheduled_at,
        sent_at=notification.sent_at,
        read_at=notification.read_at,
        expires_at=notification.expires_at,
        created_at=notification.created_at,
    )


def _encode_cursor(notification: Notification) -> str:
    raw = f"{notification.created_at.isoformat()}|{notification.id}"
    return base64.urlsafe_b64encode(raw.encode()).decode()


def _decode_cursor(cursor: str) -> tuple[datetime, UUID]:
    try:
        raw = base64.urlsafe_b64decode(cursor.encode()).decode()
        created_at, notification_id = raw.split("|", 1)
        return datetime.fromisoformat(created_at), UUID(notification_id)
    except (ValueError, TypeError, UnicodeDecodeError) as exc:
        raise AppError(
            status_code=422,
            code="NOTIFICATION_CURSOR_INVALID",
            message="The notification cursor is invalid.",
        ) from exc


async def enqueue_notification_event(
    session: AsyncSession,
    *,
    user_id: UUID,
    category: str,
    dedupe_key: str,
    event_type: str,
    payload: dict[str, Any],
    available_at: datetime | None = None,
) -> None:
    if len(dedupe_key) > 200:
        raise ValueError("Notification dedupe keys must be at most 200 characters.")
    statement = (
        pg_insert(NotificationOutbox)
        .values(
            user_id=user_id,
            event_type=event_type,
            category=category,
            dedupe_key=dedupe_key,
            payload=payload,
            status="pending",
            available_at=available_at or utcnow(),
        )
        .on_conflict_do_nothing(index_elements=["user_id", "dedupe_key"])
    )
    result = await session.execute(statement)
    return bool(result.rowcount)


async def notify_ai_job(
    session: AsyncSession,
    job: AiJob,
    *,
    succeeded: bool,
) -> None:
    category = "ai_completed" if succeeded else "ai_failed"
    status = "completed" if succeeded else "failed"
    await enqueue_notification_event(
        session,
        user_id=job.user_id,
        category=category,
        dedupe_key=f"user:{job.user_id}:ai:{job.id}:{status}",
        event_type=f"ai.job.{status}",
        payload={
            "title": "AI 任务已完成" if succeeded else "AI 任务未完成",
            "body": (
                "你的 AI 任务已经完成，可以查看结果。"
                if succeeded
                else "AI 任务未能完成，可以稍后重试；学习记录不会因此丢失。"
            ),
            "business_ref_type": "ai_job",
            "business_ref_id": str(job.id),
            "task_type": job.task_type,
        },
    )


async def notify_plan_adjusted(session: AsyncSession, *, user_id: UUID, job_id: UUID) -> None:
    await enqueue_notification_event(
        session,
        user_id=user_id,
        category="plan_adjusted",
        dedupe_key=f"user:{user_id}:plan:{job_id}",
        event_type="ai.plan_adjusted",
        payload={
            "title": "学习计划已调整",
            "body": "AI 教练已根据你的学习情况更新计划，请查看今日任务。",
            "business_ref_type": "ai_job",
            "business_ref_id": str(job_id),
        },
    )


async def notify_ai_action(session: AsyncSession, *, user_id: UUID, action_id: UUID) -> None:
    await enqueue_notification_event(
        session,
        user_id=user_id,
        category="ai_action",
        dedupe_key=f"user:{user_id}:action:{action_id}",
        event_type="ai.action.applied",
        payload={
            "title": "AI 操作已执行",
            "body": "AI 教练执行了一项需要你知晓的操作，可在教练记录中查看或撤销。",
            "business_ref_type": "coach_action",
            "business_ref_id": str(action_id),
        },
    )


def _safe_metadata(payload: dict[str, Any]) -> dict[str, Any]:
    allowed = {"task_type", "business_ref_type", "business_ref_id", "job_id", "status"}
    return {
        key: (str(value)[:200] if value is not None else None)
        for key, value in payload.items()
        if key in allowed
    }


async def process_notification_outbox(
    session: AsyncSession,
    settings: Settings,
    *,
    now: datetime | None = None,
) -> int:
    current = now or utcnow()
    events = list(
        (
            await session.scalars(
                select(NotificationOutbox)
                .where(
                    NotificationOutbox.status == "pending",
                    NotificationOutbox.available_at <= current,
                )
                .order_by(NotificationOutbox.created_at.asc())
                .limit(settings.notification_outbox_batch_size)
                .with_for_update(skip_locked=True)
            )
        ).all()
    )
    processed = 0
    for event in events:
        existing = await session.scalar(
            select(Notification).where(
                Notification.user_id == event.user_id,
                Notification.dedupe_key == event.dedupe_key,
            )
        )
        if existing is not None:
            event.status = "processed"
            event.processed_at = current
            processed += 1
            continue
        user = await session.get(User, event.user_id)
        if user is None:
            event.status = "processed"
            event.processed_at = current
            processed += 1
            continue
        preferences = _preferences_for_user(user, settings)
        local_now = _local_now(user, settings, current)
        zone_name = preferences.timezone
        local_day = local_now.date()
        start_at, end_at = _day_bounds_utc(local_day, zone_name)
        category_enabled = getattr(preferences.categories, event.category, False)
        is_ai = event.category in AI_CATEGORIES
        status = "sent"
        reason: str | None = None
        sent_at: datetime | None = current
        if not category_enabled:
            status = "suppressed"
            reason = "category_disabled"
            sent_at = None
        elif not is_ai and _is_dnd(local_now, preferences.dnd_start, preferences.dnd_end):
            status = "suppressed"
            reason = "do_not_disturb"
            sent_at = None
        elif not is_ai:
            sent_count = int(
                await session.scalar(
                    select(func.count(Notification.id)).where(
                        Notification.user_id == user.id,
                        Notification.status == "sent",
                        Notification.sent_at >= start_at,
                        Notification.sent_at < end_at,
                    )
                )
                or 0
            )
            same_category = await session.scalar(
                select(Notification.id)
                .where(
                    Notification.user_id == user.id,
                    Notification.category == event.category,
                    Notification.status == "sent",
                    Notification.sent_at >= start_at,
                    Notification.sent_at < end_at,
                )
                .limit(1)
            )
            if same_category is not None:
                status = "merged"
                reason = "same_category_merged"
                sent_at = None
            elif sent_count >= preferences.daily_limit:
                status = "suppressed"
                reason = "daily_limit"
                sent_at = None
        title = _safe_text(event.payload.get("title", "学习提醒"), 200)
        body = _safe_text(event.payload.get("body", "查看你的学习任务。"), 4000)
        business_ref_id = event.payload.get("business_ref_id")
        try:
            parsed_ref_id = UUID(str(business_ref_id)) if business_ref_id else None
        except ValueError:
            parsed_ref_id = None
        notification = Notification(
            user_id=user.id,
            category=event.category,
            title=title,
            body=body,
            status=status,
            dedupe_key=event.dedupe_key,
            business_ref_type=event.payload.get("business_ref_type"),
            business_ref_id=parsed_ref_id,
            notification_metadata=_safe_metadata(event.payload),
            scheduled_at=event.available_at,
            sent_at=sent_at,
            expires_at=current + timedelta(days=settings.notification_ttl_days),
            suppressed_reason=reason,
        )
        session.add(notification)
        event.status = "processed"
        event.processed_at = current
        await session.flush()
        processed += 1
    if events:
        await session.commit()
    return processed


async def enqueue_scheduled_notification_events(
    session: AsyncSession,
    settings: Settings,
    *,
    now: datetime | None = None,
) -> int:
    current = now or utcnow()
    local_day = current.astimezone(ZoneInfo(settings.app_timezone)).date()
    created = 0

    due_users = list(
        (
            await session.scalars(
                select(UserWordState.user_id)
                .where(
                    UserWordState.status.in_(("new", "learning", "review", "relearning")),
                    UserWordState.due_at <= current,
                )
                .distinct()
            )
        ).all()
    )
    for user_id in due_users:
        if await enqueue_notification_event(
            session,
            user_id=user_id,
            category="due_review",
            dedupe_key=f"user:{user_id}:due:{local_day.isoformat()}",
            event_type="learning.due_review",
            payload={
                "title": "有到期单词可以复习",
                "body": "你有到期单词可以复习，完成一小段即可继续保持学习节奏。",
            },
            available_at=current,
        ):
            created += 1

    plans = list(
        (await session.scalars(select(DailyPlan).where(DailyPlan.local_date == local_day))).all()
    )
    local_now = current.astimezone(ZoneInfo(settings.app_timezone))
    for plan in plans:
        words = list(
            (
                await session.scalars(select(DailyPlanWord).where(DailyPlanWord.plan_id == plan.id))
            ).all()
        )
        if not words:
            continue
        completed = sum(1 for word in words if word.completed_at is not None)
        ratio = completed / len(words)
        user = await session.get(User, plan.user_id)
        if user is None:
            continue
        if local_now.hour >= 18 and completed < len(words):
            if await enqueue_notification_event(
                session,
                user_id=user.id,
                category="today_incomplete",
                dedupe_key=f"user:{user.id}:today:{local_day.isoformat()}",
                event_type="learning.today_incomplete",
                payload={
                    "title": "今天的学习任务还可以继续",
                    "body": "完成最小一组学习任务即可，不需要给自己增加压力。",
                },
                available_at=current,
            ):
                created += 1
        if local_now.hour >= 20 and ratio < 0.5:
            history = await session.scalar(
                select(DailyActivity.user_id)
                .where(
                    DailyActivity.user_id == user.id,
                    DailyActivity.local_date < local_day,
                    DailyActivity.active_seconds > 0,
                )
                .limit(1)
            )
            start_at, end_at = _day_bounds_utc(local_day, settings.app_timezone)
            new_event = await session.scalar(
                select(MemoryEvent.id)
                .where(
                    MemoryEvent.user_id == user.id,
                    MemoryEvent.created_at >= start_at,
                    MemoryEvent.created_at < end_at,
                )
                .limit(1)
            )
            if history is not None and new_event is None:
                if await enqueue_notification_event(
                    session,
                    user_id=user.id,
                    category="streak_risk",
                    dedupe_key=f"user:{user.id}:streak:{local_day.isoformat()}",
                    event_type="learning.streak_risk",
                    payload={
                        "title": "今天还可以做一点学习",
                        "body": "完成一组最小的复习或新词任务即可，保持节奏比追求数量更重要。",
                    },
                    available_at=current,
                ):
                    created += 1
    if created:
        await session.commit()
    return created


async def cleanup_expired_notifications(
    session: AsyncSession, settings: Settings, *, now: datetime | None = None
) -> int:
    current = now or utcnow()
    result = await session.execute(delete(Notification).where(Notification.expires_at < current))
    cutoff = current - timedelta(days=settings.notification_ttl_days)
    await session.execute(
        delete(NotificationOutbox).where(
            NotificationOutbox.status == "processed",
            NotificationOutbox.processed_at < cutoff,
        )
    )
    await session.commit()
    return int(result.rowcount or 0)


async def list_notifications(
    session: AsyncSession,
    user: User,
    *,
    limit: int = 20,
    cursor: str | None = None,
    unread_only: bool = False,
) -> NotificationListResponse:
    filters = [Notification.user_id == user.id, Notification.status.in_(("sent", "merged"))]
    if unread_only:
        filters.append(Notification.read_at.is_(None))
    if cursor:
        created_at, cursor_id = _decode_cursor(cursor)
        filters.append(
            or_(
                Notification.created_at < created_at,
                and_(
                    Notification.created_at == created_at,
                    Notification.id < cursor_id,
                ),
            )
        )
    rows = list(
        (
            await session.scalars(
                select(Notification)
                .where(*filters)
                .order_by(Notification.created_at.desc(), Notification.id.desc())
                .limit(limit + 1)
            )
        ).all()
    )
    has_more = len(rows) > limit
    visible = rows[:limit]
    return NotificationListResponse(
        items=[_response(item) for item in visible],
        next_cursor=_encode_cursor(visible[-1]) if has_more and visible else None,
        has_more=has_more,
    )


async def mark_notification_read(
    session: AsyncSession, user: User, notification_id: UUID
) -> NotificationResponse:
    notification = await session.scalar(
        select(Notification).where(
            Notification.id == notification_id,
            Notification.user_id == user.id,
        )
    )
    if notification is None:
        raise AppError(
            status_code=404,
            code="NOTIFICATION_NOT_FOUND",
            message="The notification was not found.",
        )
    if notification.read_at is None:
        notification.read_at = utcnow()
        await session.commit()
    return _response(notification)


async def mark_all_notifications_read(
    session: AsyncSession, user: User
) -> NotificationReadAllResponse:
    now = utcnow()
    result = await session.execute(
        Notification.__table__.update()
        .where(
            Notification.user_id == user.id,
            Notification.status.in_(("sent", "merged")),
            Notification.read_at.is_(None),
        )
        .values(read_at=now)
    )
    await session.commit()
    return NotificationReadAllResponse(updated_count=int(result.rowcount or 0))


async def unread_notification_count(
    session: AsyncSession, user: User
) -> NotificationUnreadCountResponse:
    count = int(
        await session.scalar(
            select(func.count(Notification.id)).where(
                Notification.user_id == user.id,
                Notification.status.in_(("sent", "merged")),
                Notification.read_at.is_(None),
            )
        )
        or 0
    )
    return NotificationUnreadCountResponse(unread_count=count)
