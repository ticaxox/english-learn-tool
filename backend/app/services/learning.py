"""Learning profile, daily plan snapshots, heartbeats, and personal statistics."""

from __future__ import annotations

import math
from datetime import date, datetime, timedelta
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy import and_, delete, func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.errors import AppError
from app.models.identity import User, UserProfile
from app.models.learning import (
    DailyActivity,
    DailyPlan,
    DailyPlanWord,
    LearningHeartbeat,
    MemoryEvent,
    MemorySession,
    MemorySessionItem,
    MistakeFlag,
    UserWordState,
)
from app.models.wordbooks import (
    Wordbook,
    WordbookActivation,
    WordbookDefinition,
    WordbookEntry,
)
from app.schemas.learning import (
    HeartbeatResponse,
    LearningEventListResponse,
    LearningEventResponse,
    LearningProfilePatch,
    LearningProfileResponse,
    LearningStatsResponse,
    PlanSectionProgress,
    PlanWordResponse,
    StatsSourceBreakdown,
    TodayResponse,
)
from app.services.ai_memory import sync_profile_memories
from app.services.auth import utcnow

PLAN_RULES_VERSION = "daily-plan-1.0.0"
LEARNING_CALCULATION_VERSION = f"plan:{PLAN_RULES_VERSION}|fsrs-6.3.2"
PLAN_LOCK_BASE = 73100200261023
HEARTBEAT_MAX_SECONDS = 30
HEARTBEAT_STALE_SECONDS = 180
HEARTBEAT_IDLE_GAP_SECONDS = 120
DEFAULT_TIMEZONE = "Asia/Shanghai"
MAX_PLAN_WORDS = 500

_DUE_STATUSES = ("learning", "review", "relearning")
_EXCLUDED_NEW_STATUSES = ("mastered", "suspended")


def _zone(name: str) -> ZoneInfo:
    try:
        return ZoneInfo(name)
    except Exception:  # pragma: no cover - tzdata always ships Asia/Shanghai
        return ZoneInfo(DEFAULT_TIMEZONE)


def local_date_for(
    settings: Settings, user: User | None = None, *, now: datetime | None = None
) -> date:
    timezone_name = DEFAULT_TIMEZONE
    if user is not None and user.profile is not None:
        timezone_name = user.profile.timezone or DEFAULT_TIMEZONE
    elif settings.app_timezone:
        timezone_name = settings.app_timezone
    return (now or utcnow()).astimezone(_zone(timezone_name)).date()


def _profile_response(profile: UserProfile) -> LearningProfileResponse:
    return LearningProfileResponse(
        target_exam=profile.target_exam,
        exam_date=profile.exam_date,
        daily_new_words=profile.daily_new_words,
        daily_study_minutes=profile.daily_study_minutes,
        department=profile.department,
        learning_group=profile.learning_group,
        timezone=profile.timezone,
        onboarding_completed=profile.onboarding_completed,
        notification_preferences=profile.notification_preferences or {},
        updated_at=profile.updated_at,
    )


async def _load_profile(session: AsyncSession, user: User, *, lock: bool = False) -> UserProfile:
    statement = select(UserProfile).where(UserProfile.user_id == user.id)
    if lock:
        statement = statement.with_for_update()
    profile = await session.scalar(statement)
    if profile is None:
        profile = UserProfile(
            user_id=user.id,
            department=user.profile.department if user.profile else None,
            learning_group=user.profile.learning_group if user.profile else None,
            timezone=DEFAULT_TIMEZONE,
        )
        session.add(profile)
        await session.flush()
        await session.refresh(profile)
    return profile


async def get_profile(session: AsyncSession, user: User) -> LearningProfileResponse:
    profile = await session.scalar(select(UserProfile).where(UserProfile.user_id == user.id))
    if profile is None:
        return LearningProfileResponse(
            target_exam=None,
            exam_date=None,
            daily_new_words=20,
            daily_study_minutes=30,
            department=user.profile.department if user.profile else None,
            learning_group=user.profile.learning_group if user.profile else None,
            timezone=DEFAULT_TIMEZONE,
            onboarding_completed=False,
            notification_preferences={},
            updated_at=user.updated_at,
        )
    return _profile_response(profile)


async def update_profile(
    session: AsyncSession,
    user: User,
    payload: LearningProfilePatch,
    *,
    settings: Settings,
) -> LearningProfileResponse:
    profile = await _load_profile(session, user, lock=True)
    if payload.exam_date is not None and payload.exam_date <= local_date_for(settings, user):
        raise AppError(
            status_code=422,
            code="PROFILE_EXAM_DATE_INVALID",
            message="The exam date must be in the future.",
        )
    fields = payload.model_fields_set
    if "target_exam" in fields:
        profile.target_exam = payload.target_exam
    if "exam_date" in fields:
        profile.exam_date = payload.exam_date
    if payload.daily_new_words is not None:
        profile.daily_new_words = payload.daily_new_words
    if payload.daily_study_minutes is not None:
        profile.daily_study_minutes = payload.daily_study_minutes
    if payload.notification_preferences is not None:
        profile.notification_preferences = payload.notification_preferences
    if payload.onboarding_completed is not None:
        profile.onboarding_completed = payload.onboarding_completed
    elif profile.target_exam is not None:
        profile.onboarding_completed = True
    profile.timezone = DEFAULT_TIMEZONE
    await sync_profile_memories(session, user)
    await session.commit()
    await session.refresh(profile)
    return _profile_response(profile)


async def _activated_wordbook(session: AsyncSession, user: User) -> Wordbook:
    book = await session.scalar(
        select(Wordbook)
        .join(WordbookActivation, WordbookActivation.wordbook_id == Wordbook.id)
        .where(
            WordbookActivation.user_id == user.id,
            Wordbook.owner_id == user.id,
            Wordbook.status == "ready",
        )
    )
    if book is None:
        raise AppError(
            status_code=409,
            code="ACTIVE_WORDBOOK_REQUIRED",
            message="An active wordbook is required before starting a study plan.",
        )
    return book


async def _plan_words(
    session: AsyncSession, plan_id: UUID
) -> list[tuple[DailyPlanWord, WordbookEntry, WordbookDefinition | None]]:
    rows = (
        await session.execute(
            select(DailyPlanWord, WordbookEntry, WordbookDefinition)
            .join(WordbookEntry, WordbookEntry.id == DailyPlanWord.entry_id)
            .outerjoin(
                WordbookDefinition,
                and_(
                    WordbookDefinition.entry_id == WordbookEntry.id,
                    WordbookDefinition.sequence == 0,
                ),
            )
            .where(DailyPlanWord.plan_id == plan_id)
            .order_by(DailyPlanWord.position)
        )
    ).all()
    return [(row[0], row[1], row[2]) for row in rows]


async def _build_plan(
    session: AsyncSession,
    user: User,
    book: Wordbook,
    *,
    profile: UserProfile,
    local_date: date,
    now: datetime,
) -> DailyPlan:
    snapshot_time = now
    due_rows = (
        (
            await session.execute(
                select(UserWordState.entry_id)
                .where(
                    UserWordState.user_id == user.id,
                    UserWordState.wordbook_id == book.id,
                    UserWordState.status.in_(_DUE_STATUSES),
                    UserWordState.due_at.is_not(None),
                    UserWordState.due_at <= snapshot_time,
                )
                .order_by(UserWordState.due_at, UserWordState.entry_id)
                .limit(MAX_PLAN_WORDS)
            )
        )
        .scalars()
        .all()
    )
    due_ids = list(dict.fromkeys(due_rows))

    excluded = set(due_ids)
    excluded.update(
        (
            await session.scalars(
                select(UserWordState.entry_id).where(
                    UserWordState.user_id == user.id,
                    UserWordState.wordbook_id == book.id,
                    UserWordState.status.in_(_EXCLUDED_NEW_STATUSES),
                )
            )
        ).all()
    )

    candidate_limit = profile.daily_new_words * 4 + 50
    candidates = (
        await session.scalars(
            select(WordbookEntry.id)
            .where(WordbookEntry.wordbook_id == book.id)
            .where(
                WordbookEntry.id.not_in(excluded) if excluded else text("true"),
            )
            .order_by(WordbookEntry.sequence, WordbookEntry.id)
            .limit(candidate_limit)
        )
    ).all()
    unlearned_ids = set(
        (
            await session.scalars(
                select(UserWordState.entry_id).where(
                    UserWordState.user_id == user.id,
                    UserWordState.wordbook_id == book.id,
                )
            )
        ).all()
    )
    fresh = [entry_id for entry_id in candidates if entry_id not in unlearned_ids]
    fallback = [entry_id for entry_id in candidates if entry_id in unlearned_ids]

    target_new = profile.daily_new_words
    # Deterministic ordering derived from the plan date keeps concurrent creators identical
    # while still varying the picked words from day to day.
    import hashlib

    def _order_key(entry_id: UUID) -> str:
        return hashlib.sha256(f"{local_date.isoformat()}:{entry_id}".encode()).hexdigest()

    fresh.sort(key=_order_key)
    fallback.sort(key=_order_key)
    ordered_pool = fresh + fallback
    selected_new = ordered_pool[:target_new]
    new_word_reason: str | None = None
    if len(selected_new) < target_new:
        new_word_reason = "INSUFFICIENT_NEW_WORDS"

    plan = DailyPlan(
        user_id=user.id,
        local_date=local_date,
        wordbook_id=book.id,
        new_word_target=len(selected_new),
        study_minutes_target=profile.daily_study_minutes,
        snapshot_time=snapshot_time,
        calculation_version=LEARNING_CALCULATION_VERSION,
        status="not_started",
        new_word_reason=new_word_reason,
        stats={"requested_new_words": target_new},
    )
    session.add(plan)
    await session.flush()

    position = 0
    for entry_id in due_ids:
        session.add(
            DailyPlanWord(plan_id=plan.id, entry_id=entry_id, reason="due", position=position)
        )
        position += 1
    for entry_id in selected_new:
        session.add(
            DailyPlanWord(plan_id=plan.id, entry_id=entry_id, reason="new", position=position)
        )
        position += 1
    await session.flush()
    plan.stats = {
        "requested_new_words": target_new,
        "new_words": len(selected_new),
        "due_words": len(due_ids),
    }
    return plan


async def ensure_daily_plan(
    session: AsyncSession,
    user: User,
    *,
    settings: Settings,
    now: datetime | None = None,
) -> DailyPlan:
    current = now or utcnow()
    local_date = local_date_for(settings, user, now=current)
    existing = await session.scalar(
        select(DailyPlan).where(
            DailyPlan.user_id == user.id,
            DailyPlan.local_date == local_date,
        )
    )
    if existing is not None:
        return existing

    book = await _activated_wordbook(session, user)
    profile = await _load_profile(session, user)

    # Serialize plan creation per user so concurrent ensure calls cannot create two snapshots
    # and cannot interleave the random selection.
    await session.execute(
        text("SELECT pg_advisory_xact_lock(:key)"),
        {"key": PLAN_LOCK_BASE + (user.id.int % 1_000_000)},
    )
    existing = await session.scalar(
        select(DailyPlan)
        .where(DailyPlan.user_id == user.id, DailyPlan.local_date == local_date)
        .with_for_update()
    )
    if existing is not None:
        return existing
    try:
        plan = await _build_plan(
            session,
            user,
            book,
            profile=profile,
            local_date=local_date,
            now=current,
        )
        await session.commit()
    except IntegrityError:
        await session.rollback()
        plan = await session.scalar(
            select(DailyPlan).where(
                DailyPlan.user_id == user.id,
                DailyPlan.local_date == local_date,
            )
        )
        if plan is None:
            raise
    return plan


async def _activity(session: AsyncSession, user: User, local_date: date, *, lock: bool = False):
    statement = select(DailyActivity).where(
        DailyActivity.user_id == user.id,
        DailyActivity.local_date == local_date,
    )
    if lock:
        statement = statement.with_for_update()
    return await session.scalar(statement)


async def _extra_due_count(
    session: AsyncSession, user: User, book: Wordbook, plan: DailyPlan
) -> int:
    planned = set(
        (
            await session.scalars(
                select(DailyPlanWord.entry_id).where(DailyPlanWord.plan_id == plan.id)
            )
        ).all()
    )
    due = (
        await session.scalars(
            select(UserWordState.entry_id).where(
                UserWordState.user_id == user.id,
                UserWordState.wordbook_id == book.id,
                UserWordState.status.in_(_DUE_STATUSES),
                UserWordState.due_at.is_not(None),
                UserWordState.due_at <= utcnow(),
                UserWordState.due_at > plan.snapshot_time,
            )
        )
    ).all()
    return len([entry_id for entry_id in due if entry_id not in planned])


async def _today_items(session: AsyncSession, plan: DailyPlan) -> list[PlanWordResponse]:
    rows = await _plan_words(session, plan.id)
    return [
        PlanWordResponse(
            entry_id=entry.id,
            headword=entry.headword,
            phonetic=entry.phonetic,
            definition_zh=definition.definition_zh if definition else None,
            reason=plan_word.reason,
            is_extra=plan_word.is_extra,
            position=plan_word.position,
            completed=plan_word.completed_at is not None,
        )
        for plan_word, entry, definition in rows
    ]


async def today_summary(
    session: AsyncSession,
    user: User,
    *,
    settings: Settings,
    now: datetime | None = None,
) -> TodayResponse:
    current = now or utcnow()
    book = await _activated_wordbook(session, user)
    plan = await ensure_daily_plan(session, user, settings=settings, now=current)
    plan = await session.scalar(select(DailyPlan).where(DailyPlan.id == plan.id))
    if plan is None:
        raise AppError(
            status_code=409,
            code="ACTIVE_WORDBOOK_REQUIRED",
            message="An active wordbook is required before starting a study plan.",
        )
    if plan.wordbook_id != book.id:
        book = await session.scalar(select(Wordbook).where(Wordbook.id == plan.wordbook_id))
        if book is None:
            raise AppError(
                status_code=409,
                code="ACTIVE_WORDBOOK_REQUIRED",
                message="An active wordbook is required before starting a study plan.",
            )

    items = await _today_items(session, plan)
    new_items = [item for item in items if item.reason == "new"]
    due_items = [item for item in items if item.reason == "due"]
    new_completed = sum(1 for item in new_items if item.completed)
    due_completed = sum(1 for item in due_items if item.completed)

    activity = await _activity(session, user, plan.local_date)
    active_seconds = activity.active_seconds if activity else 0
    active_minutes = active_seconds // 60
    goal_reached = active_minutes >= plan.study_minutes_target
    extra_due = await _extra_due_count(session, user, book, plan)

    def _section(target: int, completed: int) -> PlanSectionProgress:
        if target == 0:
            status = "completed"
        elif completed == 0:
            status = "not_started"
        elif completed >= target:
            status = "completed"
        else:
            status = "in_progress"
        return PlanSectionProgress(target=target, completed=completed, status=status)

    new_section = _section(len(new_items), new_completed)
    due_section = _section(len(due_items), due_completed)
    complete = (
        new_section.status == "completed"
        and due_section.status == "completed"
        and (new_completed + due_completed) > 0
    )
    if complete and extra_due > 0:
        status_value = "extra_available"
    elif complete:
        status_value = "completed"
    elif new_completed + due_completed > 0:
        status_value = "in_progress"
    else:
        status_value = "not_started"
    if plan.status != status_value:
        plan.status = status_value
        await session.commit()

    return TodayResponse(
        local_date=plan.local_date,
        wordbook_id=book.id,
        wordbook_name=book.name,
        status=status_value,
        new_words=new_section,
        due_reviews=due_section,
        new_word_reason=plan.new_word_reason,
        extra_due_available=extra_due > 0,
        extra_due_count=extra_due,
        study_minutes_target=plan.study_minutes_target,
        active_minutes_today=active_minutes,
        goal_reached=goal_reached,
        calculation_version=plan.calculation_version,
        generated_at=plan.generated_at,
        items=items,
    )


async def record_heartbeat(
    session: AsyncSession,
    user: User,
    *,
    settings: Settings,
    idempotency_key: str,
    now: datetime | None = None,
) -> HeartbeatResponse:
    current = now or utcnow()
    local_date = local_date_for(settings, user, now=current)
    if len(idempotency_key) > 128:
        raise AppError(
            status_code=422,
            code="HEARTBEAT_KEY_INVALID",
            message="The heartbeat key must be at most 128 characters.",
        )
    existing_event = await session.scalar(
        select(LearningHeartbeat).where(
            LearningHeartbeat.user_id == user.id,
            LearningHeartbeat.idempotency_key == idempotency_key,
        )
    )
    if existing_event is not None:
        activity = await _activity(session, user, existing_event.local_date)
        active_seconds = activity.active_seconds if activity else 0
        return HeartbeatResponse(
            local_date=existing_event.local_date,
            credited_seconds=0,
            active_seconds_today=active_seconds,
            active_minutes_today=active_seconds // 60,
            study_minutes_target=await _study_target(session, user),
            goal_reached=active_seconds // 60 >= await _study_target(session, user),
            heartbeat_count=activity.heartbeat_count if activity else 0,
        )

    await session.execute(
        text("SELECT pg_advisory_xact_lock(:key)"),
        {"key": PLAN_LOCK_BASE + 500000 + (user.id.int % 1_000_000)},
    )
    activity = await _activity(session, user, local_date, lock=True)
    if activity is None:
        activity = DailyActivity(user_id=user.id, local_date=local_date, active_seconds=0)
        session.add(activity)
        await session.flush()
        activity = await _activity(session, user, local_date, lock=True)
        if activity is None:  # pragma: no cover - defensive
            raise AppError(
                status_code=409,
                code="HEARTBEAT_CONFLICT",
                message="The activity window could not be created.",
            )
    now_utc = current
    credited = 0
    if activity.last_heartbeat_at is None:
        credited = 0
    else:
        delta = (now_utc - activity.last_heartbeat_at).total_seconds()
        if delta <= 0:
            credited = 0
        elif delta > HEARTBEAT_STALE_SECONDS:
            # A page that was hidden or a clock that jumped must not grant a large block of time.
            credited = 0
        else:
            credited = int(min(HEARTBEAT_MAX_SECONDS, math.ceil(delta)))
        if delta > HEARTBEAT_IDLE_GAP_SECONDS:
            credited = 0
    activity.active_seconds += credited
    activity.heartbeat_count += 1
    activity.last_heartbeat_at = now_utc
    session.add(
        LearningHeartbeat(
            user_id=user.id,
            local_date=local_date,
            idempotency_key=idempotency_key,
            credited_seconds=credited,
            received_at=now_utc,
        )
    )
    await session.commit()
    target = await _study_target(session, user)
    return HeartbeatResponse(
        local_date=local_date,
        credited_seconds=credited,
        active_seconds_today=activity.active_seconds,
        active_minutes_today=activity.active_seconds // 60,
        study_minutes_target=target,
        goal_reached=activity.active_seconds // 60 >= target,
        heartbeat_count=activity.heartbeat_count,
    )


async def _study_target(session: AsyncSession, user: User) -> int:
    value = await session.scalar(
        select(UserProfile.daily_study_minutes).where(UserProfile.user_id == user.id)
    )
    return int(value or 30)


async def _streak_days(session: AsyncSession, user: User, today: date) -> int:
    event_dates = set(
        (
            await session.scalars(
                select(func.date(MemoryEvent.created_at)).where(
                    MemoryEvent.user_id == user.id,
                )
            )
        ).all()
    )
    activity_dates = set(
        (
            await session.scalars(
                select(DailyActivity.local_date).where(
                    DailyActivity.user_id == user.id,
                    DailyActivity.active_seconds > 0,
                )
            )
        ).all()
    )
    days = {value for value in (event_dates | activity_dates) if value is not None}
    streak = 0
    cursor = today
    if cursor not in days:
        cursor = cursor - timedelta(days=1)
    while cursor in days:
        streak += 1
        cursor = cursor - timedelta(days=1)
    return streak


async def learning_stats(
    session: AsyncSession,
    user: User,
    *,
    settings: Settings,
    now: datetime | None = None,
) -> LearningStatsResponse:
    current = now or utcnow()
    local_date = local_date_for(settings, user, now=current)
    activity = await _activity(session, user, local_date)
    active_seconds = activity.active_seconds if activity else 0
    target = await _study_target(session, user)
    plan = await session.scalar(
        select(DailyPlan).where(DailyPlan.user_id == user.id, DailyPlan.local_date == local_date)
    )
    new_completed = 0
    due_completed = 0
    if plan is not None:
        rows = (
            await session.execute(
                select(DailyPlanWord.reason, func.count(DailyPlanWord.id))
                .where(
                    DailyPlanWord.plan_id == plan.id,
                    DailyPlanWord.completed_at.is_not(None),
                )
                .group_by(DailyPlanWord.reason)
            )
        ).all()
        for reason, count in rows:
            if reason == "new":
                new_completed = int(count)
            else:
                due_completed = int(count)
    event_count = int(
        await session.scalar(
            select(func.count(MemoryEvent.id)).where(MemoryEvent.user_id == user.id)
        )
        or 0
    )
    session_count = int(
        await session.scalar(
            select(func.count(MemorySession.id)).where(MemorySession.user_id == user.id)
        )
        or 0
    )
    heartbeat_seconds = int(
        await session.scalar(
            select(func.coalesce(func.sum(DailyActivity.active_seconds), 0)).where(
                DailyActivity.user_id == user.id
            )
        )
        or 0
    )
    return LearningStatsResponse(
        local_date=local_date,
        active_minutes_today=active_seconds // 60,
        study_minutes_target=target,
        goal_reached=active_seconds // 60 >= target,
        current_streak_days=await _streak_days(session, user, local_date),
        new_words_completed_today=new_completed,
        due_words_completed_today=due_completed,
        total_reviews=event_count,
        sources=StatsSourceBreakdown(
            memory_event_count=event_count,
            heartbeat_seconds=heartbeat_seconds,
            session_count=session_count,
        ),
    )


def _decode_cursor(cursor: str | None) -> datetime | None:
    if not cursor:
        return None
    try:
        return datetime.fromisoformat(cursor)
    except ValueError as exc:
        raise AppError(
            status_code=422,
            code="CURSOR_INVALID",
            message="The pagination cursor is invalid.",
        ) from exc


async def list_events(
    session: AsyncSession,
    user: User,
    *,
    limit: int = 20,
    cursor: str | None = None,
) -> LearningEventListResponse:
    created_before = _decode_cursor(cursor)
    statement = select(MemoryEvent).where(MemoryEvent.user_id == user.id)
    if created_before is not None:
        statement = statement.where(MemoryEvent.created_at < created_before)
    statement = statement.order_by(MemoryEvent.created_at.desc(), MemoryEvent.id.desc()).limit(
        limit + 1
    )
    rows = list((await session.scalars(statement)).all())
    has_more = len(rows) > limit
    visible = rows[:limit]
    items = [
        LearningEventResponse(
            event_id=event.id,
            event_type=event.event_type,
            module=event.module,
            rating=event.rating,
            is_correct=event.is_correct,
            duration_ms=event.duration_ms,
            wordbook_id=event.wordbook_id,
            entry_id=event.entry_id,
            session_id=event.session_id,
            created_at=event.created_at,
        )
        for event in visible
    ]
    next_cursor = visible[-1].created_at.isoformat() if has_more and visible else None
    return LearningEventListResponse(items=items, next_cursor=next_cursor, has_more=has_more)


async def delete_learning_data_for_wordbook(
    session: AsyncSession, wordbook_id: UUID
) -> dict[str, int]:
    plan_ids = list(
        (
            await session.scalars(select(DailyPlan.id).where(DailyPlan.wordbook_id == wordbook_id))
        ).all()
    )
    session_ids = list(
        (
            await session.scalars(
                select(MemorySession.id).where(MemorySession.wordbook_id == wordbook_id)
            )
        ).all()
    )
    event_count = 0
    item_count = 0
    if session_ids:
        event_count = int(
            await session.scalar(
                select(func.count(MemoryEvent.id)).where(MemoryEvent.session_id.in_(session_ids))
            )
            or 0
        )
        item_count = int(
            await session.scalar(
                select(func.count(MemorySessionItem.id)).where(
                    MemorySessionItem.session_id.in_(session_ids)
                )
            )
            or 0
        )
        await session.execute(delete(MemoryEvent).where(MemoryEvent.session_id.in_(session_ids)))
        await session.execute(
            delete(MemorySessionItem).where(MemorySessionItem.session_id.in_(session_ids))
        )
        await session.execute(delete(MemorySession).where(MemorySession.id.in_(session_ids)))
    state_count = int(
        await session.scalar(
            select(func.count(UserWordState.id)).where(UserWordState.wordbook_id == wordbook_id)
        )
        or 0
    )
    await session.execute(delete(UserWordState).where(UserWordState.wordbook_id == wordbook_id))
    mistake_count = int(
        await session.scalar(
            select(func.count(MistakeFlag.id)).where(MistakeFlag.wordbook_id == wordbook_id)
        )
        or 0
    )
    await session.execute(delete(MistakeFlag).where(MistakeFlag.wordbook_id == wordbook_id))
    if plan_ids:
        await session.execute(delete(DailyPlanWord).where(DailyPlanWord.plan_id.in_(plan_ids)))
    await session.execute(delete(DailyPlan).where(DailyPlan.wordbook_id == wordbook_id))
    return {
        "deleted_word_states": state_count,
        "deleted_sessions": len(session_ids),
        "deleted_session_items": item_count,
        "deleted_events": event_count,
        "deleted_mistakes": mistake_count,
        "deleted_plans": len(plan_ids),
    }
