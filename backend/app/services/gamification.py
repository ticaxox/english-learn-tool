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
from app.models.gamification import (
    DailyQuest,
    UserAchievement,
    UserGameStats,
    XpEvent,
)
from app.models.identity import User
from app.models.learning import DailyPlan, DailyPlanWord, UserWordState
from app.models.practice import PracticeSession
from app.models.wordbooks import (
    WordbookActivation,
    WordbookDefinition,
    WordbookEntry,
)
from app.schemas.gamification import (
    BadgeResponse,
    DailyQuestResponse,
    GamificationProgressResponse,
    GamificationWeeklyResponse,
    LevelProgress,
    RadarAxis,
    WeeklyGoal,
)
from app.services.auth import utcnow
from app.services.learning import local_date_for
from app.services.word_kinds import POS_AXES, normalize_part_of_speech

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


def _month_key(day: date) -> str:
    return f"{day.year:04d}-{day.month:02d}"


def _grant_freeze(stats: UserGameStats, day: date) -> None:
    """One 护身符 per calendar month, topped up the first time the learner shows up."""
    if stats.freeze_granted_month != _month_key(day):
        stats.freeze_tokens = 1
        stats.freeze_granted_month = _month_key(day)


def _touch_streak(stats: UserGameStats, day: date) -> None:
    if stats.last_active_day == day:
        return
    _grant_freeze(stats, day)
    gap = (day - stats.last_active_day).days if stats.last_active_day else None
    if gap == 1:
        stats.streak += 1
    elif gap == 2 and stats.freeze_tokens > 0:
        # One missed day is forgiven; the token is spent and the streak continues.
        stats.freeze_tokens -= 1
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


BADGES: dict[str, tuple[str, str]] = {
    "first_lesson": ("初次拾屑", "完成第一次学习"),
    "streak_3": ("三日不辍", "连续学习 3 天"),
    "streak_7": ("七日连胜", "连续学习 7 天"),
    "streak_30": ("月度坚持", "连续学习 30 天"),
    "level_5": ("探路者", "达到 5 级"),
    "level_10": ("收藏家", "达到 10 级"),
    "practice_10": ("练习成瘾", "累计提交 10 组练习"),
    "practice_50": ("题海老手", "累计提交 50 组练习"),
    "perfect_5": ("全对五连", "五组练习全部答对"),
    "boss_1": ("首胜首领", "首次通过闯关终点"),
    "review_100": ("百词成诵", "累计复习 100 张卡片"),
    "quest_all": ("今日全勤", "一天内完成三条每日任务"),
    "streak_14": ("半月不倒", "连续学习 14 天"),
    "streak_100": ("百日长明", "连续学习 100 天"),
    "level_3": ("初尝甜头", "达到 3 级"),
    "level_20": ("夜行学者", "达到 20 级"),
    "practice_100": ("百炼成钢", "累计提交 100 组练习"),
    "perfect_20": ("全对二十连", "二十组练习全部答对"),
    "boss_10": ("十度远征", "通过十次闯关终点"),
    "review_1000": ("千词之海", "累计复习 1000 张卡片"),
    "first_boss_win": ("破晓者", "首次击败终点守卫"),
    "night_owl": ("夜猫子", "在深夜完成一次学习"),
    "early_bird": ("早起的鸟", "在清晨完成一次学习"),
}


async def _counts(session: AsyncSession, user_id: UUID) -> dict[str, int]:
    practices = int(
        await session.scalar(
            select(func.count(PracticeSession.id)).where(
                PracticeSession.user_id == user_id,
                PracticeSession.status == "submitted",
            )
        )
        or 0
    )
    perfect = int(
        await session.scalar(
            select(func.count(PracticeSession.id)).where(
                PracticeSession.user_id == user_id,
                PracticeSession.status == "submitted",
                PracticeSession.wrong_count == 0,
                PracticeSession.score.is_not(None),
            )
        )
        or 0
    )
    reviews = int(
        await session.scalar(
            select(func.count(XpEvent.id)).where(
                XpEvent.user_id == user_id, XpEvent.source_type == "review"
            )
        )
        or 0
    )
    bosses = int(
        await session.scalar(
            select(func.count(XpEvent.id)).where(
                XpEvent.user_id == user_id, XpEvent.source_type == "boss"
            )
        )
        or 0
    )
    # Two badges are about the hour of day: a night owl studies past midnight,
    # an early bird studies before the school day starts.
    night = int(
        await session.scalar(
            select(func.count(XpEvent.id))
            .where(
                XpEvent.user_id == user_id,
                func.extract("hour", XpEvent.created_at).in_((0, 1, 2, 3, 4, 5)),
            )
        )
        or 0
    )
    early = int(
        await session.scalar(
            select(func.count(XpEvent.id))
            .where(
                XpEvent.user_id == user_id,
                func.extract("hour", XpEvent.created_at).in_((5, 6, 7, 8)),
            )
        )
        or 0
    )
    return {
        "practices": practices,
        "perfect": perfect,
        "reviews": reviews,
        "bosses": bosses,
        "night": night,
        "early": early,
    }


async def evaluate_badges(
    session: AsyncSession, settings: Settings, user: User
) -> list[str]:
    """Unlock any badge whose condition now holds; returns the new keys."""
    stats = await _stats(session, user.id)
    counts = await _counts(session, user.id)
    earned = set(
        (
            await session.scalars(
                select(UserAchievement.badge_key).where(UserAchievement.user_id == user.id)
            )
        ).all()
    )
    day = local_date_for(settings, user)
    quests = {
        row.quest_key: row
        for row in (
            await session.scalars(
                select(DailyQuest).where(DailyQuest.user_id == user.id, DailyQuest.day == day)
            )
        ).all()
    }
    all_quests = len(QUEST_KEYS) == len(quests) and all(
        quests[key].completed_at is not None for key in QUEST_KEYS
    )
    conditions = {
        "first_lesson": stats.xp > 0,
        "streak_3": stats.streak_best >= 3,
        "streak_7": stats.streak_best >= 7,
        "streak_14": stats.streak_best >= 14,
        "streak_30": stats.streak_best >= 30,
        "streak_100": stats.streak_best >= 100,
        "level_3": stats.level >= 3,
        "level_5": stats.level >= 5,
        "level_10": stats.level >= 10,
        "level_20": stats.level >= 20,
        "practice_10": counts["practices"] >= 10,
        "practice_50": counts["practices"] >= 50,
        "practice_100": counts["practices"] >= 100,
        "perfect_5": counts["perfect"] >= 5,
        "perfect_20": counts["perfect"] >= 20,
        "boss_1": counts["bosses"] >= 1,
        "first_boss_win": counts["bosses"] >= 1,
        "boss_10": counts["bosses"] >= 10,
        "review_100": counts["reviews"] >= 100,
        "review_1000": counts["reviews"] >= 1000,
        "quest_all": all_quests,
        "night_owl": counts["night"] >= 1,
        "early_bird": counts["early"] >= 1,
    }
    unlocked: list[str] = []
    for key, ready in conditions.items():
        if ready and key not in earned:
            session.add(UserAchievement(user_id=user.id, badge_key=key))
            unlocked.append(key)
    if unlocked:
        await session.flush()
    return unlocked


async def list_badges(
    session: AsyncSession, user: User
) -> list[BadgeResponse]:
    earned = {
        row.badge_key: row.unlocked_at
        for row in (
            await session.scalars(
                select(UserAchievement).where(UserAchievement.user_id == user.id)
            )
        ).all()
    }
    return [
        BadgeResponse(
            key=key,
            name=name,
            description=description,
            unlocked=key in earned,
            unlocked_at=earned.get(key),
        )
        for key, (name, description) in BADGES.items()
    ]


async def progress(
    session: AsyncSession, settings: Settings, user: User
) -> GamificationProgressResponse:
    day = local_date_for(settings, user)
    stats = await _stats(session, user.id)
    quests = await refresh_quests(session, settings, user)
    await evaluate_badges(session, settings, user)
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
        freeze_tokens=stats.freeze_tokens,
        active_today=stats.last_active_day == day,
        quests=quests,
        local_date=day.isoformat(),
    )


async def _word_kind_radar(
    session: AsyncSession, user: User, start: date
) -> list[RadarAxis]:
    """The shape of the week's word kinds: studied against the book's supply.

    A spoke counts the words of one part of speech the learner touched this
    week, and how many of that kind the active wordbook holds in total. The
    total is the outer edge, so a narrow spike means "you only worked on
    verbs this week" without needing a second chart.
    """
    active = await session.scalar(
        select(WordbookActivation.wordbook_id).where(
            WordbookActivation.user_id == user.id
        )
    )
    if active is None:
        return [RadarAxis(key=key, label=label, studied=0, total=0) for key, label in POS_AXES]

    supply_rows = (
        await session.execute(
            select(WordbookDefinition.part_of_speech, func.count(WordbookDefinition.id))
            .join(WordbookEntry, WordbookEntry.id == WordbookDefinition.entry_id)
            .where(WordbookEntry.wordbook_id == active)
            .group_by(WordbookDefinition.part_of_speech)
        )
    ).all()
    supply: dict[str, int] = {key: 0 for key, _ in POS_AXES}
    for part_of_speech, count in supply_rows:
        family = normalize_part_of_speech(part_of_speech)
        supply[family] = supply.get(family, 0) + int(count or 0)

    since = datetime.combine(start, time.min)
    studied_rows = (
        await session.execute(
            select(WordbookDefinition.part_of_speech, func.count(UserWordState.id))
            .join(UserWordState, UserWordState.entry_id == WordbookDefinition.entry_id)
            .where(
                UserWordState.user_id == user.id,
                UserWordState.last_reviewed_at >= since,
            )
            .group_by(WordbookDefinition.part_of_speech)
        )
    ).all()
    studied: dict[str, int] = {key: 0 for key, _ in POS_AXES}
    for part_of_speech, count in studied_rows:
        family = normalize_part_of_speech(part_of_speech)
        studied[family] = studied.get(family, 0) + int(count or 0)

    return [
        RadarAxis(key=key, label=label, studied=studied.get(key, 0), total=supply.get(key, 0))
        for key, label in POS_AXES
    ]


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
    active_days = sum(1 for entry in days if entry["active"])
    practices = int(
        await session.scalar(
            select(func.count(PracticeSession.id)).where(
                PracticeSession.user_id == user.id,
                PracticeSession.status == "submitted",
                PracticeSession.submitted_at >= datetime.combine(start, time.min),
            )
        )
        or 0
    )
    challenges = int(
        await session.scalar(
            select(func.count(DailyChallengePlan.id)).where(
                DailyChallengePlan.user_id == user.id,
                DailyChallengePlan.local_date >= start,
                DailyChallengePlan.status == "completed",
            )
        )
        or 0
    )
    def _goal(key: str, label: str, progress: int) -> WeeklyGoal:
        return WeeklyGoal(
            key=key, label=label, progress=progress, target=5, completed=progress >= 5
        )

    goals = [
        _goal("active_days", "本周学习 5 天", active_days),
        _goal("practices", "本周完成 5 组练习", practices),
        _goal("challenges", "本周通关 5 次", challenges),
    ]
    return GamificationWeeklyResponse(
        days=days,
        xp=sum(entry["xp"] for entry in days),
        active_days=active_days,
        radar=await _word_kind_radar(session, user, start),
        streak=stats.streak,
        goals=goals,
    )
