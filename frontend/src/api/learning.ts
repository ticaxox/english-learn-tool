/**
 * Learning / memory API surface for T-FE-004.
 *
 * Endpoint paths come from the T-BE-004 task document's published API list.
 * Nothing here knows a backend field name: every response is handed to
 * `contract-adapter.ts`, and every request body is built by it too. While the
 * contract is unfrozen the adapter throws `ContractPendingError`, so callers
 * surface an explicit "pending" state instead of fabricated data.
 */
import { apiClient } from './client'
import {
  parseLearningProfile,
  parseLearningStats,
  parseLearnedWordState,
  parseMasteryOutcome,
  parseMemoryConfig,
  parseMistakes,
  parseSessionSummary,
  parseStudyFeedback,
  parseStudyQuestion,
  parseTodayPlan,
  serializeHeartbeat,
  serializeMemoryConfig,
  serializeProfileUpdate,
  serializeSessionStart,
  serializeStudyEvent,
} from './contract-adapter'
import type {
  LearningProfile,
  LearningProfileUpdate,
  LearningStats,
  LearnedWordState,
  MasteryOutcome,
  MemoryConfig,
  MemoryModule,
  MistakeQuery,
  PagedMistakes,
  SessionSummary,
  StudyEventInput,
  StudyFeedback,
  StudyQuestion,
  TodayPlan,
} from '../types/learning'

export interface FetchOptions {
  signal?: AbortSignal
}

export async function fetchLearningProfile(options: FetchOptions = {}): Promise<LearningProfile> {
  const payload = await apiClient.get('/users/me/profile', { signal: options.signal })
  return parseLearningProfile(payload)
}

export async function updateLearningProfile(
  update: LearningProfileUpdate,
  options: FetchOptions = {},
): Promise<LearningProfile> {
  const payload = await apiClient.patch('/users/me/profile', serializeProfileUpdate(update), {
    signal: options.signal,
    retryCount: 0,
  })
  return parseLearningProfile(payload)
}

export async function fetchTodayPlan(options: FetchOptions = {}): Promise<TodayPlan> {
  const payload = await apiClient.get('/learning/today', { signal: options.signal })
  return parseTodayPlan(payload)
}

/** Idempotent server-side creation of today's plan snapshot. */
export async function ensureTodayPlan(options: FetchOptions = {}): Promise<TodayPlan> {
  const payload = await apiClient.post('/learning/daily-plan/ensure', undefined, {
    signal: options.signal,
    retryCount: 0,
  })
  return parseTodayPlan(payload)
}

export async function fetchLearningStats(options: FetchOptions = {}): Promise<LearningStats> {
  const payload = await apiClient.get('/learning/stats', { signal: options.signal })
  return parseLearningStats(payload)
}

/**
 * One heartbeat. The caller owns the 30s cadence and pause logic; this only
 * transmits the activity window the contract defines (never a client-side
 * accumulated total).
 */
export async function sendHeartbeat(
  input: { windowSeconds: number },
  idempotencyKey: string,
  options: FetchOptions = {},
): Promise<void> {
  await apiClient.post('/learning/heartbeat', serializeHeartbeat(input), {
    signal: options.signal,
    retryCount: 0,
    headers: { 'Idempotency-Key': idempotencyKey },
  })
}

export async function fetchMemoryConfig(options: FetchOptions = {}): Promise<MemoryConfig> {
  const payload = await apiClient.get('/memory/config', { signal: options.signal })
  return parseMemoryConfig(payload)
}

export async function saveMemoryConfig(
  config: MemoryConfig,
  options: FetchOptions = {},
): Promise<MemoryConfig> {
  const payload = await apiClient.put('/memory/config', serializeMemoryConfig(config), {
    signal: options.signal,
    retryCount: 0,
  })
  return parseMemoryConfig(payload)
}

export async function startMemorySession(
  module: MemoryModule,
  options: FetchOptions = {},
): Promise<SessionSummary> {
  const payload = await apiClient.post('/memory/sessions', serializeSessionStart(module), {
    signal: options.signal,
    retryCount: 0,
  })
  return parseSessionSummary(payload)
}

export async function fetchMemorySession(
  sessionId: string,
  module: MemoryModule,
  options: FetchOptions = {},
): Promise<StudyQuestion> {
  const payload = await apiClient.get(`/memory/sessions/${encodeURIComponent(sessionId)}`, {
    signal: options.signal,
  })
  return parseStudyQuestion(payload, module)
}

/**
 * Submit one learner action. `Idempotency-Key` protects against double clicks
 * and network retries producing duplicate Good/Again events.
 */
export async function submitStudyEvent(
  sessionId: string,
  event: StudyEventInput,
  idempotencyKey: string,
  options: FetchOptions = {},
): Promise<StudyFeedback> {
  const payload = await apiClient.post(
    `/memory/sessions/${encodeURIComponent(sessionId)}/events`,
    serializeStudyEvent(event),
    {
      signal: options.signal,
      retryCount: 0,
      headers: { 'Idempotency-Key': idempotencyKey },
    },
  )
  return parseStudyFeedback(payload)
}

export async function completeMemorySession(
  sessionId: string,
  options: FetchOptions = {},
): Promise<void> {
  await apiClient.post(`/memory/sessions/${encodeURIComponent(sessionId)}/complete`, undefined, {
    signal: options.signal,
    retryCount: 0,
  })
}

export async function masterWord(stateId: string, options: FetchOptions = {}): Promise<MasteryOutcome> {
  const payload = await apiClient.patch(
    `/memory/words/${encodeURIComponent(stateId)}/master`,
    undefined,
    { signal: options.signal, retryCount: 0 },
  )
  return parseMasteryOutcome(payload)
}

export async function restoreWord(
  stateId: string,
  options: FetchOptions = {},
): Promise<LearnedWordState> {
  const payload = await apiClient.patch(
    `/memory/words/${encodeURIComponent(stateId)}/restore`,
    undefined,
    { signal: options.signal, retryCount: 0 },
  )
  return parseLearnedWordState(payload)
}

export async function fetchMistakes(
  query: MistakeQuery = {},
  options: FetchOptions = {},
): Promise<PagedMistakes> {
  const params = new URLSearchParams()
  params.set('offset', String(query.offset ?? 0))
  params.set('limit', String(query.limit ?? 20))
  if (query.module) {
    params.set('module', query.module)
  }
  const payload = await apiClient.get(`/memory/mistakes?${params.toString()}`, {
    signal: options.signal,
  })
  return parseMistakes(payload)
}

