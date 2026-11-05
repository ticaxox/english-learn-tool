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
import { getWordbookDetail } from './wordbooks'
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
  serializeMistakePriority,
  serializeProfileUpdate,
  serializeSessionStart,
  serializeStudyEvent,
} from './contract-adapter'
import type {
  LearningProfile,
  LearningProfileUpdate,
  LearningStats,
  LearnedWordState,
  FlashcardQuestion,
  MasteryOutcome,
  MemoryConfig,
  MemoryModule,
  MistakePriorityUpdate,
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
  const [profilePayload, configPayload] = await Promise.all([
    apiClient.get('/users/me/profile', { signal: options.signal }),
    apiClient.get('/memory/config', { signal: options.signal }),
  ])
  return parseLearningProfile(profilePayload, parseMemoryConfig(configPayload))
}

export async function updateLearningProfile(
  update: LearningProfileUpdate,
  options: FetchOptions = {},
): Promise<LearningProfile> {
  const payload = await apiClient.patch('/users/me/profile', serializeProfileUpdate(update), {
    signal: options.signal,
    retryCount: 0,
  })
  const config = await saveMemoryConfig(update.memoryConfig, options)
  return parseLearningProfile(payload, config)
}

/** Persist per-user AI quota overrides; -1 means unlimited. */
export async function updateAiQuotaLimits(limits: Record<string, number>): Promise<void> {
  await apiClient.patch('/users/me/profile', { ai_quota_limits: limits }, { retryCount: 0 })
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
  input: { sessionId: string | null },
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
): Promise<StudyQuestion | null> {
  const payload = await apiClient.get(`/memory/sessions/${encodeURIComponent(sessionId)}`, {
    signal: options.signal,
  })
  const question = parseStudyQuestion(payload, module)
  if (!question) return null
  return question.kind === 'flashcard' ? await resolveFlashcardAnswer(question) : question
}

async function resolveFlashcardAnswer(question: FlashcardQuestion): Promise<FlashcardQuestion> {
  try {
    let offset = 0
    while (true) {
      const detail = await getWordbookDetail(question.wordbookId, offset, 100)
      const entry = detail.entries.find((candidate) => candidate.id === question.entryId)
      if (entry) {
        const definition = entry.definitions.find((item) => item.definition_zh || item.definition_en) ?? entry.definitions[0]
        const example = definition?.examples[0]
        return {
          ...question,
          back: definition?.definition_zh ?? definition?.definition_en ?? null,
          partOfSpeech: question.partOfSpeech ?? definition?.part_of_speech ?? null,
          example: example?.example_en ?? null,
        }
      }
      offset += detail.entries.length
      if (offset >= detail.total_entries || detail.entries.length === 0) break
    }
  } catch {
    // The definition lookup is supplementary; a failed read leaves the card
    // usable and the trainer states that no definition was returned.
  }
  return question
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
  // FastAPI still expects a JSON body for the empty SessionCompleteRequest model.
  await apiClient.post(`/memory/sessions/${encodeURIComponent(sessionId)}/complete`, {}, {
    signal: options.signal,
    retryCount: 0,
  })
}

export interface MemoryProgressReset {
  sessionsReset: number
  wordsReset: number
}

/** Clear today's memory sessions and make their words due again. */
export async function resetMemoryProgress(options: FetchOptions = {}): Promise<MemoryProgressReset> {
  const payload = await apiClient.post('/memory/progress/reset', {}, {
    signal: options.signal,
    retryCount: 0,
  })
  const body = (payload ?? {}) as Record<string, unknown>
  return {
    sessionsReset: typeof body.sessions_reset === 'number' ? body.sessions_reset : 0,
    wordsReset: typeof body.words_reset === 'number' ? body.words_reset : 0,
  }
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

/**
 * Toggle priority review for one mistake. The server recomputes ordering; this
 * only reports whether the entry should be prioritised.
 */
export async function setMistakePriority(
  entryId: string,
  update: MistakePriorityUpdate,
  options: FetchOptions = {},
): Promise<void> {
  await apiClient.patch(
    `/memory/mistakes/${encodeURIComponent(entryId)}/priority`,
    serializeMistakePriority(update),
    { signal: options.signal, retryCount: 0 },
  )
}

export async function fetchMistakes(
  query: MistakeQuery = {},
  options: FetchOptions = {},
): Promise<PagedMistakes> {
  const params = new URLSearchParams()
  params.set('limit', String(query.limit ?? 50))
  if (query.cursor) {
    params.set('cursor', query.cursor)
  }
  const payload = await apiClient.get(`/memory/mistakes?${params.toString()}`, {
    signal: options.signal,
  })
  return parseMistakes(payload)
}
