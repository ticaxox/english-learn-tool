"""XP, crumbs, streaks and the three daily quests.

Everything is awarded server-side from actions that already happened (a graded
card, a submitted practice, a completed map node). Each award is stored as an
`xp_events` row keyed by its source, so a retried request or a re-sync cannot pay
twice.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.models.challenge import DailyChallengePlan
from app.models.gamification import DailyQuest, UserGameStats, XpEvent
from app.models.identity import User
from app.models.learning import DailyPlan, DailyPlanWord
from app.models.practice import PracticeSession
from app.schemas.gamification import (
    DailyQuestResponse,
    GamificationProgressResponse,
    GamificationWeeklyResponse,
    LevelProgress,
)
from app.services.auth import utcnow
from app.services.learning import local_date_for

# XP grows with use; crumbs are what the map spends.
AWARDS = {
    "review": (2, 2),
    "practice": (4, 4),
    "challenge_node": (20, 20),
    "boss": (50, 60),
    "quest": (1, 1),
    "daily_first": (10, 10),
}

# A heavy day is capped so grinding easy cards cannot farm the level curve.
DAILY_XP_CAP = 1200
DAILY_CRUMB_CAP = 1200

QUEST_KEYS = ("review_due", "practice_one", "challenge_done")
QUEST_REWARD = {"review_due": 30, "practice_one": 40, "challenge_done": 60}
LEVEL_TITLES = ((1, "拾屑人"), (5, "探路者"), (10, "收集家"), (20, "语言匠"), (35, "说客"))


def xp_for_level(level: int) -> int:
    return 0 if level <= 1 else int(120 * (level**1.35))


def level_for_xp(xp: int) -> int:
    """120 × L^1.35 cumulative: level 2 ≈ 320 XP, level 10 ≈ 2,700 XP."""
    level = 1
    while xp >= xp_for_level(level + 1):
        level += 1
    return level


def title_for_level(level: int) -> str:
    title = LEVEL_TITLES[0][1]
    for threshold, label in LEVEL_TITLES:
        if level >= threshold:
            title = label
    return title


def _quest_targets(user: User) -> dict[str, int]:
    new_words = user.profile.daily_new_words if user.profile is not None else 20
    return {"review_due": max(10, new_words), "practice_one": 1, "challenge_done": 1}


@dataclass
class Award:
    xp: int
    crumbs: int
    level_before: int
    level_after: int
    streak: int


async def _stats(session: AsyncSession, user_id: UUID) -> UserGameStats:
    row = await session.get(UserGameStats, user_id)
    if row is None:
        row = UserGameStats(user_id=user_id)
        session.add(row)
        await session.flush()
    return row


async def _paid_today(session: AsyncSession, user_id: UUID, day: date) -> tuple[int, int]:
    row = (
        await session.execute(
            select(
                func.coalesce(func.sum(XpEvent.xp), 0),
                func.coalesce(func.sum(XpEvent.crumbs), 0),
            ).where(XpEvent.user_id == user_id, XpEvent.day == day)
        )
    ).one()
    return int(row[0]), int(row[1])


def _touch_streak(stats: UserGameStats, day: date) -> None:
    if stats.last_active_day == day:
        return
    if stats.last_active_day is not None and (day - stats.last_active_day).days == 1:
        stats.streak += 1
    else:
        stats.streak = 1
    stats.last_active_day = day
    stats.streak_best = max(stats.streak_best, stats.streak)


async def award(
    session: AsyncSession,
    settings: Settings,
    user: User,
    *,
    source_type: str,
    source_id: str,
    units: int = 1,
) -> Award | None:
    """Grant XP for one action; None when that action was already paid."""
    if source_type not in AWARDS:
        raise ValueError(f"unknown award source: {source_type}")
    per_unit_xp, per_unit_crumbs = AWARDS[source_type]
    day = local_date_for(settings, user)

    already = await session.scalar(
        select(XpEvent.id).where(
            XpEvent.user_id == user.id,
            XpEvent.source_type == source_type,
            XpEvent.source_id == source_id,
        )
    )
    if already is not None:
        return None

    stats = await _stats(session, user.id)
    paid_xp, paid_crumbs = await _paid_today(session, user.id, day)
    xp = max(0, min(per_unit_xp * units, DAILY_XP_CAP - paid_xp))
    crumbs = max(0, min(per_unit_crumbs * units, DAILY_CRUMB_CAP - paid_crumbs))

    level_before = stats.level
    stats.xp += xp
    stats.crumbs += crumbs
    _touch_streak(stats, day)
    stats.level = level_for_xp(stats.xp)
    session.add(
        XpEvent(
            user_id=user.id,
            source_type=source_type,
            source_id=source_id,
            xp=xp,
            crumbs=crumbs,
            day=day,
        )
    )
    await session.flush()
    return Award(
        xp=xp,
        crumbs=crumbs,
        level_before=level_before,
        level_after=stats.level,
        streak=stats.streak,
    )


async def _quest_rows(
    session: AsyncSession, user: User, day: date
) -> dict[str, DailyQuest]:
    targets = _quest_targets(user)
    rows = {
        row.quest_key: row
        for row in (
            await session.scalars(
                select(DailyQuest).where(DailyQuest.user_id == user.id, DailyQuest.day == day)
            )
        ).all()
    }
    for key in QUEST_KEYS:
        if key not in rows:
            row = DailyQuest(user_id=user.id, day=day, quest_key=key, target=targets[key])
            session.add(row)
            rows[key] = row
    await session.flush()
    return rows


async def refresh_quests(
    session: AsyncSession, settings: Settings, user: User
) -> list[DailyQuestResponse]:
    """Recompute today's quests from real activity, then pay newly finished ones."""
    day = local_date_for(settings, user)
    targets = _quest_targets(user)

    reviewed = int(
        await session.scalar(
            select(func.count(DailyPlanWord.id))
            .join(DailyPlan, DailyPlan.id == DailyPlanWord.plan_id)
            .where(
                DailyPlan.user_id == user.id,
                DailyPlan.local_date == day,
                DailyPlanWord.completed_at.is_not(None),
            )
        )
        or 0
    )
    practiced = int(
        await session.scalar(
            select(func.count(PracticeSession.id)).where(
                PracticeSession.user_id == user.id,
                PracticeSession.status == "submitted",
                PracticeSession.submitted_at >= datetime.combine(day, time.min),
            )
        )
        or 0
    )
    challenge = await session.scalar(
        select(DailyChallengePlan).where(
            DailyChallengePlan.user_id == user.id, DailyChallengePlan.local_date == day
        )
    )
    challenge_done = 1 if challenge is not None and challenge.status == "completed" else 0

    progress = {
        "review_due": min(reviewed, targets["review_due"]),
        "practice_one": min(practiced, targets["practice_one"]),
        "challenge_done": min(challenge_done, targets["challenge_done"]),
    }

    rows = await _quest_rows(session, user, day)
    for key in QUEST_KEYS:
        row = rows[key]
        row.progress = max(row.progress, progress[key])
        if row.completed_at is None and row.progress >= row.target:
            row.completed_at = utcnow()
    await session.flush()

    # Paying a quest is itself an award, so it is keyed by day + quest.
    for key in QUEST_KEYS:
        if rows[key].completed_at is None:
            continue
        await award(
            session,
            settings,
            user,
            source_type="quest",
            source_id=f"{day.isoformat()}:{key}",
            units=QUEST_REWARD[key],
        )

    return [
        DailyQuestResponse(
            key=key,
            progress=rows[key].progress,
            target=rows[key].target,
            completed=rows[key].completed_at is not None,
            reward_crumbs=QUEST_REWARD[key],
        )
        for key in QUEST_KEYS
    ]


async def progress(
    session: AsyncSession, settings: Settings, user: User
) -> GamificationProgressResponse:
    day = local_date_for(settings, user)
    stats = await _stats(session, user.id)
    quests = await refresh_quests(session, settings, user)
    current_floor = xp_for_level(stats.level)
    next_floor = xp_for_level(stats.level + 1)
    return GamificationProgressResponse(
        xp=stats.xp,
        crumbs=stats.crumbs,
        level=LevelProgress(
            level=stats.level,
            title=title_for_level(stats.level),
            xp_into_level=stats.xp - current_floor,
            xp_for_next_level=max(1, next_floor - current_floor),
        ),
        streak=stats.streak,
        streak_best=stats.streak_best,
        active_today=stats.last_active_day == day,
        quests=quests,
        local_date=day.isoformat(),
    )


async def weekly(
    session: AsyncSession, settings: Settings, user: User
) -> GamificationWeeklyResponse:
    today = local_date_for(settings, user)
    start = today - timedelta(days=6)
    rows = (
        await session.execute(
            select(XpEvent.day, func.sum(XpEvent.xp), func.sum(XpEvent.crumbs))
            .where(XpEvent.user_id == user.id, XpEvent.day >= start)
            .group_by(XpEvent.day)
        )
    ).all()
    by_day = {row[0]: (int(row[1] or 0), int(row[2] or 0)) for row in rows}
    days = []
    for offset in range(7):
        day = start + timedelta(days=offset)
        xp, crumbs = by_day.get(day, (0, 0))
        days.append(
            {
                "date": day.isoformat(),
                "xp": xp,
                "crumbs": crumbs,
                "active": xp > 0,
            }
        )
    stats = await _stats(session, user.id)
    return GamificationWeeklyResponse(
        days=days,
        xp=sum(entry["xp"] for entry in days),
        active_days=sum(1 for entry in days if entry["active"]),
        streak=stats.streak,
    )
