from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class LevelProgress(BaseModel):
    level: int
    title: str
    xp_into_level: int
    xp_for_next_level: int


class DailyQuestResponse(BaseModel):
    key: str
    progress: int
    target: int
    completed: bool
    reward_crumbs: int


class GamificationProgressResponse(BaseModel):
    xp: int
    crumbs: int
    level: LevelProgress
    streak: int
    streak_best: int
    freeze_tokens: int = 0
    active_today: bool
    quests: list[DailyQuestResponse]
    local_date: str


class WeeklyDay(BaseModel):
    date: str
    xp: int
    crumbs: int
    active: bool


class WeeklyGoal(BaseModel):
    key: str
    label: str
    progress: int
    target: int
    completed: bool


class RadarAxis(BaseModel):
    """One spoke of the weekly radar: a word kind and how much of it was studied."""

    key: str
    label: str
    studied: int
    total: int


class GamificationWeeklyResponse(BaseModel):
    days: list[WeeklyDay]
    xp: int
    active_days: int
    streak: int
    goals: list[WeeklyGoal] = []
    # The word-kind shape of the week: how many words of each part of speech
    # the learner touched, against how many the wordbook holds.
    radar: list[RadarAxis] = []


class FootprintDay(BaseModel):
    date: str
    xp: int
    active: bool


class WordStateCounts(BaseModel):
    """Where the learner's words sit in the memory curve right now.

    A mastered word has left the schedule on purpose, so it is reported with
    the words under review rather than as a fifth bucket.
    """

    new: int = 0
    learning: int = 0
    review: int = 0
    relearning: int = 0
    total: int = 0


class GamificationFootprintResponse(BaseModel):
    """The calendar month so far, plus the shape of everything being learned."""

    month: str
    days: list[FootprintDay] = []
    active_days: int = 0
    streak: int = 0
    states: WordStateCounts


class AwardResponse(BaseModel):
    """Returned alongside the action that earned it, so the UI can animate."""

    xp: int
    crumbs: int
    level_before: int
    level_after: int
    streak: int
    leveled_up: bool


class BadgeResponse(BaseModel):
    key: str
    name: str
    description: str
    unlocked: bool
    unlocked_at: datetime | None = None


class BadgeListResponse(BaseModel):
    items: list[BadgeResponse]
