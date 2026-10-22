/**
 * Pure frontend validation for T-FE-004 forms.
 *
 * These checks are UX affordances only: the server is the final authority on
 * ranges, dates and eligibility. Nothing here decides learning state.
 */
import {
  DAILY_MINUTES_MAX,
  DAILY_MINUTES_MIN,
  DAILY_NEW_WORDS_MAX,
  DAILY_NEW_WORDS_MIN,
  EXAM_TARGETS,
  MEMORY_MODULES,
  type ExamTarget,
  type LearningProfileUpdate,
  type MemoryConfig,
  type MemoryModule,
  type SpellingBlankType,
} from '../types/learning'

// Re-exported so callers get ranges and validators from one import.
export {
  DAILY_MINUTES_MAX,
  DAILY_MINUTES_MIN,
  DAILY_NEW_WORDS_MAX,
  DAILY_NEW_WORDS_MIN,
  DAILY_MINUTES_DEFAULT,
  DAILY_NEW_WORDS_DEFAULT,
} from '../types/learning'

export type FieldErrors = Record<string, string>

const DATE_PATTERN = /^\d{4}-\d{2}-\d{2}$/

/** Today's local calendar date as `YYYY-MM-DD` (no timezone shifting). */
export function todayIsoDate(now: Date = new Date()): string {
  const year = now.getFullYear()
  const month = String(now.getMonth() + 1).padStart(2, '0')
  const day = String(now.getDate()).padStart(2, '0')
  return `${year}-${month}-${day}`
}

export function validateExamDate(value: string | null, today: string = todayIsoDate()): string | null {
  if (value === null || value.trim() === '') {
    return null
  }
  if (!DATE_PATTERN.test(value) || Number.isNaN(Date.parse(`${value}T00:00:00`))) {
    return '考试日期需为 YYYY-MM-DD 格式的有效日期。'
  }
  if (value <= today) {
    return '考试日期必须晚于今天；留空表示暂不设置。'
  }
  return null
}

export function validateDailyNewWords(value: number): string | null {
  if (!Number.isInteger(value)) {
    return '每日新词量需为整数。'
  }
  if (value < DAILY_NEW_WORDS_MIN || value > DAILY_NEW_WORDS_MAX) {
    return `每日新词量需在 ${DAILY_NEW_WORDS_MIN}–${DAILY_NEW_WORDS_MAX} 之间。`
  }
  return null
}

export function validateDailyMinutes(value: number): string | null {
  if (!Number.isInteger(value)) {
    return '每日学习时长需为整数分钟。'
  }
  if (value < DAILY_MINUTES_MIN || value > DAILY_MINUTES_MAX) {
    return `每日学习时长需在 ${DAILY_MINUTES_MIN}–${DAILY_MINUTES_MAX} 分钟之间。`
  }
  return null
}

/** At least one memory module must stay enabled, or the learner has no way to study. */
export function validateMemoryConfig(config: MemoryConfig): string | null {
  const enabled = MEMORY_MODULES.filter((module) => config[module].enabled)
  if (enabled.length === 0) {
    return '至少需要启用一种训练方式（翻卡、选择或拼写）。'
  }
  return null
}

export function validateProfile(update: LearningProfileUpdate, today: string = todayIsoDate()): FieldErrors {
  const errors: FieldErrors = {}

  if (!EXAM_TARGETS.includes(update.examTarget)) {
    errors.examTarget = '目标考试必须从给定选项中选择。'
  }

  const examDateError = validateExamDate(update.examDate, today)
  if (examDateError) {
    errors.examDate = examDateError
  }

  const newWordsError = validateDailyNewWords(update.dailyNewWords)
  if (newWordsError) {
    errors.dailyNewWords = newWordsError
  }

  const minutesError = validateDailyMinutes(update.dailyMinutes)
  if (minutesError) {
    errors.dailyMinutes = minutesError
  }

  const memoryError = validateMemoryConfig(update.memoryConfig)
  if (memoryError) {
    errors.memoryConfig = memoryError
  }

  return errors
}

export function hasFieldErrors(errors: FieldErrors): boolean {
  return Object.keys(errors).length > 0
}

/**
 * Spelling answer normalisation mirrors the documented backend rule: the server
 * ignores case. The frontend never decides correctness, it only sends a clean
 * string, so no local comparison happens here.
 */
export function normaliseSpellingInput(raw: string): string {
  return raw.trim().toLowerCase()
}

/** A spelling answer is submittable when every blank has one character. */
export function isSpellingComplete(values: readonly string[]): boolean {
  return values.length > 0 && values.every((value) => value.length === 1)
}

export function defaultMemoryConfig(): MemoryConfig {
  return {
    flashcard: { enabled: true, blankType: null },
    choice: { enabled: true, blankType: null },
    spelling: { enabled: true, blankType: 'full' },
  }
}

/** Enabled modules in a stable order, used for module pickers. */
export function enabledModules(config: MemoryConfig): MemoryModule[] {
  return MEMORY_MODULES.filter((module) => config[module].enabled)
}

export function isSpellingBlankType(value: unknown): value is SpellingBlankType {
  return value === 'full' || value === 'partial' || value === 'first_letter'
}

export function isExamTarget(value: unknown): value is ExamTarget {
  return typeof value === 'string' && (EXAM_TARGETS as readonly string[]).includes(value)
}
