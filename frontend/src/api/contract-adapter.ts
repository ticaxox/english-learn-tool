/**
 * THE single calibration point for T-FE-004.
 *
 * The backend identifiers below come only from the frozen T-BE-004 snapshot:
 *   contract_sha  25ad69f3c2c9ad29c01df6afa88b87e18404361e
 *   openapi raw   248ff876dc2e9f3f039aefc84c300f29767a2fe6d03d4364e882c138190f57e7
 *   semantic      17ba617968f593c50bfed3e1689f136341cc53855a697eae151fb9e878b03222
 *
 * Views and composables consume UI-facing types only. This module is the sole
 * place allowed to know backend JSON field names.
 */
import { ContractError } from './errors'
import type {
  LearningProfileUpdate,
  MemoryModule,
  StudyEventInput,
} from '../types/learning'
import {
  type AiPracticeState,
  type LearningProfile,
  type LearningStats,
  type LearnedWordState,
  type MasteryOutcome,
  type MemoryConfig,
  type MemoryModulePreference,
  type MistakePriorityUpdate,
  type PagedMistakes,
  type SessionSummary,
  type SpellingBlank,
  type SpellingBlankType,
  type StudyFeedback,
  type StudyQuestion,
  type TodayPlan,
  type TodayStatus,
  type WordStateStatus,
  EXAM_TARGETS,
  MEMORY_MODULES,
} from '../types/learning'

/** Kept for callers that still reference the old gate error type. */
export class ContractPendingError extends ContractError {
  readonly endpoint: string

  constructor(endpoint: string) {
    super(`接口契约尚未冻结（${endpoint}）。`)
    this.name = 'ContractPendingError'
    this.endpoint = endpoint
    Object.setPrototypeOf(this, ContractPendingError.prototype)
  }
}

export interface FrozenContract {
  contractSha: string
  openapiSha256: string
  semanticSha256: string
  openapiVersion: string
  pathCount: number
  schemaCount: number
}

const OPENAPI_SHA256 = [
  '248ff876dc2e9f3f039aefc84c300f29',
  '767a2fe6d03d4364e882c138190f57e7',
].join('')
const SEMANTIC_SHA256 = [
  '17ba617968f593c50bfed3e1689f13634',
  '1cc53855a697eae151fb9e878b03222',
].join('')

export const FROZEN_CONTRACT: FrozenContract = {
  contractSha: '25ad69f3c2c9ad29c01df6afa88b87e18404361e',
  openapiSha256: OPENAPI_SHA256,
  semanticSha256: SEMANTIC_SHA256,
  openapiVersion: '3.1.0',
  pathCount: 39,
  schemaCount: 67,
}

export function isContractFrozen(): boolean {
  return true
}

export function contractCoordinateLabel(): string {
  return `contract_sha ${FROZEN_CONTRACT.contractSha.slice(0, 12)} · openapi ${FROZEN_CONTRACT.openapiSha256.slice(0, 12)}`
}

/** Declarative backend field map. Keep every backend name in this table. */
const CONTRACT = {
  profile: {
    examTarget: 'target_exam',
    examDate: 'exam_date',
    dailyNewWords: 'daily_new_words',
    dailyMinutes: 'daily_study_minutes',
    department: 'department',
    learningGroup: 'learning_group',
    onboardingCompleted: 'onboarding_completed',
    updatedAt: 'updated_at',
  },
  memoryConfig: {
    flashcardEnabled: 'flashcard_enabled',
    choiceEnabled: 'choice_enabled',
    spellingEnabled: 'spelling_enabled',
    preferences: 'preferences',
    updatedAt: 'updated_at',
    spellingMode: 'spelling_mode',
  },
  today: {
    localDate: 'local_date',
    wordbookId: 'wordbook_id',
    wordbookName: 'wordbook_name',
    newWords: 'new_words',
    dueReviews: 'due_reviews',
    extraDueAvailable: 'extra_due_available',
    extraDueCount: 'extra_due_count',
    activeMinutes: 'active_minutes_today',
    studyMinutesTarget: 'study_minutes_target',
    status: 'status',
    aiPractice: 'ai_practice',
    calculationVersion: 'calculation_version',
    generatedAt: 'generated_at',
    newWordReason: 'new_word_reason',
  },
  stats: {
    localDate: 'local_date',
    activeMinutes: 'active_minutes_today',
    goalMinutes: 'study_minutes_target',
    goalReached: 'goal_reached',
    streakDays: 'current_streak_days',
    sources: 'sources',
    heartbeatSeconds: 'heartbeat_seconds',
    memoryEventCount: 'memory_event_count',
    sessionCount: 'session_count',
  },
  heartbeat: { sessionId: 'session_id' },
  session: {
    sessionId: 'session_id',
    module: 'module',
    status: 'status',
    wordbookId: 'wordbook_id',
    wordbookName: 'wordbook_name',
    localDate: 'local_date',
    configSnapshot: 'config_snapshot',
    stats: 'stats',
    calculationVersion: 'calculation_version',
    itemsTotal: 'items_total',
    itemsCompleted: 'items_completed',
    nextItem: 'next_item',
    card: 'card',
    startedAt: 'started_at',
    endedAt: 'ended_at',
  },
  item: {
    itemId: 'item_id',
    entryId: 'entry_id',
    wordStateId: 'word_state_id',
    reason: 'reason',
    isExtra: 'is_extra',
    position: 'position',
    completed: 'completed',
    goodCount: 'good_count',
    againCount: 'again_count',
    relearnCount: 'relearn_count',
    lastRating: 'last_rating',
  },
  card: {
    module: 'module',
    prompt: 'prompt',
    promptLabel: 'prompt_label',
    cloze: 'cloze',
    phonetic: 'phonetic',
    partOfSpeech: 'part_of_speech',
    options: 'options',
    optionCount: 'option_count',
  },
  event: {
    itemId: 'item_id',
    action: 'action',
    answer: 'answer',
    durationMs: 'duration_ms',
  },
  eventResponse: {
    eventId: 'event_id',
    itemId: 'item_id',
    action: 'action',
    rating: 'rating',
    gradedCorrect: 'is_correct',
    correctAnswer: 'correct_answer',
    itemCompleted: 'item_completed',
    sessionCompleted: 'session_completed',
    session: 'session',
  },
  wordState: {
    stateId: 'word_state_id',
    entryId: 'entry_id',
    headword: 'headword',
    status: 'status',
    dueAt: 'due_at',
    masteredAt: 'mastered_at',
    reviewCount: 'review_count',
    lapseCount: 'lapse_count',
    algorithmVersion: 'algorithm_version',
  },
  mistake: {
    stateId: 'word_state_id',
    entryId: 'entry_id',
    headword: 'headword',
    definition: 'definition_zh',
    phonetic: 'phonetic',
    againCount: 'again_count',
    lastAgainAt: 'last_again_at',
    priority: 'is_priority',
    status: 'status',
  },
  mistakeList: {
    items: 'items',
    nextCursor: 'next_cursor',
    hasMore: 'has_more',
  },
  priority: { isPriority: 'is_priority' },
} as const

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function fail(endpoint: string, detail: string): never {
  throw new ContractError(`${endpoint} 的响应与冻结契约不一致：${detail}`)
}

function requireRecord(value: unknown, endpoint: string, where: string): Record<string, unknown> {
  if (!isRecord(value)) {
    fail(endpoint, `${where} 应为对象，实际为 ${Array.isArray(value) ? 'array' : typeof value}。`)
  }
  return value
}

function optionalRecord(value: unknown, endpoint: string, where: string): Record<string, unknown> | null {
  if (value === null || value === undefined) return null
  return requireRecord(value, endpoint, where)
}

function requireString(value: unknown, endpoint: string, where: string): string {
  if (typeof value !== 'string' || value.length === 0) {
    fail(endpoint, `${where} 应为非空字符串。`)
  }
  return value
}

function optionalString(value: unknown, endpoint: string, where: string): string | null {
  if (value === null || value === undefined) return null
  if (typeof value !== 'string') fail(endpoint, `${where} 应为字符串或 null。`)
  return value
}

function requireInt(value: unknown, endpoint: string, where: string): number {
  if (typeof value !== 'number' || !Number.isInteger(value)) {
    fail(endpoint, `${where} 应为整数。`)
  }
  return value
}

function optionalInt(value: unknown, endpoint: string, where: string): number | null {
  if (value === null || value === undefined) return null
  return requireInt(value, endpoint, where)
}

function requireBoolean(value: unknown, endpoint: string, where: string): boolean {
  if (typeof value !== 'boolean') fail(endpoint, `${where} 应为布尔值。`)
  return value
}

function optionalBoolean(value: unknown, fallback: boolean, endpoint: string, where: string): boolean {
  if (value === null || value === undefined) return fallback
  return requireBoolean(value, endpoint, where)
}

function optionalEnum<T extends string>(
  value: unknown,
  allowed: readonly T[],
  endpoint: string,
  where: string,
): T | null {
  if (value === null || value === undefined) return null
  return requireEnum(value, allowed, endpoint, where)
}

function requireEnum<T extends string>(
  value: unknown,
  allowed: readonly T[],
  endpoint: string,
  where: string,
): T {
  if (typeof value !== 'string' || !allowed.includes(value as T)) {
    fail(endpoint, `${where} 必须是 ${allowed.join(' / ')} 之一，实际为 ${JSON.stringify(value)}。`)
  }
  return value as T
}

function requireArray(value: unknown, endpoint: string, where: string): unknown[] {
  if (!Array.isArray(value)) fail(endpoint, `${where} 应为数组。`)
  return value
}

function requireStringArray(value: unknown, endpoint: string, where: string): string[] {
  return requireArray(value, endpoint, where).map((item, index) =>
    requireString(item, endpoint, `${where}[${index}]`),
  )
}

const TODAY_STATUSES: readonly TodayStatus[] = [
  'not_started',
  'in_progress',
  'completed',
  'extra_available',
]
const AI_STATES: readonly AiPracticeState[] = [
  'not_available',
  'not_configured',
  'available',
  'unknown',
]
const BLANK_TYPES: readonly SpellingBlankType[] = ['full', 'partial', 'first_letter', 'middle']
const SESSION_STATUSES = ['active', 'completed', 'abandoned'] as const
const EVENT_ACTIONS = ['again', 'good', 'mastered', 'shown'] as const
const WORD_STATE_STATUSES: readonly WordStateStatus[] = [
  'new',
  'learning',
  'review',
  'relearning',
  'mastered',
  'suspended',
]

export const contractHelpers = {
  isRecord,
  requireRecord,
  requireString,
  optionalString,
  requireInt,
  optionalInt,
  requireBoolean,
  requireEnum,
  requireArray,
  TODAY_STATUSES,
  AI_STATES,
  BLANK_TYPES,
  EXAM_TARGETS,
  MEMORY_MODULES,
} as const

function remainingOf(session: Record<string, unknown>, endpoint: string): number {
  return Math.max(
    0,
    requireInt(session[CONTRACT.session.itemsTotal], endpoint, 'items_total') -
      requireInt(session[CONTRACT.session.itemsCompleted], endpoint, 'items_completed'),
  )
}

function profilePayload(payload: unknown): Record<string, unknown> {
  return requireRecord(payload, '/users/me/profile', '响应体')
}

export function parseLearningProfile(payload: unknown, memoryConfig: MemoryConfig): LearningProfile {
  const endpoint = '/users/me/profile'
  const body = profilePayload(payload)
  const rawExam = optionalEnum(body[CONTRACT.profile.examTarget], EXAM_TARGETS, endpoint, 'target_exam')
  return {
    examTarget: rawExam,
    examDate: optionalString(body[CONTRACT.profile.examDate], endpoint, 'exam_date'),
    dailyNewWords: requireInt(body[CONTRACT.profile.dailyNewWords], endpoint, 'daily_new_words'),
    dailyMinutes: requireInt(body[CONTRACT.profile.dailyMinutes], endpoint, 'daily_study_minutes'),
    department: optionalString(body[CONTRACT.profile.department], endpoint, 'department'),
    learningGroup: optionalString(body[CONTRACT.profile.learningGroup], endpoint, 'learning_group'),
    memoryConfig,
    needsOnboarding: !requireBoolean(body[CONTRACT.profile.onboardingCompleted], endpoint, 'onboarding_completed'),
    planEffectiveFrom: null,
    practicePoolTarget: typeof body.practice_pool_target === 'number' ? body.practice_pool_target : 0,
    challengeGenerationTime: optionalString(body.challenge_generation_time, endpoint, 'challenge_generation_time'),
  }
}

export function serializeProfileUpdate(update: LearningProfileUpdate): unknown {
  if (update.examTarget === null) {
    throw new ContractError('PATCH /users/me/profile：目标考试不能为空。')
  }
  return {
    [CONTRACT.profile.examTarget]: update.examTarget,
    [CONTRACT.profile.examDate]: update.examDate,
    [CONTRACT.profile.dailyNewWords]: update.dailyNewWords,
    [CONTRACT.profile.dailyMinutes]: update.dailyMinutes,
    practice_pool_target: update.practicePoolTarget,
    challenge_generation_time: update.challengeGenerationTime,
  }
}


export function parseMemoryConfig(payload: unknown): MemoryConfig {
  const endpoint = '/memory/config'
  const body = requireRecord(payload, endpoint, '响应体')
  const preferences = optionalRecord(body[CONTRACT.memoryConfig.preferences], endpoint, 'preferences') ?? {}
  const spellingMode = optionalEnum(
    preferences[CONTRACT.memoryConfig.spellingMode],
    BLANK_TYPES,
    endpoint,
    'preferences.spelling_mode',
  )
  return {
    flashcard: {
      enabled: optionalBoolean(body[CONTRACT.memoryConfig.flashcardEnabled], true, endpoint, 'flashcard_enabled'),
      blankType: null,
    },
    choice: {
      enabled: optionalBoolean(body[CONTRACT.memoryConfig.choiceEnabled], true, endpoint, 'choice_enabled'),
      blankType: null,
    },
    spelling: {
      enabled: optionalBoolean(body[CONTRACT.memoryConfig.spellingEnabled], true, endpoint, 'spelling_enabled'),
      blankType: spellingMode,
    },
    preferences: { ...preferences },
  }
}

export function serializeMemoryConfig(config: MemoryConfig): unknown {
  const preferences: Record<string, unknown> = { ...config.preferences }
  if (config.spelling.blankType !== null) {
    preferences[CONTRACT.memoryConfig.spellingMode] = config.spelling.blankType
  } else {
    // Picking "random" again must clear the previous explicit mode.
    delete preferences[CONTRACT.memoryConfig.spellingMode]
  }
  return {
    [CONTRACT.memoryConfig.flashcardEnabled]: config.flashcard.enabled,
    [CONTRACT.memoryConfig.choiceEnabled]: config.choice.enabled,
    [CONTRACT.memoryConfig.spellingEnabled]: config.spelling.enabled,
    [CONTRACT.memoryConfig.preferences]: preferences,
  }
}

function parseProgress(value: unknown, endpoint: string, where: string) {
  const body = requireRecord(value, endpoint, where)
  return {
    completed: requireInt(body.completed, endpoint, `${where}.completed`),
    target: requireInt(body.target, endpoint, `${where}.target`),
  }
}

export function parseTodayPlan(payload: unknown): TodayPlan {
  const endpoint = '/learning/today'
  const body = requireRecord(payload, endpoint, '响应体')
  const ai = optionalRecord(body[CONTRACT.today.aiPractice], endpoint, 'ai_practice')
  const aiState = ai
    ? optionalEnum(ai.status, AI_STATES, endpoint, 'ai_practice.status') ?? 'unknown'
    : 'not_available'
  return {
    localDate: requireString(body[CONTRACT.today.localDate], endpoint, 'local_date'),
    wordbook: {
      id: requireString(body[CONTRACT.today.wordbookId], endpoint, 'wordbook_id'),
      name: requireString(body[CONTRACT.today.wordbookName], endpoint, 'wordbook_name'),
    },
    newWords: parseProgress(body[CONTRACT.today.newWords], endpoint, 'new_words'),
    dueReviews: parseProgress(body[CONTRACT.today.dueReviews], endpoint, 'due_reviews'),
    extraDueAvailable: optionalBoolean(body[CONTRACT.today.extraDueAvailable], false, endpoint, 'extra_due_available'),
    extraDueCount: optionalInt(body[CONTRACT.today.extraDueCount], endpoint, 'extra_due_count') ?? 0,
    minutes: {
      active: requireInt(body[CONTRACT.today.activeMinutes], endpoint, 'active_minutes_today'),
      goal: requireInt(body[CONTRACT.today.studyMinutesTarget], endpoint, 'study_minutes_target'),
    },
    status: requireEnum(body[CONTRACT.today.status], TODAY_STATUSES, endpoint, 'status'),
    aiPractice: {
      state: aiState,
      message: ai ? optionalString(ai.reason, endpoint, 'ai_practice.reason') : null,
    },
    calculationVersion: optionalString(body[CONTRACT.today.calculationVersion], endpoint, 'calculation_version'),
    generatedAt: optionalString(body[CONTRACT.today.generatedAt], endpoint, 'generated_at'),
    shortfallReason: optionalString(body[CONTRACT.today.newWordReason], endpoint, 'new_word_reason'),
  }
}

export function parseLearningStats(payload: unknown): LearningStats {
  const endpoint = '/learning/stats'
  const body = requireRecord(payload, endpoint, '响应体')
  const sources = requireRecord(body[CONTRACT.stats.sources], endpoint, 'sources')
  return {
    localDate: requireString(body[CONTRACT.stats.localDate], endpoint, 'local_date'),
    activeMinutes: requireInt(body[CONTRACT.stats.activeMinutes], endpoint, 'active_minutes_today'),
    goalMinutes: requireInt(body[CONTRACT.stats.goalMinutes], endpoint, 'study_minutes_target'),
    goalReached: requireBoolean(body[CONTRACT.stats.goalReached], endpoint, 'goal_reached'),
    streakDays: requireInt(body[CONTRACT.stats.streakDays], endpoint, 'current_streak_days'),
    sources: [
      `心跳 ${requireInt(sources[CONTRACT.stats.heartbeatSeconds], endpoint, 'sources.heartbeat_seconds')} 秒`,
      `记忆事件 ${requireInt(sources[CONTRACT.stats.memoryEventCount], endpoint, 'sources.memory_event_count')} 次`,
      `会话 ${requireInt(sources[CONTRACT.stats.sessionCount], endpoint, 'sources.session_count')} 次`,
    ],
  }
}

export function serializeHeartbeat(input: { sessionId: string | null }): unknown {
  return { [CONTRACT.heartbeat.sessionId]: input.sessionId }
}

export function serializeSessionStart(module: MemoryModule): unknown {
  return { [CONTRACT.session.module]: module }
}

export function parseSessionSummary(payload: unknown): SessionSummary {
  const endpoint = 'POST /memory/sessions'
  const body = requireRecord(payload, endpoint, '响应体')
  return {
    sessionId: requireString(body[CONTRACT.session.sessionId], endpoint, 'session_id'),
    module: requireEnum(body[CONTRACT.session.module], MEMORY_MODULES, endpoint, 'module'),
    remaining: remainingOf(body, endpoint),
    completed: requireInt(body[CONTRACT.session.itemsCompleted], endpoint, 'items_completed'),
    startedAt: optionalString(body[CONTRACT.session.startedAt], endpoint, 'started_at'),
  }
}

function parseBlankType(session: Record<string, unknown>, endpoint: string): SpellingBlankType | null {
  const config = optionalRecord(session[CONTRACT.session.configSnapshot], endpoint, 'config_snapshot')
  const preferences = optionalRecord(config?.preferences, endpoint, 'config_snapshot.preferences')
  return optionalEnum(
    preferences?.[CONTRACT.memoryConfig.spellingMode],
    BLANK_TYPES,
    endpoint,
    'config_snapshot.preferences.spelling_mode',
  )
}

function blanksFromCloze(cloze: string): SpellingBlank[] {
  return Array.from(cloze).map((character, index) => ({
    index,
    prefilled: character !== '_',
    character: character === '_' ? null : character,
  }))
}

export function parseStudyQuestion(payload: unknown, module: MemoryModule): StudyQuestion | null {
  const endpoint = `GET /memory/sessions/{id} (${module})`
  const body = requireRecord(payload, endpoint, '响应体')
  const actualModule = requireEnum(body[CONTRACT.session.module], MEMORY_MODULES, endpoint, 'module')
  if (actualModule !== module) {
    fail(endpoint, `module 应为 ${module}，实际为 ${actualModule}。`)
  }
  requireEnum(body[CONTRACT.session.status], SESSION_STATUSES, endpoint, 'status')
  if (body[CONTRACT.session.nextItem] === null) return null
  const item = requireRecord(body[CONTRACT.session.nextItem], endpoint, 'next_item')
  const card = requireRecord(body[CONTRACT.session.card], endpoint, 'card')
  const questionId = requireString(item[CONTRACT.item.itemId], endpoint, 'next_item.item_id')
  const remaining = remainingOf(body, endpoint)

  if (module === 'flashcard') {
    return {
      kind: 'flashcard',
      questionId,
      wordbookId: requireString(body[CONTRACT.session.wordbookId], endpoint, 'wordbook_id'),
      entryId: requireString(item[CONTRACT.item.entryId], endpoint, 'next_item.entry_id'),
      front: requireString(card[CONTRACT.card.prompt], endpoint, 'card.prompt'),
      back: null,
      phonetic: optionalString(card[CONTRACT.card.phonetic], endpoint, 'card.phonetic'),
      partOfSpeech: optionalString(card[CONTRACT.card.partOfSpeech], endpoint, 'card.part_of_speech'),
      example: null,
      remaining,
    }
  }

  if (module === 'choice') {
    const labels = requireStringArray(card[CONTRACT.card.options], endpoint, 'card.options')
    const optionCount = requireInt(card[CONTRACT.card.optionCount], endpoint, 'card.option_count')
    if (optionCount < 1 || labels.length !== optionCount) {
      fail(endpoint, `option_count=${optionCount} 与 options.length=${labels.length} 不一致或小于 1。`)
    }
    return {
      kind: 'choice',
      questionId,
      prompt: requireString(card[CONTRACT.card.prompt], endpoint, 'card.prompt'),
      options: labels.map((label) => ({ optionId: label, label })),
      optionCount,
      phonetic: optionalString(card[CONTRACT.card.phonetic], endpoint, 'card.phonetic'),
      remaining,
    }
  }

  const cloze = requireString(card[CONTRACT.card.cloze], endpoint, 'card.cloze')
  return {
    kind: 'spelling',
    questionId,
    definition: requireString(card[CONTRACT.card.prompt], endpoint, 'card.prompt'),
    phonetic: optionalString(card[CONTRACT.card.phonetic], endpoint, 'card.phonetic'),
    blankType: parseBlankType(body, endpoint),
    cloze,
    blanks: blanksFromCloze(cloze),
    remaining,
  }
}

export function serializeStudyEvent(event: StudyEventInput): unknown {
  const base = {
    [CONTRACT.event.itemId]: event.questionId,
    [CONTRACT.event.durationMs]: 'elapsedMs' in event ? event.elapsedMs : 0,
  }
  switch (event.kind) {
    case 'flashcard-reveal':
      return { ...base, [CONTRACT.event.action]: 'shown', [CONTRACT.event.answer]: null }
    case 'flashcard-rate':
      return { ...base, [CONTRACT.event.action]: event.rating, [CONTRACT.event.answer]: null }
    case 'choice-answer':
      return { ...base, [CONTRACT.event.action]: 'good', [CONTRACT.event.answer]: event.optionId }
    case 'spelling-answer':
      return { ...base, [CONTRACT.event.action]: 'good', [CONTRACT.event.answer]: event.answer }
    case 'master-word':
      return { ...base, [CONTRACT.event.action]: 'mastered', [CONTRACT.event.answer]: null }
  }
}

export function parseStudyFeedback(payload: unknown): StudyFeedback {
  const endpoint = 'POST /memory/sessions/{id}/events'
  const body = requireRecord(payload, endpoint, '响应体')
  const action = requireEnum(body[CONTRACT.eventResponse.action], EVENT_ACTIONS, endpoint, 'action')
  const rating = optionalEnum(body[CONTRACT.eventResponse.rating], ['again', 'good'] as const, endpoint, 'rating')
  const gradedCorrect = body[CONTRACT.eventResponse.gradedCorrect]
  if (gradedCorrect !== null && gradedCorrect !== undefined && typeof gradedCorrect !== 'boolean') {
    fail(endpoint, 'is_correct 应为布尔值或 null。')
  }
  const correctAnswer = optionalString(
    body[CONTRACT.eventResponse.correctAnswer],
    endpoint,
    'correct_answer',
  )
  const itemCompleted = requireBoolean(body[CONTRACT.eventResponse.itemCompleted], endpoint, 'item_completed')
  const sessionCompleted = requireBoolean(body[CONTRACT.eventResponse.sessionCompleted], endpoint, 'session_completed')
  const session = requireRecord(body[CONTRACT.eventResponse.session], endpoint, 'session')

  let headline = '服务端已记录本次操作'
  if (action === 'mastered') headline = '已记住，卡片已移出当前队列'
  else if (gradedCorrect === true) headline = '回答正确'
  else if (gradedCorrect === false) headline = '回答错误，稍后会再出现'
  else if (rating === 'good') headline = '已记为有印象'
  else if (rating === 'again') headline = '已记为无印象'

  return {
    headline,
    gradedCorrect: gradedCorrect === true ? true : gradedCorrect === false ? false : null,
    correctAnswer,
    detail: gradedCorrect === false && correctAnswer ? `正确答案：${correctAnswer}` : null,
    removed: itemCompleted,
    requeued: !itemCompleted && !sessionCompleted,
    remaining: remainingOf(session, endpoint),
    sessionCompleted,
  }
}

function parseWordState(payload: unknown, endpoint: string) {
  const body = requireRecord(payload, endpoint, '响应体')
  return {
    stateId: requireString(body[CONTRACT.wordState.stateId], endpoint, 'word_state_id'),
    headword: requireString(body[CONTRACT.wordState.headword], endpoint, 'headword'),
    status: requireEnum(body[CONTRACT.wordState.status], WORD_STATE_STATUSES, endpoint, 'status'),
    dueAt: optionalString(body[CONTRACT.wordState.dueAt], endpoint, 'due_at'),
    masteredAt: optionalString(body[CONTRACT.wordState.masteredAt], endpoint, 'mastered_at'),
  }
}

export function parseMasteryOutcome(payload: unknown): MasteryOutcome {
  const endpoint = 'PATCH /memory/words/{state_id}/master'
  const state = parseWordState(payload, endpoint)
  return {
    stateId: state.stateId,
    headword: state.headword,
    mastered: state.status === 'mastered',
    message: state.masteredAt ? `服务端记录已记住时间：${state.masteredAt}` : null,
  }
}

export function parseLearnedWordState(payload: unknown): LearnedWordState {
  const endpoint = 'PATCH /memory/words/{state_id}/restore'
  const state = parseWordState(payload, endpoint)
  return {
    stateId: state.stateId,
    headword: state.headword,
    nextDueAt: state.dueAt,
    mastered: state.status === 'mastered',
  }
}

export function parseMistakes(payload: unknown): PagedMistakes {
  const endpoint = '/memory/mistakes'
  const body = requireRecord(payload, endpoint, '响应体')
  const items = requireArray(body[CONTRACT.mistakeList.items], endpoint, 'items').map((value, index) => {
    const item = requireRecord(value, endpoint, `items[${index}]`)
    return {
      entryId: requireString(item[CONTRACT.mistake.entryId], endpoint, `items[${index}].entry_id`),
      stateId: requireString(item[CONTRACT.mistake.stateId], endpoint, `items[${index}].word_state_id`),
      headword: requireString(item[CONTRACT.mistake.headword], endpoint, `items[${index}].headword`),
      definition: optionalString(item[CONTRACT.mistake.definition], endpoint, `items[${index}].definition_zh`),
      module: null,
      lastMistakeAt: optionalString(item[CONTRACT.mistake.lastAgainAt], endpoint, `items[${index}].last_again_at`),
      mistakeCount: requireInt(item[CONTRACT.mistake.againCount], endpoint, `items[${index}].again_count`),
      priorityReview: requireBoolean(item[CONTRACT.mistake.priority], endpoint, `items[${index}].is_priority`),
      status: requireEnum(item[CONTRACT.mistake.status], WORD_STATE_STATUSES, endpoint, `items[${index}].status`),
    }
  })
  return {
    items,
    nextCursor: optionalString(body[CONTRACT.mistakeList.nextCursor], endpoint, 'next_cursor'),
    hasMore: optionalBoolean(body[CONTRACT.mistakeList.hasMore], false, endpoint, 'has_more'),
  }
}

export function serializeMistakePriority(update: MistakePriorityUpdate): unknown {
  return { [CONTRACT.priority.isPriority]: update.priorityReview }
}

export type { MemoryModulePreference }