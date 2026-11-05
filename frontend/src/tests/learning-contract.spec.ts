import { describe, expect, it } from 'vitest'
import {
  FROZEN_CONTRACT,
  contractCoordinateLabel,
  contractHelpers,
  isContractFrozen,
  parseLearningProfile,
  parseMemoryConfig,
  parseMistakes,
  parseStudyFeedback,
  parseStudyQuestion,
  parseTodayPlan,
  serializeHeartbeat,
  serializeMemoryConfig,
  serializeProfileUpdate,
  serializeStudyEvent,
} from '../api/contract-adapter'
import { defaultMemoryConfig, todayIsoDate } from '../lib/learning-validation'
import { ContractError } from '../api/errors'

const profilePayload = {
  daily_new_words: 20,
  daily_study_minutes: 30,
  department: '学习部',
  exam_date: '2027-06-01',
  learning_group: 'A 组',
  notification_preferences: {},
  onboarding_completed: true,
  target_exam: 'CET6',
  timezone: 'Asia/Shanghai',
  updated_at: '2026-10-23T01:00:00Z',
}

const configPayload = {
  flashcard_enabled: true,
  choice_enabled: false,
  spelling_enabled: true,
  preferences: { spelling_mode: 'first_letter', choice_prompt: 'definition' },
  updated_at: '2026-10-23T01:00:00Z',
}

const todayPayload = {
  active_minutes_today: 12,
  ai_practice: { reason: 'AI practice is not implemented in this milestone.', status: 'not_available' },
  calculation_version: 'plan:daily-plan-1.0.0|fsrs-6.3.2',
  due_reviews: { completed: 2, status: 'in_progress', target: 8 },
  extra_due_available: true,
  extra_due_count: 3,
  generated_at: '2026-10-23T01:00:00Z',
  goal_reached: false,
  items: [],
  local_date: '2026-10-23',
  new_word_reason: 'Only 6 unseen words were available.',
  new_words: { completed: 1, status: 'in_progress', target: 20 },
  status: 'in_progress',
  study_minutes_target: 30,
  wordbook_id: 'book-1',
  wordbook_name: 'CET-6 核心词',
}

function sessionPayload() {
  return {
    calculation_version: 'plan:daily-plan-1.0.0|fsrs-6.3.2',
    card: {
      cloze: null,
      module: 'choice',
      option_count: 3,
      options: ['有弹性的', '沉默的', '昂贵的'],
      part_of_speech: 'adj.',
      phonetic: '/rɪˈzɪliənt/',
      prompt: 'resilient',
      prompt_label: 'headword',
    },
    config_snapshot: { preferences: { spelling_mode: 'partial' } },
    ended_at: null,
    items_completed: 1,
    items_total: 4,
    local_date: '2026-10-23',
    module: 'choice',
    next_item: {
      again_count: 0,
      completed: false,
      entry_id: 'entry-1',
      good_count: 0,
      is_extra: false,
      item_id: 'item-1',
      last_rating: null,
      position: 1,
      reason: 'new',
      relearn_count: 0,
      word_state_id: 'state-1',
    },
    session_id: 'session-1',
    started_at: '2026-10-23T01:00:00Z',
    stats: {},
    status: 'active',
    wordbook_id: 'book-1',
    wordbook_name: 'CET-6 核心词',
  }
}

describe('frozen contract coordinates', () => {
  it('pins the exact A01-frozen SHA and OpenAPI coordinates', () => {
    expect(isContractFrozen()).toBe(true)
    expect(FROZEN_CONTRACT.contractSha).toBe('25ad69f3c2c9ad29c01df6afa88b87e18404361e')
    expect(FROZEN_CONTRACT.openapiSha256).toHaveLength(64)
    expect(FROZEN_CONTRACT.openapiSha256.startsWith('248ff876')).toBe(true)
    expect(FROZEN_CONTRACT.openapiSha256.endsWith('f57e7')).toBe(true)
    expect(FROZEN_CONTRACT.semanticSha256).toHaveLength(64)
    expect(FROZEN_CONTRACT.semanticSha256.startsWith('17ba6179')).toBe(true)
    expect(FROZEN_CONTRACT.semanticSha256.endsWith('03222')).toBe(true)
    expect(FROZEN_CONTRACT.pathCount).toBe(39)
    expect(FROZEN_CONTRACT.schemaCount).toBe(67)
    expect(contractCoordinateLabel()).toContain('25ad69f3c2c9')
  })
})

describe('profile and memory config', () => {
  it('maps the real profile fields and keeps config separate', () => {
    const config = parseMemoryConfig(configPayload)
    const profile = parseLearningProfile(profilePayload, config)
    expect(profile).toMatchObject({
      examTarget: 'CET6',
      examDate: '2027-06-01',
      dailyNewWords: 20,
      dailyMinutes: 30,
      department: '学习部',
      learningGroup: 'A 组',
      needsOnboarding: false,
    })
    expect(profile.memoryConfig.choice.enabled).toBe(false)
    expect(profile.memoryConfig.spelling.blankType).toBe('first_letter')
  })

  it('serializes only fields accepted by LearningProfilePatch', () => {
    const payload = serializeProfileUpdate({
      examTarget: 'CET4',
      examDate: null,
      dailyNewWords: 25,
      dailyMinutes: 45,
      memoryConfig: defaultMemoryConfig(),
      practicePoolTarget: 1,
      challengeGenerationTime: '06:30',
    }) as Record<string, unknown>
    expect(payload).toEqual({
      target_exam: 'CET4',
      exam_date: null,
      daily_new_words: 25,
      daily_study_minutes: 45,
      practice_pool_target: 1,
      challenge_generation_time: '06:30',
    })
    expect(payload).not.toHaveProperty('flashcard_enabled')
  })

  it('preserves unknown preference keys when saving memory config', () => {
    const config = parseMemoryConfig(configPayload)
    config.spelling.blankType = 'full'
    const payload = serializeMemoryConfig(config) as Record<string, unknown>
    expect(payload).toMatchObject({
      flashcard_enabled: true,
      choice_enabled: false,
      spelling_enabled: true,
      preferences: { spelling_mode: 'full', choice_prompt: 'definition' },
    })
  })

  it('clears the stored spelling mode when random is chosen again', () => {
    const config = parseMemoryConfig({ ...configPayload, preferences: { ...configPayload.preferences, spelling_mode: 'middle' } })
    config.spelling.blankType = null
    const payload = serializeMemoryConfig(config) as Record<string, unknown>
    expect((payload.preferences as Record<string, unknown>)).not.toHaveProperty('spelling_mode')
  })
})

describe('today, heartbeat and mistakes', () => {
  it('maps server progress and AI availability without inventing completion', () => {
    const plan = parseTodayPlan(todayPayload)
    expect(plan.newWords).toEqual({ completed: 1, target: 20 })
    expect(plan.dueReviews).toEqual({ completed: 2, target: 8 })
    expect(plan.minutes).toEqual({ active: 12, goal: 30 })
    expect(plan.extraDueCount).toBe(3)
    expect(plan.aiPractice.state).toBe('not_available')
    expect(plan.shortfallReason).toContain('6 unseen')
  })

  it('sends only the session id in a heartbeat', () => {
    expect(serializeHeartbeat({ sessionId: 'session-1' })).toEqual({ session_id: 'session-1' })
    expect(serializeHeartbeat({ sessionId: null })).toEqual({ session_id: null })
  })

  it('maps cursor-paginated mistakes and their entry ids', () => {
    const page = parseMistakes({
      has_more: true,
      items: [
        {
          again_count: 2,
          definition_zh: '有弹性的',
          entry_id: 'entry-1',
          headword: 'resilient',
          is_priority: true,
          last_again_at: '2026-10-23T01:00:00Z',
          phonetic: null,
          status: 'relearning',
          word_state_id: 'state-1',
        },
      ],
      next_cursor: 'cursor-2',
    })
    expect(page.items[0]).toMatchObject({
      entryId: 'entry-1',
      stateId: 'state-1',
      priorityReview: true,
      module: null,
      mistakeCount: 2,
    })
    expect(page.nextCursor).toBe('cursor-2')
    expect(page.hasMore).toBe(true)
  })
})

describe('session question and event mapping', () => {
  it('uses server option_count instead of a hard-coded four-option rule', () => {
    const question = parseStudyQuestion(sessionPayload(), 'choice')
    if (!question || question.kind !== 'choice') throw new Error('unexpected question kind')
    expect(question.optionCount).toBe(3)
    expect(question.options).toHaveLength(3)
    expect(JSON.stringify(question)).not.toMatch(/correct|answer_key|is_right/)
  })

  it('treats a completed queue as no next question instead of failing the contract', () => {
    const payload = sessionPayload() as Record<string, unknown>
    payload.next_item = null
    payload.card = null
    expect(parseStudyQuestion(payload, 'choice')).toBeNull()
  })

  it('rejects a payload whose option_count disagrees with options', () => {
    const payload = sessionPayload()
    payload.card.option_count = 4
    expect(() => parseStudyQuestion(payload, 'choice')).toThrow(ContractError)
  })

  it('maps the real event request and server-confirmed grading', () => {
    expect(
      serializeStudyEvent({
        kind: 'choice-answer',
        questionId: 'item-1',
        optionId: '有弹性的',
        elapsedMs: 2400,
      }),
    ).toEqual({ item_id: 'item-1', action: 'good', answer: '有弹性的', duration_ms: 2400 })

    const feedback = parseStudyFeedback({
      action: 'again',
      correct_answer: 'resilient',
      event_id: 'event-1',
      is_correct: false,
      item_completed: false,
      item_id: 'item-1',
      rating: 'again',
      session: { ...sessionPayload(), items_completed: 2 },
      session_completed: false,
    })
    expect(feedback.headline).toContain('错误')
    expect(feedback.detail).toContain('resilient')
    expect(feedback.remaining).toBe(2)
    expect(feedback.requeued).toBe(true)
  })
})

describe('contract helpers', () => {
  const endpoint = '/test'

  it('accepts the documented enum values and rejects others', () => {
    expect(contractHelpers.requireEnum('not_started', contractHelpers.TODAY_STATUSES, endpoint, 'status')).toBe(
      'not_started',
    )
    expect(() => contractHelpers.requireEnum('done', contractHelpers.TODAY_STATUSES, endpoint, 'status')).toThrow(
      ContractError,
    )
  })

  it('rejects non-integer numbers so counts cannot be fractional or NaN', () => {
    expect(contractHelpers.requireInt(3, endpoint, 'count')).toBe(3)
    expect(() => contractHelpers.requireInt(3.5, endpoint, 'count')).toThrow(ContractError)
    expect(() => contractHelpers.requireInt(Number.NaN, endpoint, 'count')).toThrow(ContractError)
  })

  it('rejects arrays where an object is required', () => {
    expect(() => contractHelpers.requireRecord([], endpoint, 'body')).toThrow(ContractError)
    expect(() => contractHelpers.requireRecord(null, endpoint, 'body')).toThrow(ContractError)
  })

  it('normalises optional strings to null rather than undefined', () => {
    expect(contractHelpers.optionalString(undefined, endpoint, 'x')).toBeNull()
    expect(() => contractHelpers.optionalString(3, endpoint, 'x')).toThrow(ContractError)
  })

  it('publishes the exact enums used by the frozen contract', () => {
    expect(contractHelpers.EXAM_TARGETS).toEqual(['CET4', 'CET6', 'POSTGRAD', 'IELTS', 'TOEFL'])
    expect(contractHelpers.MEMORY_MODULES).toEqual(['flashcard', 'choice', 'spelling'])
    expect(contractHelpers.BLANK_TYPES).toEqual(['full', 'partial', 'first_letter', 'middle'])
  })
})

describe('date helper', () => {
  it('formats the local calendar date without timezone drift', () => {
    expect(todayIsoDate(new Date(2026, 9, 23, 23, 30))).toBe('2026-10-23')
    expect(todayIsoDate(new Date(2026, 0, 1, 0, 5))).toBe('2026-01-01')
  })
})