from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta

from redis.asyncio import Redis
from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.errors import AppError
from app.models.ai import AiJob, AiUsageLedger
from app.models.identity import User
from app.schemas.ai import (
    AdminAiUsageResponse,
    AdminProviderAggregate,
    AdminQuotaAggregate,
    AdminTaskAggregate,
    AiUserUsageResponse,
    ConcurrencyUsage,
    DailyQuotaUsage,
)
from app.services.ai_concurrency import concurrency_in_use
from app.services.auth import utcnow
from app.services.learning import local_date_for
from app.services.users import require_admin

QUOTA_KINDS = ("coach_messages", "question_generation", "subjective_grading")


def quota_limits(settings: Settings) -> dict[str, int]:
    return {
        "coach_messages": settings.ai_daily_coach_messages,
        "question_generation": settings.ai_daily_question_generation,
        "subjective_grading": settings.ai_daily_subjective_grading,
    }


async def user_usage(
    session: AsyncSession,
    redis: Redis,
    user: User,
    settings: Settings,
    *,
    local_date: date | None = None,
) -> AiUserUsageResponse:
    target_date = local_date or local_date_for(settings, user, now=utcnow())
    limits = quota_limits(settings)
    rows = (
        await session.execute(
            select(
                AiUsageLedger.quota_kind,
                func.coalesce(func.sum(AiUsageLedger.consumed), 0),
                func.coalesce(
                    func.sum(
                        case(
                            (AiUsageLedger.status == "reserved", AiUsageLedger.reserved),
                            else_=0,
                        )
                    ),
                    0,
                ),
            )
            .where(
                AiUsageLedger.user_id == user.id,
                AiUsageLedger.local_date == target_date,
            )
            .group_by(AiUsageLedger.quota_kind)
        )
    ).all()
    values = {row[0]: (int(row[1]), int(row[2])) for row in rows}
    quotas = []
    for kind in QUOTA_KINDS:
        used, reserved = values.get(kind, (0, 0))
        limit = limits[kind]
        quotas.append(
            DailyQuotaUsage(
                quota_kind=kind,
                limit=limit,
                used=used,
                reserved=reserved,
                remaining=max(limit - used - reserved, 0),
            )
        )
    return AiUserUsageResponse(
        local_date=target_date,
        quotas=quotas,
        concurrency=ConcurrencyUsage(
            limit=settings.ai_concurrency_limit,
            in_use=await concurrency_in_use(redis, user_id=user.id),
        ),
    )


async def admin_usage(
    session: AsyncSession,
    actor: User,
    settings: Settings,
    *,
    date_from: date | None = None,
    date_to: date | None = None,
) -> AdminAiUsageResponse:
    require_admin(actor)
    today = utcnow().date()
    start = date_from or today - timedelta(days=6)
    end = date_to or today
    if end < start or (end - start).days > 366:
        raise AppError(
            status_code=422,
            code="AI_USAGE_DATE_RANGE_INVALID",
            message="The usage date range is invalid.",
        )
    start_at = datetime.combine(start, time.min, tzinfo=UTC)
    end_at = datetime.combine(end + timedelta(days=1), time.min, tzinfo=UTC)
    job_filters = (AiJob.created_at >= start_at, AiJob.created_at < end_at)
    total_jobs = int(await session.scalar(select(func.count(AiJob.id)).where(*job_filters)) or 0)
    active_jobs = int(
        await session.scalar(
            select(func.count(AiJob.id)).where(
                *job_filters,
                AiJob.status.in_(("queued", "running")),
            )
        )
        or 0
    )
    task_rows = (
        await session.execute(
            select(AiJob.task_type, AiJob.status, func.count(AiJob.id))
            .where(*job_filters)
            .group_by(AiJob.task_type, AiJob.status)
            .order_by(AiJob.task_type, AiJob.status)
        )
    ).all()
    provider_rows = (
        await session.execute(
            select(
                AiJob.provider_id,
                func.coalesce(AiJob.provider_name, "unassigned"),
                func.count(AiJob.id),
                func.coalesce(func.sum(case((AiJob.status == "succeeded", 1), else_=0)), 0),
                func.coalesce(func.sum(case((AiJob.status == "failed", 1), else_=0)), 0),
            )
            .where(*job_filters)
            .group_by(AiJob.provider_id, AiJob.provider_name)
            .order_by(func.coalesce(AiJob.provider_name, "unassigned"))
        )
    ).all()
    quota_rows = (
        await session.execute(
            select(
                AiUsageLedger.quota_kind,
                func.count(func.distinct(AiUsageLedger.user_id)),
                func.coalesce(func.sum(AiUsageLedger.consumed), 0),
                func.coalesce(
                    func.sum(
                        case(
                            (AiUsageLedger.status == "reserved", AiUsageLedger.reserved),
                            else_=0,
                        )
                    ),
                    0,
                ),
                func.coalesce(func.sum(AiUsageLedger.released), 0),
            )
            .where(AiUsageLedger.local_date.between(start, end))
            .group_by(AiUsageLedger.quota_kind)
        )
    ).all()
    limits = quota_limits(settings)
    quota_values = {row[0]: row[1:] for row in quota_rows}
    return AdminAiUsageResponse(
        date_from=start,
        date_to=end,
        total_jobs=total_jobs,
        active_jobs=active_jobs,
        tasks=[
            AdminTaskAggregate(task_type=row[0], status=row[1], count=int(row[2]))
            for row in task_rows
        ],
        providers=[
            AdminProviderAggregate(
                provider_id=row[0],
                provider_name=row[1],
                jobs=int(row[2]),
                succeeded=int(row[3]),
                failed=int(row[4]),
            )
            for row in provider_rows
        ],
        quotas=[
            AdminQuotaAggregate(
                quota_kind=kind,
                limit_per_user=limits[kind],
                users_with_usage=int(quota_values.get(kind, (0, 0, 0, 0))[0]),
                consumed=int(quota_values.get(kind, (0, 0, 0, 0))[1]),
                reserved=int(quota_values.get(kind, (0, 0, 0, 0))[2]),
                released=int(quota_values.get(kind, (0, 0, 0, 0))[3]),
            )
            for kind in QUOTA_KINDS
        ],
    )
