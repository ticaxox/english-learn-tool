from __future__ import annotations

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
    active_today: bool
    quests: list[DailyQuestResponse]
    local_date: str


class WeeklyDay(BaseModel):
    date: str
    xp: int
    crumbs: int
    active: bool


class GamificationWeeklyResponse(BaseModel):
    days: list[WeeklyDay]
    xp: int
    active_days: int
    streak: int


class AwardResponse(BaseModel):
    """Returned alongside the action that earned it, so the UI can animate."""

    xp: int
    crumbs: int
    level_before: int
    level_after: int
    streak: int
    leveled_up: bool
