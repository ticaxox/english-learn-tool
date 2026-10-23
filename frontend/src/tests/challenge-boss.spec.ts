import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { defineComponent, h } from 'vue'
import ChallengeBossPanel from '../components/ChallengeBossPanel.vue'
import { ApiError } from '../api/errors'

const challengeMocks = vi.hoisted(() => ({ submitChallengeBoss: vi.fn() }))
const practiceState = vi.hoisted(() => ({
  session: { value: null as unknown },
  loading: { value: false },
  generating: { value: false },
  error: { value: null as unknown },
  load: vi.fn(async () => undefined),
}))

vi.mock('../api/challenge', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../api/challenge')>()
  return { ...actual, ...challengeMocks }
})

vi.mock('../composables/usePracticeSession', () => ({
  usePracticeSession: () => ({
    session: practiceState.session,
    loading: practiceState.loading,
    generating: practiceState.generating,
    error: practiceState.error,
    load: practiceState.load,
  }),
}))

vi.mock('../components/PracticeQuestionCard.vue', () => ({
  default: defineComponent({
    props: ['question', 'modelValue', 'index', 'total'],
    emits: ['update:modelValue'],
    setup(props, { emit }) {
      return () => h('input', {
        class: 'question-answer',
        value: props.modelValue,
        onInput: (event: Event) => emit('update:modelValue', (event.target as HTMLInputElement).value),
      })
    },
  }),
}))

function makeQuestions(count = 5) {
  return Array.from({ length: count }, (_, index) => ({
    id: `q-${index + 1}`,
    position: index,
    questionType: 'fill_blank',
    prompt: `Question ${index + 1}`,
    sentence: `Sentence ${index + 1} ____.`,
    sentenceZh: null,
    article: null,
    articleZh: null,
    options: [],
    sourceText: null,
    sourceLanguage: null,
    targetLanguage: null,
    requirements: [],
    targetEntryIds: [],
  }))
}

function completedResult() {
  return {
    challengeId: 'challenge-1', nodeId: 'boss-1', status: 'completed' as const, score: 80, completed: true,
    submissionId: 'submission-1', result: { question_stats: { total: 5, correct: 4, mistakes: 1 } },
    errorCode: null, errorMessage: null, message: 'The final challenge is complete.',
  }
}

describe('challenge BOSS panel', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    practiceState.session.value = {
      id: 'boss-session-1', status: 'ready', questions: makeQuestions(), draftAnswers: {},
    }
    practiceState.loading.value = false
    practiceState.generating.value = false
    practiceState.error.value = null
    challengeMocks.submitChallengeBoss.mockResolvedValue(completedResult())
  })

  it('requires all server questions before submitting the real BOSS endpoint', async () => {
    const wrapper = mount(ChallengeBossPanel, { props: { challengeId: 'challenge-1', nodeId: 'boss-1', sessionId: 'boss-session-1' } })
    await flushPromises()
    const submit = wrapper.findAll('button').find((button) => button.text().includes('提交终点挑战'))!
    expect(submit.attributes('disabled')).toBeDefined()
    const inputs = wrapper.findAll('.question-answer')
    expect(inputs).toHaveLength(5)
    for (let index = 0; index < inputs.length; index += 1) await inputs[index].setValue(`answer-${index + 1}`)
    expect(submit.attributes('disabled')).toBeUndefined()
    await submit.trigger('click')
    await flushPromises()

    expect(challengeMocks.submitChallengeBoss).toHaveBeenCalledWith(
      'challenge-1', 'boss-1',
      expect.arrayContaining([{ questionId: 'q-1', answer: 'answer-1' }]),
      expect.any(String),
    )
    expect(wrapper.text()).toContain('得分：80')
    expect(wrapper.emitted('completed')).toHaveLength(1)
  })

  it('surfaces quota errors with request id and keeps the answer state', async () => {
    challengeMocks.submitChallengeBoss.mockRejectedValueOnce(
      new ApiError(429, 'AI_QUOTA_EXHAUSTED', 'Quota exhausted.', null, 'boss-429', true),
    )
    const wrapper = mount(ChallengeBossPanel, { props: { challengeId: 'challenge-1', nodeId: 'boss-1', sessionId: 'boss-session-1' } })
    await flushPromises()
    const inputs = wrapper.findAll('.question-answer')
    for (let index = 0; index < inputs.length; index += 1) await inputs[index].setValue(`answer-${index + 1}`)
    await wrapper.findAll('button').find((button) => button.text().includes('提交终点挑战'))!.trigger('click')
    await flushPromises()

    expect(wrapper.text()).toContain('请求过于频繁')
    expect(wrapper.text()).toContain('boss-429')
    expect((wrapper.findAll('.question-answer')[0].element as HTMLInputElement).value).toBe('answer-1')
  })

  it('does not claim completion for a scoring response', async () => {
    challengeMocks.submitChallengeBoss.mockResolvedValueOnce({
      ...completedResult(), status: 'scoring', score: null, completed: false, result: null, message: 'The final challenge is being scored.',
    })
    const wrapper = mount(ChallengeBossPanel, { props: { challengeId: 'challenge-1', nodeId: 'boss-1', sessionId: 'boss-session-1' } })
    await flushPromises()
    const inputs = wrapper.findAll('.question-answer')
    for (let index = 0; index < inputs.length; index += 1) await inputs[index].setValue(`answer-${index + 1}`)
    await wrapper.findAll('button').find((button) => button.text().includes('提交终点挑战'))!.trigger('click')
    await flushPromises()
    expect(wrapper.text()).toContain('正在评分')
    expect(wrapper.emitted('completed')).toBeUndefined()
  })
})

