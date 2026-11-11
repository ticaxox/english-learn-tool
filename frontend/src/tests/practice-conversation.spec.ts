import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import PracticeConversation from '../components/PracticeConversation.vue'
import type { PracticeConversationTurn, PracticeQuestion } from '../api/practice'

const practiceMocks = vi.hoisted(() => ({
  listConversationTurns: vi.fn(),
  postConversationTurn: vi.fn(),
}))

vi.mock('../api/practice', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../api/practice')>()
  return { ...actual, ...practiceMocks }
})

const question: PracticeQuestion = {
  id: 'q-1', position: 0, questionType: 'conversation', prompt: null, sentence: null, sentenceZh: null,
  article: null, articleZh: null, options: [],
  sourceText: null, sourceLanguage: null, targetLanguage: null, requirements: [], targetEntryIds: [],
  targetWords: ['resilient'], sourceCitation: null,
  topic: 'A weekend hike', topicZh: '一次周末徒步',
  role: 'A friendly guide at the trailhead', roleZh: ' trailhead 的向导',
  scenario: 'You meet at the trailhead.', scenarioZh: '你们在登山口相遇。',
  turns: [{ id: 't-1', line: 'Morning! Ready to head up?', lineZh: '早上好！准备出发了吗？', intent: 'greet the learner' }],
}

function turn(overrides: Partial<PracticeConversationTurn>): PracticeConversationTurn {
  return {
    id: 'turn-1', sequence: 0, speaker: 'guide', line: 'Morning! Ready to head up?',
    lineZh: '早上好！准备出发了吗？', intent: 'greet the learner', createdAt: null,
    ...overrides,
  }
}

describe('conversation practice', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    practiceMocks.listConversationTurns.mockResolvedValue([turn({})])
    practiceMocks.postConversationTurn.mockResolvedValue({
      turn: turn({ id: 'turn-2', sequence: 1, line: '', intent: null }),
      jobId: 'job-1',
      status: 'queued',
    })
  })

  it('shows the topic, the character and the opening line', async () => {
    const wrapper = mount(PracticeConversation, { props: { sessionId: 'session-1', question } })
    await flushPromises()
    expect(wrapper.text()).toContain('A weekend hike')
    expect(wrapper.text()).toContain('一次周末徒步')
    expect(wrapper.text()).toContain('A friendly guide at the trailhead')
    expect(wrapper.text()).toContain('Morning! Ready to head up?')
    // The word the learner should reach for is on the table.
    expect(wrapper.text()).toContain('resilient')
  })

  it('sends what the learner typed and shows it in the talk', async () => {
    const wrapper = mount(PracticeConversation, { props: { sessionId: 'session-1', question } })
    await flushPromises()
    await wrapper.get('textarea').setValue('Yes, I brought water.')
    await wrapper.get('form').trigger('submit')
    await flushPromises()
    expect(practiceMocks.postConversationTurn).toHaveBeenCalledWith(
      'session-1', 'Yes, I brought water.', expect.any(String),
    )
    expect(wrapper.text()).toContain('Yes, I brought water.')
  })

  it('hands the learner line to the session as the answer', async () => {
    const wrapper = mount(PracticeConversation, { props: { sessionId: 'session-1', question } })
    await flushPromises()
    await wrapper.get('textarea').setValue('Yes, I brought water.')
    await wrapper.get('form').trigger('submit')
    await flushPromises()
    expect(wrapper.emitted('answer')).toEqual([['Yes, I brought water.']])
  })

  it('will not send an empty line', async () => {
    const wrapper = mount(PracticeConversation, { props: { sessionId: 'session-1', question } })
    await flushPromises()
    const send = wrapper.get('.practice-conversation__send')
    expect(send.attributes('disabled')).toBeDefined()
    await wrapper.get('form').trigger('submit')
    await flushPromises()
    expect(practiceMocks.postConversationTurn).not.toHaveBeenCalled()
  })

  it('shows the guide answering once the line arrives', async () => {
    vi.useFakeTimers()
    try {
      practiceMocks.listConversationTurns
        .mockResolvedValueOnce([turn({})])
        .mockResolvedValue([
          turn({}),
          turn({ id: 'turn-2', sequence: 1, line: 'Good, water is heavy. Shall we start?', lineZh: '好，水很重。出发吗？', intent: 'move the talk on' }),
        ])
      const wrapper = mount(PracticeConversation, { props: { sessionId: 'session-1', question } })
      await flushPromises()
      await wrapper.get('textarea').setValue('Yes, I brought water.')
      await wrapper.get('form').trigger('submit')
      await flushPromises()
      await vi.advanceTimersByTimeAsync(1200)
      await flushPromises()
      expect(wrapper.text()).toContain('Shall we start?')
    } finally {
      vi.useRealTimers()
    }
  })

  it('accepts a guide turn the model has not written yet', async () => {
    // The guide's line arrives later than the row that holds it, so the
    // client has to cope with an empty one.
    practiceMocks.listConversationTurns.mockResolvedValue([
      turn({}),
      turn({ id: 'turn-2', sequence: 1, line: '', lineZh: null, intent: null }),
    ])
    const wrapper = mount(PracticeConversation, { props: { sessionId: 'session-1', question } })
    await flushPromises()
    expect(wrapper.find('.practice-conversation__error').exists()).toBe(false)
    // An empty bubble would be a blank line in the talk, so it stays hidden.
    const bubbles = wrapper.findAll('.practice-conversation__bubble')
    expect(bubbles).toHaveLength(2)
    expect(bubbles[1].isVisible()).toBe(false)
  })

  it('tells the learner when the guide stays silent', async () => {
    vi.useFakeTimers()
    try {
      const wrapper = mount(PracticeConversation, { props: { sessionId: 'session-1', question } })
      await flushPromises()
      await wrapper.get('textarea').setValue('Hello?')
      await wrapper.get('form').trigger('submit')
      await flushPromises()
      // The guide never answers; the wait is bounded.
      for (let step = 0; step < 31; step += 1) {
        await vi.advanceTimersByTimeAsync(1000)
      }
      await flushPromises()
      expect(wrapper.text()).toContain('没有接上话')
    } finally {
      vi.useRealTimers()
    }
  })
})
