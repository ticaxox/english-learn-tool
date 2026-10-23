from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field

AiQuotaKind = Literal["coach_messages", "question_generation", "subjective_grading"]


class DashboardFilters(BaseModel):
    date_from: date
    date_to: date
    department: str | None = None
    learning_group: str | None = None
    timezone: str


class DashboardPrivacy(BaseModel):
    suppressed: bool
    minimum_group_size: int = 3
    reason: str | None = None


class DashboardMetrics(BaseModel):
    total_members: int
    active_members: int | None = None
    active_member_rate: float | None = None
    study_minutes: float | None = None
    plans_total: int | None = None
    plans_completed: int | None = None
    task_completion_rate: float | None = None
    new_words_completed: int | None = None
    due_words_completed: int | None = None
    practice_submissions: int | None = None
    practice_correct_rate: float | None = None
    mistake_flags: int | None = None
    high_priority_mistakes: int | None = None
    memory_events: int | None = None
    average_current_streak_days: float | None = None
    members_with_streak_7d: int | None = None
    ai_jobs: int | None = None
    ai_failed: int | None = None
    ai_failure_rate: float | None = None
    challenges_completed: int | None = None


class DashboardTrendPoint(BaseModel):
    local_date: date
    active_members: int | None = None
    study_minutes: float | None = None
    plans_completed: int | None = None
    practice_submissions: int | None = None
    practice_correct_rate: float | None = None
    mistakes: int | None = None
    memory_events: int | None = None
    ai_jobs: int | None = None
    ai_failed: int | None = None
    challenges_completed: int | None = None


class DashboardGroupRow(BaseModel):
    department: str | None = None
    learning_group: str | None = None
    member_count: int
    active_members: int | None = None
    study_minutes: float | None = None
    task_completion_rate: float | None = None
    practice_correct_rate: float | None = None
    mistake_flags: int | None = None
    ai_failure_rate: float | None = None


class DashboardQuotaUsage(BaseModel):
    quota_kind: AiQuotaKind
    consumed: int
    reserved: int
    released: int


class DashboardRiskHints(BaseModel):
    inactive_members_3d: int | None = None
    high_mistake_members: int | None = None
    ai_failure_alert: bool | None = None


class AdminDashboardResponse(BaseModel):
    generated_at: datetime
    calculation_version: str
    filters: DashboardFilters
    privacy: DashboardPrivacy
    metrics: DashboardMetrics
    trend: list[DashboardTrendPoint] = Field(default_factory=list)
    groups: list[DashboardGroupRow] = Field(default_factory=list)
    group_page: int = 1
    group_page_size: int = 10
    group_has_more: bool = False
    suppressed_group_count: int = 0
    quota_usage: list[DashboardQuotaUsage] = Field(default_factory=list)
    risk_hints: DashboardRiskHints = Field(default_factory=DashboardRiskHints)
