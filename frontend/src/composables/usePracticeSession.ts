import { computed, getCurrentInstance, onUnmounted, ref } from 'vue'
import {
  getPracticeResult,
  getPracticeSession,
  regeneratePracticeSession,
  savePracticeDraft,
  startPracticeSession,
  submitPracticeSession,
  type PracticeAnswerInput,
  type PracticeDraftResult,
  type PracticeResult,
  type PracticeSession,
  type PracticeSubmitResponse,
} from '../api/practice'

export interface PracticeSessionApi {
  load: (sessionId: string) => Promise<PracticeSession>
  start: (sessionId: string) => Promise<PracticeSession>
  saveDraft: (sessionId: string, input: { version: number; answers: Record<string, string> }) => Promise<PracticeDraftResult>
  regenerate: (sessionId: string, key: string) => Promise<PracticeSession>
  submit: (sessionId: string, answers: PracticeAnswerInput[], key: string) => Promise<PracticeSubmitResponse>
  result: (sessionId: string) => Promise<PracticeResult>
}

export interface PracticeSessionOptions {
  api?: PracticeSessionApi
  pollIntervalMs?: number
  maxPolls?: number
}

export function usePracticeSession(sessionId: string, options: PracticeSessionOptions = {}) {
  const api = options.api ?? {
    load: getPracticeSession,
    start: startPracticeSession,
    saveDraft: savePracticeDraft,
    regenerate: regeneratePracticeSession,
    submit: submitPracticeSession,
    result: getPracticeResult,
  }
  const pollIntervalMs = options.pollIntervalMs ?? 1500
  const maxPolls = options.maxPolls ?? 120

  const session = ref<PracticeSession | null>(null)
  const result = ref<PracticeResult | null>(null)
  const loading = ref(false)
  const polling = ref(false)
  const busy = ref(false)
  const draftSaving = ref(false)
  const error = ref<unknown>(null)
  const draftError = ref<unknown>(null)
  const submitError = ref<unknown>(null)
  const lastRequestId = ref<string | null>(null)

  let timer: number | null = null
  let pollCount = 0
  let started = false
  let disposed = false

  const ready = computed(() => session.value?.status === 'ready')
  const generating = computed(() => session.value?.status === 'generating')

  function clearTimer(): void {
    if (timer !== null) {
      window.clearTimeout(timer)
      timer = null
    }
  }

  function schedulePoll(): void {
    if (disposed || timer !== null) return
    timer = window.setTimeout(() => {
      timer = null
      void pollSession()
    }, pollIntervalMs)
  }

  async function pollSession(): Promise<void> {
    if (disposed || !generating.value) {
      polling.value = false
      return
    }
    pollCount += 1
    if (pollCount > maxPolls) {
      polling.value = false
      error.value = new Error('练习生成等待超时。页面不会伪造题目，请稍后刷新或重新创建。')
      return
    }
    polling.value = true
    try {
      const next = await api.load(sessionId)
      session.value = next
      lastRequestId.value = null
      if (next.status === 'generating') {
        schedulePoll()
        return
      }
      polling.value = false
      if (next.status === 'ready' && !started) {
        started = true
        try {
          session.value = await api.start(sessionId)
        } catch {
          // Starting is an event marker; a failure is visible through the next
          // real API operation and must not hide the ready questions.
        }
      }
      if (next.status === 'submitted') {
        await loadResult()
      }
    } catch (requestError) {
      polling.value = false
      error.value = requestError
    }
  }

  async function load(): Promise<void> {
    loading.value = true
    error.value = null
    clearTimer()
    pollCount = 0
    try {
      const next = await api.load(sessionId)
      session.value = next
      if (next.status === 'generating') {
        polling.value = true
        schedulePoll()
      } else if (next.status === 'ready' && !started) {
        started = true
        try {
          session.value = await api.start(sessionId)
        } catch {
          // See pollSession: the ready payload remains usable.
        }
      } else if (next.status === 'submitted') {
        await loadResult()
      }
    } catch (requestError) {
      error.value = requestError
      session.value = null
    } finally {
      loading.value = false
    }
  }

  async function loadResult(): Promise<void> {
    try {
      result.value = await api.result(sessionId)
      if (result.value.status === 'scoring') {
        pollCount = 0
        await pollResult()
      }
    } catch (requestError) {
      error.value = requestError
    }
  }

  async function saveDraft(answers: Record<string, string>): Promise<PracticeDraftResult | null> {
    if (!session.value || draftSaving.value || session.value.status !== 'ready') return null
    draftSaving.value = true
    draftError.value = null
    try {
      const saved = await api.saveDraft(sessionId, {
        version: session.value.draftVersion,
        answers,
      })
      session.value = {
        ...session.value,
        draftVersion: saved.draftVersion,
        draftAnswers: saved.answers,
      }
      return saved
    } catch (requestError) {
      draftError.value = requestError
      return null
    } finally {
      draftSaving.value = false
    }
  }

  async function regenerate(key: string): Promise<void> {
    if (busy.value) return
    busy.value = true
    error.value = null
    try {
      result.value = null
      pollCount = 0
      session.value = await api.regenerate(sessionId, key)
      if (session.value.status === 'generating') {
        polling.value = true
        schedulePoll()
      }
    } catch (requestError) {
      error.value = requestError
    } finally {
      busy.value = false
    }
  }

  async function submit(answers: PracticeAnswerInput[], key: string): Promise<PracticeSubmitResponse | null> {
    if (busy.value) return null
    busy.value = true
    submitError.value = null
    error.value = null
    try {
      const response = await api.submit(sessionId, answers, key)
      if (response.result) {
        result.value = response.result
      } else if (response.status === 'scoring') {
        pollCount = 0
        await pollResult()
      } else if (response.status === 'failed') {
        submitError.value = new Error(response.errorMessage || 'AI 评分失败，未生成默认分数。')
      }
      return response
    } catch (requestError) {
      submitError.value = requestError
      return null
    } finally {
      busy.value = false
    }
  }

  async function pollResult(): Promise<void> {
    polling.value = true
    try {
      while (!disposed && pollCount < maxPolls) {
        pollCount += 1
        const next = await api.result(sessionId)
        result.value = next
        if (next.status === 'completed' || next.status === 'failed') {
          if (next.status === 'failed') {
            submitError.value = new Error(next.errorMessage || 'AI 评分失败，未生成默认分数。')
          }
          return
        }
        await new Promise<void>((resolve) => {
          timer = window.setTimeout(() => {
            timer = null
            resolve()
          }, pollIntervalMs)
        })
      }
      submitError.value = new Error('评分等待超时。页面不会显示半成品分数，请稍后刷新结果。')
    } catch (requestError) {
      submitError.value = requestError
    } finally {
      polling.value = false
    }
  }

  function dispose(): void {
    disposed = true
    clearTimer()
  }

  if (getCurrentInstance()) onUnmounted(dispose)

  return {
    session,
    result,
    loading,
    polling,
    busy,
    draftSaving,
    error,
    draftError,
    submitError,
    lastRequestId,
    ready,
    generating,
    load,
    refresh: load,
    saveDraft,
    regenerate,
    submit,
    pollResult,
    dispose,
  }
}