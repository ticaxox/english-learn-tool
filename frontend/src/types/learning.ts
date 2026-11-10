/**
 * UI-facing view models for learning / memory (T-FE-004).
 *
 * These types are deliberately OUR OWN shapes, not a transcription of the
 * backend JSON. Every backend field name lives in exactly one place,
 * `src/api/contract-adapter.ts`, which refuses to run until A01 freezes a
 * contract_sha for T-BE-004.
 *
 * Anti-leak note: `StudyQuestion` has no field able to carry a correct
 * answer, correct option id or answer key. Leakage becomes a type error
 * instead of a review item.
 */

export type ExamTarget = 'GAOKAO' | 'CET4' | 'CET6' | 'POSTGRAD' | 'IELTS' | 'TOEFL'

export const EXAM_TARGETS: readonly ExamTarget[] = [
  'GAOKAO',
  'CET4',
  'CET6',
  'POSTGRAD',
  'IELTS',
  'TOEFL',
]

export const EXAM_TARGET_LABELS: Record<ExamTarget, string> = {
  GAOKAO: '高考英语',
  CET4: '大学英语四级（CET-4）',
  CET6: '大学英语六级（CET-6）',
  POSTGRAD: '考研英语',
  IELTS: '雅思（IELTS）',
  TOEFL: '托福（TOEFL）',
}

export const DAILY_NEW_WORDS_MIN = 5
export const DAILY_NEW_WORDS_MAX = 100
export const DAILY_MINUTES_MIN = 15
export const DAILY_MINUTES_MAX = 180
export const DAILY_NEW_WORDS_DEFAULT = 20
export const DAILY_MINUTES_DEFAULT = 30

export type MemoryModule = 'flashcard' | 'choice' | 'spelling'

export const MEMORY_MODULES: readonly MemoryModule[] = ['flashcard', 'choice', 'spelling']

export const MEMORY_MODULE_LABELS: Record<MemoryModule, string> = {
  flashcard: '翻卡',
  choice: '选择',
  spelling: '拼写',
}

/** Spelling blanking strategy described by the product contract. */
export type SpellingBlankType = 'full' | 'partial' | 'first_letter' | 'middle'

export const SPELLING_BLANK_LABELS: Record<SpellingBlankType, string> = {
  full: '全挖空',
  partial: '部分挖空',
  first_letter: '保留首字母',
  middle: '中间挖空',
}

export interface MemoryModulePreference {
  enabled: boolean
  /** Only meaningful for spelling; `null` keeps the server-side default. */
  blankType: SpellingBlankType | null
}

export interface MemoryConfig {
  flashcard: MemoryModulePreference
  choice: MemoryModulePreference
  spelling: MemoryModulePreference
  /** Raw server preference keys preserved across a PUT. */
  preferences: Record<string, unknown>
}

export interface LearningProfile {
  examTarget: ExamTarget | null
  /** ISO calendar date `YYYY-MM-DD`, or null when unset. */
  examDate: string | null
  dailyNewWords: number
  dailyMinutes: number
  department: string | null
  learningGroup: string | null
  memoryConfig: MemoryConfig
  /** Backend reports no profile yet; the UI should onboard. */
  needsOnboarding: boolean
  /** Server instant from which the latest change applies to planning. */
  planEffectiveFrom: string | null
  practicePoolTarget: number
  challengeGenerationTime: string | null
  aiQuotaLimits: Record<string, number>
}

export type TodayStatus = 'not_started' | 'in_progress' | 'completed' | 'extra_available'

export const TODAY_STATUS_LABELS: Record<TodayStatus, string> = {
  not_started: '尚未开始',
  in_progress: '进行中',
  completed: '今日已完成',
  extra_available: '目标已完成，可继续加练',
}

export type AiPracticeState = 'not_available' | 'not_configured' | 'available' | 'unknown'

export interface AiPracticeSummary {
  state: AiPracticeState
  /** Server-provided explanation; never invented by the frontend. */
  message: string | null
}

export interface ProgressCounter {
  completed: number
  target: number
}

export interface TodayPlan {
  localDate: string
  wordbook: { id: string; name: string } | null
  newWords: ProgressCounter
  dueReviews: ProgressCounter
  extraDueAvailable: boolean
  extraDueCount: number
  minutes: { active: number; goal: number }
  status: TodayStatus
  aiPractice: AiPracticeSummary
  calculationVersion: string | null
  generatedAt: string | null
  /** Server note explaining a shortfall, e.g. not enough unseen words. */
  shortfallReason: string | null
}

export interface LearningStats {
  localDate: string
  activeMinutes: number
  goalMinutes: number
  goalReached: boolean
  streakDays: number | null
  sources: string[]
}

export interface SessionSummary {
  sessionId: string
  module: MemoryModule
  remaining: number
  completed: number
  startedAt: string | null
}

export interface FlashcardQuestion {
  kind: 'flashcard'
  questionId: string
  wordbookId: string
  entryId: string
  front: string
  /** Server-backed definition, or null when the wordbook has no definition. */
  back: string | null
  phonetic: string | null
  partOfSpeech: string | null
  example: string | null
  remaining: number
}

export interface ChoiceOption {
  optionId: string
  label: string
}

export interface ChoiceQuestion {
  kind: 'choice'
  questionId: string
  prompt: string
  options: ChoiceOption[]
  /** Server-declared option count; it is authoritative, not a UI constant. */
  optionCount: number
  phonetic: string | null
  partOfSpeech: string | null
  remaining: number
}

/**
 * One letter slot. The server lists EVERY letter position of the word, with
 * `prefilled` marking the letters it reveals (e.g. the first letter for the
 * `first_letter` strategy). That way the answer can be reconstructed by
 * concatenation in slot order, and the frontend never needs the full word.
 */
export interface SpellingBlank {
  index: number
  /** `true` when the server pre-fills this position (e.g. first letter). */
  prefilled: boolean
  /** Pre-filled character; only present when `prefilled` is true. */
  character: string | null
}

export interface SpellingQuestion {
  kind: 'spelling'
  questionId: string
  definition: string
  phonetic: string | null
  partOfSpeech: string | null
  blankType: SpellingBlankType | null
  cloze: string
  blanks: SpellingBlank[]
  remaining: number
}

export type StudyQuestion = FlashcardQuestion | ChoiceQuestion | SpellingQuestion

/** Learner actions understood by the memory session contract. */
export type FlashcardRating = 'again' | 'good'

export interface StudyFeedback {
  /** Server-confirmed outcome text; never computed locally. */
  headline: string
  /** Graded correctness; null for ungraded actions such as reveals or ratings. */
  gradedCorrect: boolean | null
  /** The correct word for a wrong graded answer; null otherwise. */
  correctAnswer: string | null
  detail: string | null
  /** Server says the word leaves the current queue. */
  removed: boolean
  /** Server asks for a later re-queue instead of completing. */
  requeued: boolean
  remaining: number
  sessionCompleted: boolean
}

/** Result of a server-confirmed "已记住" action. */
export interface MasteryOutcome {
  stateId: string
  headword: string
  mastered: boolean
  /** Server note, e.g. that the word was removed from the current queue. */
  message: string | null
}

export type WordStateStatus = 'new' | 'learning' | 'review' | 'relearning' | 'mastered' | 'suspended'

export interface MistakeEntry {
  entryId: string
  stateId: string
  headword: string
  definition: string | null
  /** The mistake endpoint does not expose the originating module. */
  module: MemoryModule | null
  lastMistakeAt: string | null
  mistakeCount: number
  priorityReview: boolean
  status: WordStateStatus
}

export interface PagedMistakes {
  items: MistakeEntry[]
  nextCursor: string | null
  hasMore: boolean
}

export interface LearnedWordState {
  stateId: string
  headword: string
  /** Server-computed next appearance; null while mastered. */
  nextDueAt: string | null
  mastered: boolean
}

// ---------------------------------------------------------------------------
// Request payloads (UI intent). The adapter converts these to backend JSON.
// ---------------------------------------------------------------------------

export interface LearningProfileUpdate {
  examTarget: ExamTarget
  examDate: string | null
  dailyNewWords: number
  dailyMinutes: number
  memoryConfig: MemoryConfig
  practicePoolTarget: number
  challengeGenerationTime: string | null
  aiQuotaLimits: Record<string, number>
}

/**
 * UI intent for the priority-review toggle. Our own shape: the adapter owns the
 * backend field name, which is not known before calibration.
 */
export interface MistakePriorityUpdate {
  priorityReview: boolean
}

export interface MistakeQuery {
  cursor?: string | null
  limit?: number
}

/** One learner action inside a memory session. */
export type StudyEventInput =
  | { kind: 'flashcard-reveal'; questionId: string }
  | { kind: 'flashcard-rate'; questionId: string; rating: FlashcardRating; elapsedMs: number }
  | { kind: 'choice-answer'; questionId: string; optionId: string; elapsedMs: number }
  | { kind: 'spelling-answer'; questionId: string; answer: string; elapsedMs: number }
  | { kind: 'master-word'; questionId: string; elapsedMs: number }
