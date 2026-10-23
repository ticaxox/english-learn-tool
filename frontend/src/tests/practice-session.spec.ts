import { afterEach, describe, expect, it, vi } from 'vitest'
import { usePracticeSession, type PracticeSessionApi } from '../composables/usePracticeSession'
import { ApiError } from '../api/errors'
import type { PracticeResult, PracticeSession } from '../api/practice'

const baseSession: PracticeSession = {
  id: 'session-1', practiceType: 'fill_blank', source: 'whole_book', difficulty: null,
  wordbookId: 'book-1', status: 'generating', questionCount: 3, generationNumber: 1,
  draftVersion: 0, draftAnswers: {}, questions: [], jobStatus: 'running', errorCode: null,
  errorMessage: null, createdAt: '2026-10-23T04:00:00Z', updatedAt: '2026-10-23T04:00:00Z',
}
const readySession: PracticeSession = {
  ...baseSession, status: 'ready', jobStatus: 'succeeded', questions: [
    { id: 'q-1', position: 0, questionType: 'fill_blank', prompt: 'Prompt', sentence: 'Sentence', sentenceZh: null, article: null, articleZh: null, options: [{ id: 'o-1', text: 'A', textZh: null }], sourceText: null, sourceLanguage: null, targetLanguage: null, requirements: [], targetEntryIds: [] },
  ],
}
const result: PracticeResult = {
  sessionId: 'session-1', submissionId: 'submission-1', status: 'completed', score: 100,
  correctCount: 1, totalQuestions: 1, wrongCount: 0, questions: [], mistakes: [],
  errorCode: null, errorMessage: null, submittedAt: '2026-10-23T04:03:00Z',
}
type MockPracticeApi = { [K in keyof PracticeSessionApi]: PracticeSessionApi[K] & ReturnType<typeof vi.fn> }

function makeApi(): MockPracticeApi {
  return {
    load: vi.fn(async () => baseSession),
    start: vi.fn(async () => readySession),
    saveDraft: vi.fn(async () => ({ sessionId: 'session-1', draftVersion: 1, answers: { 'q-1': 'o-1' }, savedAt: '2026-10-23T04:02:00Z' })),
    regenerate: vi.fn(async () => baseSession),
    submit: vi.fn(async () => ({ sessionId: 'session-1', submissionId: 'submission-1', status: 'completed' as const, result, errorCode: null, errorMessage: null })),
    result: vi.fn(async () => result),
  }
}

afterEach(() => vi.useRealTimers())

describe('practice session orchestration', () => {
  it('polls a 202 generation until the server reports ready', async () => {
    vi.useFakeTimers()
    const api = makeApi()
    api.load.mockResolvedValueOnce(baseSession).mockResolvedValueOnce(readySession)
    const practice = usePracticeSession('session-1', { api, pollIntervalMs: 100 })
    await practice.load()
    expect(practice.session.value?.status).toBe('generating')
    await vi.advanceTimersByTimeAsync(100)
    await vi.runOnlyPendingTimersAsync()
    expect(practice.session.value?.status).toBe('ready')
    expect(api.start).toHaveBeenCalledWith('session-1')
  })

  it('restores a server draft and saves a new version', async () => {
    const api = makeApi()
    api.load.mockResolvedValueOnce({ ...readySession, draftVersion: 2, draftAnswers: { 'q-1': 'o-1' } })
    api.start.mockResolvedValueOnce({ ...readySession, draftVersion: 2, draftAnswers: { 'q-1': 'o-1' } })
    const practice = usePracticeSession('session-1', { api })
    await practice.load()
    expect(practice.session.value?.draftAnswers['q-1']).toBe('o-1')
    await practice.saveDraft({ 'q-1': 'o-2' })
    expect(api.saveDraft).toHaveBeenCalledWith('session-1', { version: 2, answers: { 'q-1': 'o-2' } })
    expect(practice.session.value?.draftVersion).toBe(1)
  })

  it('surfaces draft version conflicts without overwriting local answers', async () => {
    const api = makeApi()
    api.load.mockResolvedValueOnce(readySession)
    api.saveDraft.mockRejectedValueOnce(new ApiError(409, 'PRACTICE_DRAFT_VERSION_CONFLICT', 'The draft changed.', { current_version: 4 }, 'draft-conflict', false))
    const practice = usePracticeSession('session-1', { api })
    await practice.load()
    await practice.saveDraft({ 'q-1': 'local answer' })
    expect(practice.draftError.value).toMatchObject({ code: 'PRACTICE_DRAFT_VERSION_CONFLICT' })
  })

  it('regenerates only through the server and resumes polling', async () => {
    const api = makeApi()
    api.load.mockResolvedValueOnce(readySession)
    const practice = usePracticeSession('session-1', { api, pollIntervalMs: 100 })
    await practice.load()
    await practice.regenerate('regen-key')
    expect(api.regenerate).toHaveBeenCalledWith('session-1', 'regen-key')
    expect(practice.session.value?.status).toBe('generating')
  })

  it('shows an objective result immediately after submission', async () => {
    const api = makeApi()
    api.load.mockResolvedValueOnce(readySession)
    const practice = usePracticeSession('session-1', { api })
    await practice.load()
    await practice.submit([{ questionId: 'q-1', answer: 'o-1' }], 'submit-key')
    expect(api.submit).toHaveBeenCalledWith('session-1', [{ questionId: 'q-1', answer: 'o-1' }], 'submit-key')
    expect(practice.result.value?.score).toBe(100)
  })

  it('polls subjective scoring without inventing an intermediate score', async () => {
    vi.useFakeTimers()
    const api = makeApi()
    api.load.mockResolvedValueOnce(readySession)
    api.submit.mockResolvedValueOnce({ sessionId: 'session-1', submissionId: 'submission-1', status: 'scoring', result: null, errorCode: null, errorMessage: null })
    api.result.mockResolvedValueOnce({ ...result, status: 'scoring', score: null, correctCount: null, wrongCount: null, questions: [], submittedAt: null }).mockResolvedValueOnce(result)
    const practice = usePracticeSession('session-1', { api, pollIntervalMs: 100 })
    await practice.load()
    const pending = practice.submit([{ questionId: 'q-1', answer: 'o-1' }], 'submit-key')
    await Promise.resolve()
    await Promise.resolve()
    expect(practice.result.value?.status).toBe('scoring')
    await vi.advanceTimersByTimeAsync(100)
    await vi.runOnlyPendingTimersAsync()
    await pending
    expect(practice.result.value?.status).toBe('completed')
    expect(practice.result.value?.score).toBe(100)
  })

  it('keeps generation failures visible instead of producing placeholder questions', async () => {
    const api = makeApi()
    api.load.mockResolvedValueOnce({ ...baseSession, status: 'failed', errorCode: 'AI_PROVIDER_UNAVAILABLE', errorMessage: 'Provider unavailable.' })
    const practice = usePracticeSession('session-1', { api })
    await practice.load()
    expect(practice.session.value?.status).toBe('failed')
    expect(practice.session.value?.questions).toEqual([])
  })
})