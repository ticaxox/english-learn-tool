from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, time, timedelta
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.errors import AppError
from app.models.ai import AiJob, AiUsageLedger
from app.models.challenge import DailyChallengePlan
from app.models.identity import User, UserProfile
from app.models.learning import DailyActivity, DailyPlan, DailyPlanWord, MemoryEvent, MistakeFlag
from app.models.practice import PracticeSubmission
from app.schemas.dashboard import (
    AdminDashboardResponse,
    DashboardFilters,
    DashboardGroupRow,
    DashboardMetrics,
    DashboardPrivacy,
    DashboardQuotaUsage,
    DashboardRiskHints,
    DashboardTrendPoint,
)
from app.services.auth import utcnow
from app.services.users import require_admin

DASHBOARD_VERSION = "dashboard-v1"
MINIMUM_GROUP_SIZE = 3
MAX_RANGE_DAYS = 90


def _local_date(value: datetime, timezone: str) -> date:
    return value.astimezone(ZoneInfo(timezone)).date()


def _date_range(
    settings: Settings, date_from: date | None, date_to: date | None
) -> tuple[date, date]:
    today = utcnow().astimezone(ZoneInfo(settings.app_timezone)).date()
    resolved_to = date_to or today
    resolved_from = date_from or (resolved_to - timedelta(days=6))
    if resolved_from > resolved_to:
        raise AppError(
            status_code=422,
            code="DASHBOARD_DATE_RANGE_INVALID",
            message="date_from must be on or before date_to.",
        )
    if (resolved_to - resolved_from).days > MAX_RANGE_DAYS:
        raise AppError(
            status_code=422,
            code="DASHBOARD_DATE_RANGE_TOO_LARGE",
            message=f"Dashboard ranges are limited to {MAX_RANGE_DAYS} days.",
        )
    return resolved_from, resolved_to


def _utc_bounds(date_from: date, date_to: date, timezone: str) -> tuple[datetime, datetime]:
    zone = ZoneInfo(timezone)
    start = datetime.combine(date_from, time.min, tzinfo=zone).astimezone(ZoneInfo("UTC"))
    end = datetime.combine(date_to + timedelta(days=1), time.min, tzinfo=zone).astimezone(
        ZoneInfo("UTC")
    )
    return start, end


def _rate(numerator: int, denominator: int) -> float | None:
    return round(numerator / denominator, 4) if denominator else None


def _days_between(date_from: date, date_to: date) -> list[date]:
    return [date_from + timedelta(days=index) for index in range((date_to - date_from).days + 1)]


def _empty_user_metrics() -> dict[str, int]:
    return {
        "active_days": 0,
        "study_seconds": 0,
        "plans_total": 0,
        "plans_completed": 0,
        "new_words_completed": 0,
        "due_words_completed": 0,
        "practice_submissions": 0,
        "practice_correct": 0,
        "practice_total": 0,
        "mistake_flags": 0,
        "high_priority_mistakes": 0,
        "memory_events": 0,
        "ai_jobs": 0,
        "ai_failed": 0,
        "challenges_completed": 0,
    }


def _sum_metrics(items: list[dict[str, int]]) -> dict[str, int]:
    total = _empty_user_metrics()
    for item in items:
        for key, value in item.items():
            total[key] += value
    return total


async def get_admin_dashboard(
    session: AsyncSession,
    admin: User,
    settings: Settings,
    *,
    date_from: date | None = None,
    date_to: date | None = None,
    department: str | None = None,
    learning_group: str | None = None,
    page: int = 1,
    page_size: int = 10,
) -> AdminDashboardResponse:
    require_admin(admin)
    resolved_from, resolved_to = _date_range(settings, date_from, date_to)
    department = department.strip() if department and department.strip() else None
    learning_group = learning_group.strip() if learning_group and learning_group.strip() else None
    timezone = settings.app_timezone
    start_utc, end_utc = _utc_bounds(resolved_from, resolved_to, timezone)

    member_statement = (
        select(User.id, UserProfile.department, UserProfile.learning_group)
        .outerjoin(UserProfile, UserProfile.user_id == User.id)
        .where(User.role == "member", User.status == "active")
    )
    if department is not None:
        member_statement = member_statement.where(UserProfile.department == department)
    if learning_group is not None:
        member_statement = member_statement.where(UserProfile.learning_group == learning_group)
    member_rows = (await session.execute(member_statement)).all()
    members = {
        row.id: {"department": row.department, "learning_group": row.learning_group}
        for row in member_rows
    }
    user_ids = list(members)
    filters = DashboardFilters(
        date_from=resolved_from,
        date_to=resolved_to,
        department=department,
        learning_group=learning_group,
        timezone=timezone,
    )
    if not user_ids:
        return AdminDashboardResponse(
            generated_at=utcnow(),
            calculation_version=DASHBOARD_VERSION,
            filters=filters,
            privacy=DashboardPrivacy(
                suppressed=True,
                minimum_group_size=MINIMUM_GROUP_SIZE,
                reason="aggregate sample below minimum size",
            ),
            metrics=DashboardMetrics(total_members=0),
        )

    user_metrics = {user_id: _empty_user_metrics() for user_id in user_ids}
    activity_days: dict[UUID, set[date]] = defaultdict(set)
    trend = {
        day: {
            "active_users": set(),
            "study_seconds": 0,
            "plans_completed": 0,
            "practice_submissions": 0,
            "practice_correct": 0,
            "practice_total": 0,
            "mistakes": 0,
            "memory_events": 0,
            "ai_jobs": 0,
            "ai_failed": 0,
            "challenges_completed": 0,
        }
        for day in _days_between(resolved_from, resolved_to)
    }

    activity_rows = (
        await session.execute(
            select(
                DailyActivity.user_id,
                DailyActivity.local_date,
                DailyActivity.active_seconds,
            ).where(
                DailyActivity.user_id.in_(user_ids),
                DailyActivity.local_date.between(resolved_from, resolved_to),
            )
        )
    ).all()
    for row in activity_rows:
        if row.user_id not in user_metrics or row.active_seconds <= 0:
            continue
        user_metrics[row.user_id]["active_days"] += 1
        user_metrics[row.user_id]["study_seconds"] += row.active_seconds
        activity_days[row.user_id].add(row.local_date)
        trend[row.local_date]["active_users"].add(row.user_id)
        trend[row.local_date]["study_seconds"] += row.active_seconds

    plan_rows = (
        await session.execute(
            select(DailyPlan.user_id, DailyPlan.local_date, DailyPlan.status).where(
                DailyPlan.user_id.in_(user_ids),
                DailyPlan.local_date.between(resolved_from, resolved_to),
            )
        )
    ).all()
    for row in plan_rows:
        if row.user_id not in user_metrics:
            continue
        user_metrics[row.user_id]["plans_total"] += 1
        if row.status == "completed":
            user_metrics[row.user_id]["plans_completed"] += 1
            trend[row.local_date]["plans_completed"] += 1

    word_rows = (
        await session.execute(
            select(DailyPlan.user_id, DailyPlanWord.reason, DailyPlanWord.completed_at)
            .join(DailyPlan, DailyPlan.id == DailyPlanWord.plan_id)
            .where(
                DailyPlan.user_id.in_(user_ids),
                DailyPlan.local_date.between(resolved_from, resolved_to),
                DailyPlanWord.completed_at.is_not(None),
            )
        )
    ).all()
    for row in word_rows:
        if row.user_id not in user_metrics:
            continue
        if row.reason == "new":
            user_metrics[row.user_id]["new_words_completed"] += 1
        elif row.reason == "due":
            user_metrics[row.user_id]["due_words_completed"] += 1

    practice_rows = (
        await session.execute(
            select(
                PracticeSubmission.user_id,
                PracticeSubmission.created_at,
                PracticeSubmission.correct_count,
                PracticeSubmission.total_questions,
            ).where(
                PracticeSubmission.user_id.in_(user_ids),
                PracticeSubmission.status == "completed",
                PracticeSubmission.created_at >= start_utc,
                PracticeSubmission.created_at < end_utc,
            )
        )
    ).all()
    for row in practice_rows:
        if row.user_id not in user_metrics:
            continue
        day = _local_date(row.created_at, timezone)
        user_metrics[row.user_id]["practice_submissions"] += 1
        user_metrics[row.user_id]["practice_correct"] += row.correct_count
        user_metrics[row.user_id]["practice_total"] += row.total_questions
        if day in trend:
            trend[day]["practice_submissions"] += 1
            trend[day]["practice_correct"] += row.correct_count
            trend[day]["practice_total"] += row.total_questions

    mistake_rows = (
        await session.execute(
            select(MistakeFlag.user_id, MistakeFlag.last_again_at, MistakeFlag.is_priority).where(
                MistakeFlag.user_id.in_(user_ids),
                MistakeFlag.last_again_at >= start_utc,
                MistakeFlag.last_again_at < end_utc,
            )
        )
    ).all()
    for row in mistake_rows:
        if row.user_id not in user_metrics:
            continue
        user_metrics[row.user_id]["mistake_flags"] += 1
        if row.is_priority:
            user_metrics[row.user_id]["high_priority_mistakes"] += 1
        day = _local_date(row.last_again_at, timezone)
        if day in trend:
            trend[day]["mistakes"] += 1

    memory_rows = (
        await session.execute(
            select(MemoryEvent.user_id, MemoryEvent.created_at).where(
                MemoryEvent.user_id.in_(user_ids),
                MemoryEvent.created_at >= start_utc,
                MemoryEvent.created_at < end_utc,
            )
        )
    ).all()
    for row in memory_rows:
        if row.user_id not in user_metrics:
            continue
        user_metrics[row.user_id]["memory_events"] += 1
        day = _local_date(row.created_at, timezone)
        if day in trend:
            trend[day]["memory_events"] += 1

    ai_rows = (
        await session.execute(
            select(AiJob.user_id, AiJob.created_at, AiJob.status).where(
                AiJob.user_id.in_(user_ids),
                AiJob.created_at >= start_utc,
                AiJob.created_at < end_utc,
            )
        )
    ).all()
    for row in ai_rows:
        if row.user_id not in user_metrics:
            continue
        user_metrics[row.user_id]["ai_jobs"] += 1
        failed = row.status in {"failed", "stale"}
        if failed:
            user_metrics[row.user_id]["ai_failed"] += 1
        day = _local_date(row.created_at, timezone)
        if day in trend:
            trend[day]["ai_jobs"] += 1
            if failed:
                trend[day]["ai_failed"] += 1

    quota_rows = (
        await session.execute(
            select(
                AiUsageLedger.quota_kind,
                AiUsageLedger.consumed,
                AiUsageLedger.reserved,
                AiUsageLedger.released,
            ).where(
                AiUsageLedger.user_id.in_(user_ids),
                AiUsageLedger.local_date.between(resolved_from, resolved_to),
            )
        )
    ).all()
    quota_totals: dict[str, dict[str, int]] = {
        "coach_messages": {"consumed": 0, "reserved": 0, "released": 0},
        "question_generation": {"consumed": 0, "reserved": 0, "released": 0},
        "subjective_grading": {"consumed": 0, "reserved": 0, "released": 0},
    }
    for row in quota_rows:
        quota_totals[row.quota_kind]["consumed"] += row.consumed
        quota_totals[row.quota_kind]["reserved"] += row.reserved
        quota_totals[row.quota_kind]["released"] += row.released

    challenge_rows = (
        await session.execute(
            select(
                DailyChallengePlan.user_id,
                DailyChallengePlan.local_date,
                DailyChallengePlan.status,
            ).where(
                DailyChallengePlan.user_id.in_(user_ids),
                DailyChallengePlan.local_date.between(resolved_from, resolved_to),
            )
        )
    ).all()
    for row in challenge_rows:
        if row.user_id not in user_metrics:
            continue
        if row.status == "completed":
            user_metrics[row.user_id]["challenges_completed"] += 1
            if row.local_date in trend:
                trend[row.local_date]["challenges_completed"] += 1

    history_start = resolved_to - timedelta(days=29)
    history_rows = (
        await session.execute(
            select(DailyActivity.user_id, DailyActivity.local_date).where(
                DailyActivity.user_id.in_(user_ids),
                DailyActivity.local_date.between(history_start, resolved_to),
                DailyActivity.active_seconds > 0,
            )
        )
    ).all()
    history_days: dict[UUID, set[date]] = defaultdict(set)
    for row in history_rows:
        history_days[row.user_id].add(row.local_date)

    streaks: dict[UUID, int] = {}
    for user_id in user_ids:
        active_dates = history_days.get(user_id, set())
        if not active_dates:
            streaks[user_id] = 0
            continue
        cursor = max(active_dates)
        streak = 0
        while cursor in active_dates:
            streak += 1
            cursor -= timedelta(days=1)
        streaks[user_id] = streak

    total_metrics = _sum_metrics(list(user_metrics.values()))
    active_users = {
        user_id for user_id, metrics in user_metrics.items() if metrics["active_days"] > 0
    }
    practice_total = total_metrics["practice_total"]
    ai_total = total_metrics["ai_jobs"]
    suppressed = len(user_ids) < MINIMUM_GROUP_SIZE
    privacy = DashboardPrivacy(
        suppressed=suppressed,
        minimum_group_size=MINIMUM_GROUP_SIZE,
        reason="aggregate sample below minimum size" if suppressed else None,
    )
    if suppressed:
        return AdminDashboardResponse(
            generated_at=utcnow(),
            calculation_version=DASHBOARD_VERSION,
            filters=filters,
            privacy=privacy,
            metrics=DashboardMetrics(total_members=len(user_ids)),
            group_page=page,
            group_page_size=page_size,
            suppressed_group_count=1 if user_ids else 0,
        )

    metrics = DashboardMetrics(
        total_members=len(user_ids),
        active_members=len(active_users),
        active_member_rate=_rate(len(active_users), len(user_ids)),
        study_minutes=round(total_metrics["study_seconds"] / 60, 2),
        plans_total=total_metrics["plans_total"],
        plans_completed=total_metrics["plans_completed"],
        task_completion_rate=_rate(total_metrics["plans_completed"], total_metrics["plans_total"]),
        new_words_completed=total_metrics["new_words_completed"],
        due_words_completed=total_metrics["due_words_completed"],
        practice_submissions=total_metrics["practice_submissions"],
        practice_correct_rate=_rate(total_metrics["practice_correct"], practice_total),
        mistake_flags=total_metrics["mistake_flags"],
        high_priority_mistakes=total_metrics["high_priority_mistakes"],
        memory_events=total_metrics["memory_events"],
        average_current_streak_days=round(sum(streaks.values()) / len(streaks), 2)
        if streaks
        else 0,
        members_with_streak_7d=sum(1 for value in streaks.values() if value >= 7),
        ai_jobs=ai_total,
        ai_failed=total_metrics["ai_failed"],
        ai_failure_rate=_rate(total_metrics["ai_failed"], ai_total),
        challenges_completed=total_metrics["challenges_completed"],
    )
    trend_points = [
        DashboardTrendPoint(
            local_date=day,
            active_members=len(data["active_users"]),
            study_minutes=round(data["study_seconds"] / 60, 2),
            plans_completed=data["plans_completed"],
            practice_submissions=data["practice_submissions"],
            practice_correct_rate=_rate(data["practice_correct"], data["practice_total"]),
            mistakes=data["mistakes"],
            memory_events=data["memory_events"],
            ai_jobs=data["ai_jobs"],
            ai_failed=data["ai_failed"],
            challenges_completed=data["challenges_completed"],
        )
        for day, data in sorted(trend.items())
    ]

    group_members: dict[tuple[str | None, str | None], list[UUID]] = defaultdict(list)
    for user_id, member in members.items():
        group_members[(member["department"], member["learning_group"])].append(user_id)
    group_rows: list[DashboardGroupRow] = []
    suppressed_group_count = 0
    for (group_department, group_name), ids in group_members.items():
        if len(ids) < MINIMUM_GROUP_SIZE:
            suppressed_group_count += 1
            continue
        aggregate = _sum_metrics([user_metrics[user_id] for user_id in ids])
        group_active = sum(1 for user_id in ids if user_metrics[user_id]["active_days"] > 0)
        group_rows.append(
            DashboardGroupRow(
                department=group_department,
                learning_group=group_name,
                member_count=len(ids),
                active_members=group_active,
                study_minutes=round(aggregate["study_seconds"] / 60, 2),
                task_completion_rate=_rate(aggregate["plans_completed"], aggregate["plans_total"]),
                practice_correct_rate=_rate(
                    aggregate["practice_correct"], aggregate["practice_total"]
                ),
                mistake_flags=aggregate["mistake_flags"],
                ai_failure_rate=_rate(aggregate["ai_failed"], aggregate["ai_jobs"]),
            )
        )
    group_rows.sort(key=lambda row: (row.department or "", row.learning_group or ""))
    group_start = (page - 1) * page_size
    paged_groups = group_rows[group_start : group_start + page_size]
    quota_usage = [
        DashboardQuotaUsage(
            quota_kind=kind,
            consumed=values["consumed"],
            reserved=values["reserved"],
            released=values["released"],
        )
        for kind, values in sorted(quota_totals.items())
    ]
    inactive_members_3d = 0
    for user_id in user_ids:
        if not any(
            resolved_to - timedelta(days=offset) in history_days.get(user_id, set())
            for offset in range(3)
        ):
            inactive_members_3d += 1
    high_mistake_members = sum(
        1 for metrics_for_user in user_metrics.values() if metrics_for_user["mistake_flags"] >= 5
    )
    ai_failure_rate = metrics.ai_failure_rate
    risk_hints = DashboardRiskHints(
        inactive_members_3d=inactive_members_3d,
        high_mistake_members=high_mistake_members,
        ai_failure_alert=bool(ai_failure_rate is not None and ai_failure_rate >= 0.2),
    )
    return AdminDashboardResponse(
        generated_at=utcnow(),
        calculation_version=DASHBOARD_VERSION,
        filters=filters,
        privacy=privacy,
        metrics=metrics,
        trend=trend_points,
        groups=paged_groups,
        group_page=page,
        group_page_size=page_size,
        group_has_more=len(group_rows) > group_start + page_size,
        suppressed_group_count=suppressed_group_count,
        quota_usage=quota_usage,
        risk_hints=risk_hints,
    )
