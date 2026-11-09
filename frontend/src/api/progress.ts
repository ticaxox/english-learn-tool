/** XP, level, streak and today's quests. */

import { apiClient } from './client'

export interface LevelProgress {
  level: number
  title: string
  xpIntoLevel: number
  xpForNextLevel: number
}

export interface DailyQuest {
  key: string
  progress: number
  target: number
  completed: boolean
  rewardCrumbs: number
}

export interface GamificationProgress {
  xp: number
  crumbs: number
  level: LevelProgress
  streak: number
  streakBest: number
  activeToday: boolean
  quests: DailyQuest[]
  localDate: string
}

export interface WeeklyDay {
  date: string
  xp: number
  crumbs: number
  active: boolean
}

export interface GamificationWeekly {
  days: WeeklyDay[]
  xp: number
  activeDays: number
  streak: number
}

export const QUEST_LABELS: Record<string, string> = {
  review_due: '清空今日到期',
  practice_one: '做一组练习',
  challenge_done: '完成今日闯关',
}

function record(value: unknown, context: string): Record<string, unknown> {
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    throw new Error(`${context} 格式不正确。`)
  }
  return value as Record<string, unknown>
}

function num(value: unknown, fallback = 0): number {
  return typeof value === 'number' && Number.isFinite(value) ? value : fallback
}

function parseQuest(value: unknown): DailyQuest {
  const body = record(value, '每日任务')
  return {
    key: String(body.key ?? ''),
    progress: num(body.progress),
    target: num(body.target, 1),
    completed: body.completed === true,
    rewardCrumbs: num(body.reward_crumbs),
  }
}

export function parseProgress(value: unknown): GamificationProgress {
  const body = record(value, '学习进度')
  const level = record(body.level, '等级')
  return {
    xp: num(body.xp),
    crumbs: num(body.crumbs),
    level: {
      level: num(level.level, 1),
      title: String(level.title ?? ''),
      xpIntoLevel: num(level.xp_into_level),
      xpForNextLevel: Math.max(1, num(level.xp_for_next_level, 1)),
    },
    streak: num(body.streak),
    streakBest: num(body.streak_best),
    activeToday: body.active_today === true,
    quests: Array.isArray(body.quests) ? body.quests.map(parseQuest) : [],
    localDate: String(body.local_date ?? ''),
  }
}

export function parseWeekly(value: unknown): GamificationWeekly {
  const body = record(value, '周报')
  const days = Array.isArray(body.days) ? body.days.map((item) => record(item, '周报日')) : []
  return {
    days: days.map((day) => ({
      date: String(day.date ?? ''),
      xp: num(day.xp),
      crumbs: num(day.crumbs),
      active: day.active === true,
    })),
    xp: num(body.xp),
    activeDays: num(body.active_days),
    streak: num(body.streak),
  }
}

export async function fetchProgress(): Promise<GamificationProgress> {
  return parseProgress(await apiClient.get('/me/progress'))
}

export async function fetchWeekly(): Promise<GamificationWeekly> {
  return parseWeekly(await apiClient.get('/me/progress/weekly'))
}
