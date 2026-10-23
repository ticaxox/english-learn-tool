import { describe, expect, it, vi } from 'vitest'
import { useMemorySession } from '../composables/useMemorySession'
import type {
  MemoryModule,
  SessionSummary,
  StudyEventInput,
  StudyFeedback,
  StudyQuestion,
} from '../types/learning'

function card(remaining = 3): StudyQuestion {
  return {
    kind: 'flashcard',
    questionId: 'q-1',
    wordbookId: 'book-1',
    entryId: 'entry-1',
    front: 'probably',
    back: '很可能',
    phonetic: null,
    partOfSpeech: null,
    example: null,
    remaining,
  }
}

function feedback(remaining: number, requeued = false): StudyFeedback {
  return {
    headline: '服务端已记录',
    detail: null,
    removed: false,
    requeued,
    remaining,
    sessionCompleted: remaining === 0,
  }
}

const summary: SessionSummary = {
  sessionId: 'session-1',
  module: 'flashcard',
  remaining: 3,
  completed: 0,
  startedAt: '2026-10-23T00:00:00Z',
}

function makeApi() {
  return {
    start: vi.fn(async (_module: MemoryModule) => summary),
    loadQuestion: vi.fn(async (_sessionId: string, _module: MemoryModule) => card()),
    submit: vi.fn(async (_sessionId: string, _event: StudyEventInput, _key: string) => feedback(2)),
    complete: vi.fn(async (_sessionId: string) => undefined),
  }
}

describe('memory session orchestration', () => {
  it('starts or resumes the server session, then loads the server card', async () => {
    const api = makeApi()
    const session = useMemorySession({ api })

    await session.open('flashcard')

    expect(api.start).toHaveBeenCalledWith('flashcard')
    expect(api.loadQuestion).toHaveBeenCalledWith('session-1', 'flashcard')
    expect(session.sessionId.value).toBe('session-1')
    expect(session.question.value?.kind).toBe('flashcard')
  })

  it('resumes an existing session without creating a second one', async () => {
    const api = makeApi()
    const session = useMemorySession({ api })

    await session.open('flashcard', 'session-existing')

    expect(api.start).not.toHaveBeenCalled()
    expect(api.loadQuestion).toHaveBeenCalledWith('session-existing', 'flashcard')
  })

  it('records a reveal without advancing the server queue', async () => {
    const api = makeApi()
    const session = useMemorySession({ api })
    await session.open('flashcard')
    await session.recordReveal('q-1')

    const [, event] = api.submit.mock.calls[0]
    expect(event).toMatchObject({ kind: 'flashcard-reveal', questionId: 'q-1' })
    expect(api.loadQuestion).toHaveBeenCalledTimes(1)
  })

  it('submits a rated flashcard with elapsed time, not a computed grade', async () => {
    let clock = 1000
    const api = makeApi()
    const session = useMemorySession({ api, now: () => clock })

    await session.open('flashcard')
    clock = 4200
    await session.rateFlashcard('q-1', 'good')

    const [, event] = api.submit.mock.calls[0]
    expect(event).toMatchObject({ kind: 'flashcard-rate', questionId: 'q-1', rating: 'good' })
    expect(event).toHaveProperty('elapsedMs', 3200)
    // The client must never send a stability/due/state field.
    expect(JSON.stringify(event)).not.toMatch(/stability|difficulty|due|state/)
  })

  it('reuses the idempotency key when the same action is retried', async () => {
    const api = makeApi()
    api.submit
      .mockRejectedValueOnce(new Error('network down'))
      .mockResolvedValueOnce(feedback(2))

    const session = useMemorySession({ api })
    await session.open('flashcard')

    await expect(session.rateFlashcard('q-1', 'good')).rejects.toThrow('network down')
    await session.rateFlashcard('q-1', 'good')

    const firstKey = api.submit.mock.calls[0][2]
    const secondKey = api.submit.mock.calls[1][2]
    expect(firstKey).toBe(secondKey)
  })

  it('rotates the idempotency key for a genuinely different action', async () => {
    const api = makeApi()
    const session = useMemorySession({ api })
    await session.open('flashcard')

    await session.rateFlashcard('q-1', 'good')
    await session.rateFlashcard('q-2', 'again')

    const firstKey = api.submit.mock.calls[0][2]
    const secondKey = api.submit.mock.calls[1][2]
    expect(firstKey).not.toBe(secondKey)
  })

  it('advances to the next server card after a successful action', async () => {
    const api = makeApi()
    api.loadQuestion
      .mockResolvedValueOnce(card(3))
      .mockResolvedValueOnce(card(2))

    const session = useMemorySession({ api })
    await session.open('flashcard')
    await session.rateFlashcard('q-1', 'good')

    expect(api.loadQuestion).toHaveBeenCalledTimes(2)
    expect(session.question.value?.remaining).toBe(2)
    expect(session.finished.value).toBe(false)
  })

  it('finishes only when the server reports no remaining cards', async () => {
    const api = makeApi()
    api.submit.mockResolvedValueOnce(feedback(0))

    const session = useMemorySession({ api })
    await session.open('flashcard')
    await session.rateFlashcard('q-1', 'good')

    expect(session.finished.value).toBe(true)
    expect(session.question.value).toBeNull()
  })

  it('surfaces a requeued card without locally deciding the queue', async () => {
    const api = makeApi()
    api.submit.mockResolvedValueOnce(feedback(1, true))

    const session = useMemorySession({ api })
    await session.open('flashcard')
    await session.rateFlashcard('q-1', 'again')

    expect(session.feedback.value?.requeued).toBe(true)
    expect(session.finished.value).toBe(false)
  })

  it('does not submit twice while a submission is in flight', async () => {
    const api = makeApi()
    let release: (() => void) | null = null
    api.submit.mockImplementation(
      () => new Promise<StudyFeedback>((resolve) => {
        release = () => resolve(feedback(2))
      }),
    )

    const session = useMemorySession({ api })
    await session.open('flashcard')

    const first = session.rateFlashcard('q-1', 'good')
    const second = session.rateFlashcard('q-1', 'good')
    release!()
    await Promise.all([first, second])

    expect(api.submit).toHaveBeenCalledTimes(1)
  })

  it('keeps the server error visible when a submission fails', async () => {
    const api = makeApi()
    api.submit.mockRejectedValueOnce(new Error('409 conflict'))

    const session = useMemorySession({ api })
    await session.open('flashcard')
    await expect(session.rateFlashcard('q-1', 'good')).rejects.toThrow('409 conflict')

    expect(session.lastError.value).toBeInstanceOf(Error)
  })

  it('ends the session through the server without marking targets complete', async () => {
    const api = makeApi()
    const session = useMemorySession({ api })
    await session.open('flashcard')

    await session.endSession()

    expect(api.complete).toHaveBeenCalledWith('session-1')
    expect(session.finished.value).toBe(true)
  })

  it('sends choice answers by option id only', async () => {
    const api = makeApi()
    const session = useMemorySession({ api })
    await session.open('choice')

    await session.answerChoice('q-9', 'o-3')

    const [, event] = api.submit.mock.calls[0]
    expect(event).toMatchObject({ kind: 'choice-answer', questionId: 'q-9', optionId: 'o-3' })
    expect(JSON.stringify(event)).not.toMatch(/correct|answer_key|is_right/)
  })

  it('sends the spelling answer verbatim for the server to grade', async () => {
    const api = makeApi()
    const session = useMemorySession({ api })
    await session.open('spelling')

    await session.answerSpelling('q-5', 'opportunity')

    const [, event] = api.submit.mock.calls[0]
    expect(event).toMatchObject({ kind: 'spelling-answer', questionId: 'q-5', answer: 'opportunity' })
  })

  it('routes "already known" through the session event endpoint', async () => {
    const api = makeApi()
    const session = useMemorySession({ api })
    await session.open('flashcard')

    await session.markMastered('q-1')

    const [, event] = api.submit.mock.calls[0]
    expect(event).toMatchObject({ kind: 'master-word', questionId: 'q-1' })
  })
})
