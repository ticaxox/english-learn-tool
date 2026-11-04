/**
 * Memory session orchestration (T-FE-004).
 *
 * Owns: session start/restore, current question, guarded submission with
 * per-action idempotency keys, and server-confirmed feedback.
 *
 * Explicitly NOT owned here: scheduling, queue order, scoring, or deciding
 * that a word is finished. Every one of those is read from the server response.
 */
import { computed, ref } from 'vue'
import {
  completeMemorySession,
  fetchMemorySession,
  startMemorySession,
  submitStudyEvent,
} from '../api/learning'
import type {
  FlashcardRating,
  MemoryModule,
  SessionSummary,
  StudyEventInput,
  StudyFeedback,
  StudyQuestion,
} from '../types/learning'

function newIdempotencyKey(): string {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID()
  }
  return `ev-${Date.now()}-${Math.random().toString(16).slice(2)}`
}

export interface MemorySessionOptions {
  /** Injected for tests; defaults to the real endpoints. */
  api?: {
    start: (module: MemoryModule) => Promise<SessionSummary>
    loadQuestion: (sessionId: string, module: MemoryModule) => Promise<StudyQuestion | null>
    submit: (sessionId: string, event: StudyEventInput, key: string) => Promise<StudyFeedback>
    complete: (sessionId: string) => Promise<void>
  }
  now?: () => number
}

export function useMemorySession(options: MemorySessionOptions = {}) {
  const api = options.api ?? {
    start: startMemorySession,
    loadQuestion: fetchMemorySession,
    submit: submitStudyEvent,
    complete: completeMemorySession,
  }
  const now = options.now ?? (() => Date.now())

  const module = ref<MemoryModule | null>(null)
  const sessionId = ref<string | null>(null)
  const question = ref<StudyQuestion | null>(null)
  const feedback = ref<StudyFeedback | null>(null)
  const busy = ref(false)
  const finished = ref(false)
  const lastError = ref<unknown>(null)
  const lastRequestId = ref<string | null>(null)

  /** Timestamp the current card became visible, used for elapsed_ms only. */
  let cardShownAt = now()
  /** Key for the action currently in flight, so a retry after failure reuses it. */
  let pendingKey: string | null = null
  let pendingAction: string | null = null

  const hasSession = computed(() => sessionId.value !== null)
  const remaining = computed(() => question.value?.remaining ?? 0)

  function beginCard(): void {
    cardShownAt = now()
  }

  function elapsedMs(): number {
    return Math.max(0, now() - cardShownAt)
  }

  /**
   * Idempotency policy: the same logical action retried after a network failure
   * must reuse its key; a genuinely new action must rotate it. That prevents a
   * retried Good from being counted twice while still letting the learner retry.
   */
  function keyFor(action: string): string {
    if (pendingAction === action && pendingKey) {
      return pendingKey
    }
    pendingAction = action
    pendingKey = newIdempotencyKey()
    return pendingKey
  }

  function clearPendingKey(): void {
    pendingKey = null
    pendingAction = null
  }

  async function open(target: MemoryModule, existingSessionId?: string): Promise<void> {
    busy.value = true
    lastError.value = null
    feedback.value = null
    finished.value = false
    module.value = target

    try {
      if (existingSessionId) {
        sessionId.value = existingSessionId
      } else {
        const summary = await api.start(target)
        sessionId.value = summary.sessionId
        if (summary.remaining <= 0) {
          finished.value = true
          question.value = null
          return
        }
      }
      const next = await api.loadQuestion(sessionId.value as string, target)
      if (!next) {
        finished.value = true
        question.value = null
        return
      }
      question.value = next
      beginCard()
    } catch (error) {
      lastError.value = error
      question.value = null
      throw error
    } finally {
      busy.value = false
    }
  }

  /** Reload the current card from the server; used after a failed submission. */
  async function refreshQuestion(): Promise<void> {
    if (!sessionId.value || !module.value) {
      return
    }
    const next = await api.loadQuestion(sessionId.value, module.value)
    if (!next) {
      finished.value = true
      question.value = null
      return
    }
    question.value = next
    beginCard()
  }

  async function submit(event: StudyEventInput): Promise<StudyFeedback | null> {
    if (!sessionId.value || busy.value) {
      return null
    }
    busy.value = true
    lastError.value = null

    try {
      const key = keyFor(`${event.kind}:${'questionId' in event ? event.questionId : ''}`)
      const result = await api.submit(sessionId.value, event, key)
      feedback.value = result
      clearPendingKey()
      return result
    } catch (error) {
      // Keep the key so a retry is idempotent.
      lastError.value = error
      throw error
    } finally {
      busy.value = false
    }
  }

  /** Record that the learner saw the back, without advancing the queue. */
  async function recordReveal(questionId: string): Promise<void> {
    if (!sessionId.value || busy.value) return
    const key = keyFor(`flashcard-reveal:${questionId}`)
    try {
      await api.submit(
        sessionId.value,
        { kind: 'flashcard-reveal', questionId },
        key,
      )
      clearPendingKey()
      lastError.value = null
    } catch (error) {
      lastError.value = error
    }
  }

  async function rateFlashcard(questionId: string, rating: FlashcardRating): Promise<void> {
    const result = await submit({ kind: 'flashcard-rate', questionId, rating, elapsedMs: elapsedMs() })
    if (result) {
      await advanceAfterFeedback(result)
    }
  }

  async function answerChoice(questionId: string, optionId: string): Promise<StudyFeedback | null> {
    return submit({ kind: 'choice-answer', questionId, optionId, elapsedMs: elapsedMs() })
  }

  async function answerSpelling(questionId: string, answer: string): Promise<StudyFeedback | null> {
    return submit({ kind: 'spelling-answer', questionId, answer, elapsedMs: elapsedMs() })
  }

  /**
   * "已记住" during a session. Routed through the session event endpoint so the
   * server owns the mastery decision and can keep queue bookkeeping consistent;
   * nothing about stability or due dates is sent from the client.
   */
  async function markMastered(questionId: string): Promise<void> {
    const result = await submit({ kind: 'master-word', questionId, elapsedMs: elapsedMs() })
    if (result) {
      await advanceAfterFeedback(result)
    }
  }

  /**
   * Move to the next server-provided card. The frontend never decides that the
   * queue is empty on its own: `remaining === 0` and an empty read end it.
   */
  /** Continue after a paused (wrong) answer: move on using the last server feedback. */
  async function advance(): Promise<void> {
    if (feedback.value) {
      await advanceAfterFeedback(feedback.value)
    }
  }

  async function advanceAfterFeedback(result: StudyFeedback): Promise<void> {
    if (result.remaining <= 0) {
      finished.value = true
      question.value = null
      return
    }
    await refreshQuestion()
  }


  async function endSession(): Promise<void> {
    if (!sessionId.value) {
      return
    }
    busy.value = true
    try {
      await api.complete(sessionId.value)
      finished.value = true
      question.value = null
    } finally {
      busy.value = false
    }
  }

  function reset(): void {
    module.value = null
    sessionId.value = null
    question.value = null
    feedback.value = null
    finished.value = false
    lastError.value = null
    clearPendingKey()
  }

  return {
    module,
    sessionId,
    question,
    feedback,
    busy,
    finished,
    lastError,
    lastRequestId,
    hasSession,
    remaining,
    open,
    refreshQuestion,
    recordReveal,
    rateFlashcard,
    answerChoice,
    answerSpelling,
    advance,
    markMastered,
    endSession,
    reset,
  }
}
