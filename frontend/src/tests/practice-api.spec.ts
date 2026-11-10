import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { apiClient } from '../api/client'
import {
  buildPracticeRecordQuery,
  createPracticeSession,
  deletePracticeRecords,
  fetchPracticeUsage,
  getPracticeRecord,
  parsePracticeResult,
  parsePracticeSession,
  savePracticeDraft,
  submitPracticeSession,
} from '../api/practice'
import { ContractError } from '../api/errors'

const questionPayload = {
  id: 'q-1',
  position: 0,
  question_type: 'fill_blank',
  prompt: 'Choose the best answer',
  sentence: 'The team remained ____ under pressure.',
  sentence_zh: '团队在压力下仍然保持____。',
  article: null,
  article_zh: null,
  options: [
    { id: 'o-1', text: 'resilient', text_zh: '有韧性的' },
    { id: 'o-2', text: 'fragile', text_zh: '脆弱的' },
  ],
  source_text: null,
  source_language: null,
  target_language: null,
  requirements: [],
  target_entry_ids: ['entry-1'],
}

const sessionPayload = {
  id: 'session-1',
  practice_type: 'fill_blank',
  source: 'whole_book',
  difficulty: null,
  wordbook_id: 'book-1',
  status: 'ready',
  question_count: 1,
  generation_number: 1,
  draft_version: 2,
  draft_answers: { 'q-1': 'o-1' },
  questions: [questionPayload],
  job_status: 'succeeded',
  error_code: null,
  error_message: null,
  created_at: '2026-10-23T04:00:00Z',
  updated_at: '2026-10-23T04:01:00Z',
}

const resultPayload = {
  session_id: 'session-1',
  submission_id: 'submission-1',
  status: 'completed',
  score: 100,
  correct_count: 1,
  total_questions: 1,
  wrong_count: 0,
  questions: [{
    question_id: 'q-1',
    question_type: 'fill_blank',
    user_answer: 'o-1',
    is_correct: true,
    is_mistake: false,
    score: 100,
    correct_option_id: 'o-1',
    correct_option_text: 'resilient',
    explanation: 'Context points to resilience.',
    reference_content: null,
    dimensions: [],
    errors: [],
    suggestions: [],
  }],
  mistakes: [],
  error_code: null,
  error_message: null,
  submitted_at: '2026-10-23T04:02:00Z',
}

function jsonResponse(payload: unknown, status = 200, requestId = 'practice-req'): Response {
  return new Response(JSON.stringify(payload), {
    status,
    headers: { 'Content-Type': 'application/json', 'X-Request-ID': requestId },
  })
}

describe('practice API contract', () => {
  beforeEach(() => {
    apiClient.clearCredentials()
    localStorage.clear()
    sessionStorage.clear()
  })

  afterEach(() => vi.unstubAllGlobals())

  it('parses a public session and preserves server draft answers', () => {
    const session = parsePracticeSession(sessionPayload)
    expect(session).toMatchObject({
      id: 'session-1',
      status: 'ready',
      draftVersion: 2,
      questions: [expect.objectContaining({ questionType: 'fill_blank', options: expect.any(Array) })],
    })
    expect(session.draftAnswers['q-1']).toBe('o-1')
    expect(session.questions[0]).not.toHaveProperty('correctChoiceId')
  })

  it('accepts a mixed session type', () => {
    const session = parsePracticeSession({ ...sessionPayload, practice_type: 'mixed' })
    expect(session.practiceType).toBe('mixed')
  })

  it('rejects a pre-submit session that leaks private answer fields', () => {
    const leaked = {
      ...sessionPayload,
      questions: [{ ...questionPayload, correct_option_id: 'o-1', explanation: 'leaked' }],
    }
    expect(() => parsePracticeSession(leaked)).toThrow(ContractError)
  })

  it('creates with the documented payload and idempotency header', async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(sessionPayload, 202))
    vi.stubGlobal('fetch', fetchMock)
    const session = await createPracticeSession({
      practiceType: 'fill_blank',
      source: 'whole_book',
      count: 3,
      difficulty: null,
      wordbookId: 'book-1',
    }, 'practice-create-key')
    expect(session.id).toBe('session-1')
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit]
    expect(url).toBe('/api/v1/practice/sessions')
    expect((init.headers as Headers).get('Idempotency-Key')).toBe('practice-create-key')
    expect(JSON.parse(String(init.body))).toEqual({
      practice_type: 'fill_blank',
      source: 'whole_book',
      count: 3,
      difficulty: null,
      wordbook_id: 'book-1',
      translation_direction: null,
      writing_target_words: null,
    })
  })

  it('saves a versioned draft and submits all answers with stable keys', async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(jsonResponse({ session_id: 'session-1', draft_version: 3, answers: { 'q-1': 'o-1' }, saved_at: '2026-10-23T04:03:00Z' }))
      .mockResolvedValueOnce(jsonResponse({ session_id: 'session-1', submission_id: 'submission-1', status: 'completed', result: resultPayload, error_code: null, error_message: null }, 202))
    vi.stubGlobal('fetch', fetchMock)
    await savePracticeDraft('session-1', { version: 2, answers: { 'q-1': 'o-1' } })
    const submitted = await submitPracticeSession('session-1', [{ questionId: 'q-1', answer: 'o-1' }], 'submit-key')
    expect(submitted.result?.score).toBe(100)
    expect(JSON.parse(String((fetchMock.mock.calls[0][1] as RequestInit).body))).toEqual({ version: 2, answers: { 'q-1': 'o-1' } })
    const submitInit = fetchMock.mock.calls[1][1] as RequestInit
    expect((submitInit.headers as Headers).get('Idempotency-Key')).toBe('submit-key')
    expect(JSON.parse(String(submitInit.body))).toEqual({ answers: [{ question_id: 'q-1', answer: 'o-1' }] })
  })

  it('parses post-submit answer and explanation fields only after submission', () => {
    const result = parsePracticeResult(resultPayload)
    expect(result.questions[0]).toMatchObject({ gradedCorrect: true, correctChoiceId: 'o-1', explanation: expect.stringContaining('resilience') })
  })

  it('builds record filters and parses record detail', async () => {
    expect(buildPracticeRecordQuery({ practiceType: 'reading', source: 'today_new', offset: 20, limit: 10 }))
      .toBe('?practice_type=reading&source=today_new&offset=20&limit=10')
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse({
      id: 'session-1', practice_type: 'fill_blank', source: 'whole_book', difficulty: null,
      score: 100, correct_count: 1, total_questions: 1, wrong_count: 0,
      submitted_at: '2026-10-23T04:02:00Z', status: 'submitted', result: resultPayload,
    })))
    const detail = await getPracticeRecord('session-1')
    expect(detail.result?.totalQuestions).toBe(1)
  })

  it('bulk deletes only selected ids and parses aggregate usage', async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(jsonResponse({ deleted_count: 1, deleted_ids: ['session-1'] }))
      .mockResolvedValueOnce(jsonResponse({
        local_date: '2026-10-23',
        quotas: [{ quota_kind: 'question_generation', limit: 20, used: 1, reserved: 0, remaining: 19 }],
        concurrency: { limit: 2, in_use: 0 },
      }))
    vi.stubGlobal('fetch', fetchMock)
    const deleted = await deletePracticeRecords(['session-1'], 'delete-key')
    expect(deleted.deletedCount).toBe(1)
    const usage = await fetchPracticeUsage()
    expect(usage.quotas[0].remaining).toBe(19)
    const deleteInit = fetchMock.mock.calls[0][1] as RequestInit
    expect(deleteInit.method).toBe('DELETE')
    expect((deleteInit.headers as Headers).get('Idempotency-Key')).toBe('delete-key')
    expect(JSON.parse(String(deleteInit.body))).toEqual({ ids: ['session-1'] })
  })
})