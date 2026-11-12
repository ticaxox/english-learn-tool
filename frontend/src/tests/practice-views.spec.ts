import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createMemoryHistory, createRouter } from 'vue-router'
import { defineComponent, h } from 'vue'
import PracticeHubView from '../views/PracticeHubView.vue'
import PracticeRecordsView from '../views/PracticeRecordsView.vue'
import PracticeQuestionCard from '../components/PracticeQuestionCard.vue'
import PracticeResultView from '../components/PracticeResultView.vue'
import type { PracticeQuestion, PracticeRecordPage, PracticeResult, PracticeSession, PracticeUsage } from '../api/practice'
import { ApiError } from '../api/errors'
import type { WordbookListPage } from '../api/wordbooks'

const practiceMocks = vi.hoisted(() => ({
  createPracticeSession: vi.fn(),
  fetchPracticeUsage: vi.fn(),
  listPracticeRecords: vi.fn(),
  listPracticeMistakes: vi.fn(),
  getPracticeRecord: vi.fn(),
  deletePracticeRecords: vi.fn(),
}))
const wordbookMocks = vi.hoisted(() => ({ listWordbooks: vi.fn() }))

vi.mock('../api/practice', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../api/practice')>()
  return { ...actual, ...practiceMocks }
})
vi.mock('../api/wordbooks', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../api/wordbooks')>()
  return { ...actual, ...wordbookMocks }
})

const StubPage = defineComponent({ render: () => h('div') })
function makeRouter() {
  return createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/practice', name: 'practice', component: StubPage },
      { path: '/practice/records', name: 'practice-records', component: StubPage },
      { path: '/practice/mistakes', name: 'practice-mistakes', component: StubPage },
      { path: '/practice/:sessionId', name: 'practice-session', component: StubPage },
      { path: '/wordbooks', name: 'wordbooks', component: StubPage },
      { path: '/memory', name: 'memory', component: StubPage },
    ],
  })
}
async function mountRoute(component: Parameters<typeof mount>[0], path: string, props = {}) {
  const router = makeRouter()
  await router.push(path)
  await router.isReady()
  const wrapper = mount(component, { props, global: { plugins: [router] } })
  await flushPromises()
  return { wrapper, router }
}

const session: PracticeSession = {
  id: 'session-1', practiceType: 'fill_blank', source: 'today_new', difficulty: null, wordbookId: null,
  translationDirection: null, writingTargetWords: null,
  status: 'generating', questionCount: 5, generationNumber: 1, draftVersion: 0, draftAnswers: {},
  questions: [], jobStatus: 'queued', errorCode: null, errorMessage: null,
  createdAt: '2026-10-23T04:00:00Z', updatedAt: '2026-10-23T04:00:00Z',
}
const usage: PracticeUsage = {
  localDate: '2026-10-23',
  quotas: [{ quotaKind: 'question_generation', limit: 20, used: 1, reserved: 0, remaining: 19 }, { quotaKind: 'subjective_grading', limit: 50, used: 0, reserved: 0, remaining: 50 }],
  concurrency: { limit: 2, inUse: 0 },
}
const recordPage: PracticeRecordPage = {
  items: [{ id: 'record-1', practiceType: 'fill_blank', source: 'whole_book', difficulty: null, score: 100, correctCount: 1, totalQuestions: 1, wrongCount: 0, submittedAt: '2026-10-23T04:02:00Z', status: 'submitted' }],
  total: 1, offset: 0, limit: 20,
}
const wordbookPage: WordbookListPage = {
  items: [{ id: 'book-1', visibility: 'private', status: 'ready', name: 'Core Words', version: '1', entry_count: 10, is_active: true, created_at: '2026-10-23T04:00:00Z', updated_at: '2026-10-23T04:00:00Z', description: null, owner_id: 'member-1', created_by: 'member-1' }],
  total: 1, offset: 0, limit: 100,
}
const question: PracticeQuestion = {
  id: 'q-1', position: 0, questionType: 'fill_blank', prompt: 'Choose', sentence: 'The team remained ____.', sentenceZh: null,
  article: null, articleZh: null, options: [{ id: 'o-1', text: 'resilient', textZh: '有韧性的' }, { id: 'o-2', text: 'fragile', textZh: '脆弱的' }],
  sourceText: null, sourceLanguage: null, targetLanguage: null, requirements: [], targetEntryIds: [], targetWords: [], sourceCitation: null,
  topic: null, topicZh: null, role: null, roleZh: null, scenario: null, scenarioZh: null, turns: [],
}
const result: PracticeResult = {
  sessionId: 'session-1', submissionId: 'submission-1', status: 'completed', score: 100, correctCount: 1, totalQuestions: 1, wrongCount: 0,
  questions: [{ questionId: 'q-1', questionType: 'fill_blank', userAnswer: 'o-1', gradedCorrect: true, isMistake: false, score: 100, correctChoiceId: 'o-1', correctOptionText: 'resilient', explanation: 'Context points to resilience.', referenceContent: null, dimensions: [{ name: '词义', score: 1, maxScore: 1 }], errors: [], suggestions: [] }],
  mistakes: [], errorCode: null, errorMessage: null, submittedAt: '2026-10-23T04:02:00Z',
}

describe('practice views', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    practiceMocks.createPracticeSession.mockResolvedValue(session)
    practiceMocks.fetchPracticeUsage.mockResolvedValue(usage)
    practiceMocks.listPracticeRecords.mockResolvedValue(recordPage)
    practiceMocks.listPracticeMistakes.mockResolvedValue(recordPage)
    practiceMocks.getPracticeRecord.mockResolvedValue({ ...recordPage.items[0], result })
    practiceMocks.deletePracticeRecords.mockResolvedValue({ deletedCount: 1, deletedIds: ['record-1'] })
    wordbookMocks.listWordbooks.mockResolvedValue(wordbookPage)
  })

  it('surfaces 429 on practice creation with request id', async () => {
    practiceMocks.createPracticeSession.mockRejectedValueOnce(new ApiError(429, 'AI_QUOTA_EXHAUSTED', 'Daily quota exhausted.', null, 'quota-request', true))
    const { wrapper } = await mountRoute(PracticeHubView, '/practice?type=fill_blank')
    await wrapper.get('.practice-config-dialog form').trigger('submit')
    await flushPromises()
    expect(wrapper.text()).toContain('今天的 AI 次数已用完')
    expect(wrapper.text()).toContain('quota-request')
  })

  it('surfaces 403 on the records page', async () => {
    practiceMocks.listPracticeRecords.mockRejectedValueOnce(new ApiError(403, 'FORBIDDEN', 'Practice access denied.', null, 'forbidden-practice', false))
    const { wrapper } = await mountRoute(PracticeRecordsView, '/practice/records')
    expect(wrapper.text()).toContain('权限不足或操作被拒绝')
    expect(wrapper.text()).toContain('forbidden-practice')
  })

  it('creates a writing session with one question from its book', async () => {
    const { wrapper, router } = await mountRoute(PracticeHubView, '/practice?type=writing')
    // Writing has no question-count choice; it always creates one essay.
    expect(wrapper.find('#practice-count').exists()).toBe(false)
    expect((wrapper.get('#practice-writing-length').element as HTMLSelectElement).value).toBe('150')
    await wrapper.get('.practice-config-dialog form').trigger('submit')
    await flushPromises()
    expect(practiceMocks.createPracticeSession).toHaveBeenCalledWith(
      expect.objectContaining({
        practiceType: 'writing',
        count: 1,
        writingTargetWords: 150,
        translationDirection: null,
      }),
      expect.any(String),
    )
    expect(router.currentRoute.value.name).toBe('practice')
    expect(router.currentRoute.value.query.session).toBeTruthy()
  })

  it('offers the four generated exercise types as books', async () => {
    const { wrapper } = await mountRoute(PracticeHubView, '/practice')
    const books = wrapper.findAll('.practice-shelf .shelf-book')
    expect(books.map((book) => book.text())).toHaveLength(4)
    const labels = books.map((book) => book.text())
    expect(labels.some((text) => text.includes('填空'))).toBe(true)
    expect(labels.some((text) => text.includes('阅读'))).toBe(true)
    // Conversation is one dialogue, so it stands on the card row instead.
    expect(labels.some((text) => text.includes('对话'))).toBe(false)
    // The form is not on the page until a book is picked.
    expect(wrapper.find('.practice-config-dialog').exists()).toBe(false)
  })

  it('offers the memory drills as cards, with conversation among them', async () => {
    const { wrapper } = await mountRoute(PracticeHubView, '/practice')
    const cards = wrapper.findAll('.shelf--cards .shelf-book')
    const labels = cards.map((card) => card.text())
    expect(labels.some((text) => text.includes('翻卡'))).toBe(true)
    expect(labels.some((text) => text.includes('选择'))).toBe(true)
    expect(labels.some((text) => text.includes('拼写'))).toBe(true)
    expect(labels.some((text) => text.includes('对话'))).toBe(true)
    // A board under the books is the shelf; the card row stands on the page.
    expect(wrapper.find('.shelf--cards .shelf-board').exists()).toBe(false)
  })

  it('opens the settings dialog when a book is picked', async () => {
    const { wrapper } = await mountRoute(PracticeHubView, '/practice')
    const reading = wrapper.findAll('.practice-shelf .shelf-book').find((book) => book.text().includes('阅读'))
    expect(reading).toBeTruthy()
    await reading!.trigger('click')
    await flushPromises()
    expect(wrapper.find('.practice-config-dialog').exists()).toBe(true)
    expect(wrapper.get('.practice-config-dialog h2').text()).toContain('阅读')
    await wrapper.get('.practice-config-dialog form').trigger('submit')
    await flushPromises()
    const [input] = practiceMocks.createPracticeSession.mock.calls.at(-1)!
    expect(input.practiceType).toBe('reading')
  })

  it('keeps a mixed set reachable without a book of its own', async () => {
    const { wrapper } = await mountRoute(PracticeHubView, '/practice')
    await wrapper.get('.practice-shelf__mixed-link').trigger('click')
    await flushPromises()
    expect(wrapper.find('.practice-config-dialog').exists()).toBe(true)
    await wrapper.get('.practice-config-dialog form').trigger('submit')
    await flushPromises()
    const [input] = practiceMocks.createPracticeSession.mock.calls.at(-1)!
    expect(input.practiceType).toBe('mixed')
  })

  it('renders a choice question without any answer or explanation fields', () => {
    const wrapper = mount(PracticeQuestionCard, { props: { question, modelValue: '', index: 0, total: 1 } })
    expect(wrapper.findAll('input[type="radio"]')).toHaveLength(2)
    // Choice questions never fall through to the free-text answer box.
    expect(wrapper.find('textarea').exists()).toBe(false)
    expect(wrapper.text()).not.toContain('解析：')
    expect(wrapper.text()).not.toContain('正确答案')
    expect(wrapper.html()).not.toContain('correct_option')
  })

  it('renders translation and writing as server-backed text areas', () => {
    const translation = mount(PracticeQuestionCard, { props: { question: { ...question, questionType: 'translation', sourceText: 'Hello', sourceLanguage: 'en', targetLanguage: 'zh', requirements: ['保持语气'] }, modelValue: '', index: 0, total: 1 } })
    const writing = mount(PracticeQuestionCard, { props: { question: { ...question, questionType: 'writing', prompt: 'Write about learning', requirements: ['至少 100 词'] }, modelValue: '', index: 0, total: 1 } })
    expect(translation.find('textarea').exists()).toBe(true)
    expect(translation.text()).toContain('Hello')
    expect(writing.find('textarea').exists()).toBe(true)
    expect(writing.text()).toContain('至少 100 词')
  })

  it('shows result answer, explanation and dimensions only after submit', () => {
    const wrapper = mount(PracticeResultView, { props: { result } })
    expect(wrapper.text()).toContain('100 分')
    expect(wrapper.text()).toContain('resilient')
    expect(wrapper.text()).toContain('Context points to resilience')
    expect(wrapper.text()).toContain('词义')
  })

  it('filters records and bulk deletes only selected records after confirmation', async () => {
    vi.spyOn(window, 'confirm').mockReturnValueOnce(true)
    const { wrapper } = await mountRoute(PracticeRecordsView, '/practice/records')
    expect(wrapper.findAll('.practice-records-table tbody tr')).toHaveLength(1)
    await wrapper.get('#record-type').setValue('fill_blank')
    await flushPromises()
    expect(practiceMocks.listPracticeRecords).toHaveBeenLastCalledWith(expect.objectContaining({ practiceType: 'fill_blank', offset: 0 }))
    await wrapper.get('tbody input[type="checkbox"]').setValue(true)
    await wrapper.findAll('[role="button"]').find((button) => button.text().includes('删除选中'))!.trigger('click')
    await flushPromises()
    expect(practiceMocks.deletePracticeRecords).toHaveBeenCalledWith(['record-1'], expect.any(String))
  })

  it('uses the mistakes endpoint on the dedicated mistakes view', async () => {
    await mountRoute(PracticeRecordsView, '/practice/mistakes', { onlyMistakes: true })
    expect(practiceMocks.listPracticeMistakes).toHaveBeenCalled()
    expect(practiceMocks.listPracticeRecords).not.toHaveBeenCalled()
  })

  it('keeps option glosses out of the answering view and shows them on review', () => {
    const answering = mount(PracticeQuestionCard, { props: { question, modelValue: '', index: 0, total: 1 } })
    expect(answering.text()).toContain('The team remained ____.')
    // Glosses would give the answer away while the learner is choosing.
    expect(answering.text()).not.toContain('有韧性的')
    expect(answering.text()).not.toContain('源语言')

    const review = mount(PracticeQuestionCard, {
      props: { question, modelValue: 'o-2', index: 0, total: 1, review: { selected: 'o-2', correct: 'o-1' } },
    })
    expect(review.find('.practice-option--wrong').exists()).toBe(true)
    expect(review.find('.practice-option--correct').exists()).toBe(true)
    expect(review.text()).toContain('有韧性的')
    expect(review.text()).not.toContain('正确')
    expect(review.text()).not.toContain('你的选择')
  })

  it('shows a reading passage once above its questions', () => {
    const readingQuestion: PracticeQuestion = {
      ...question,
      questionType: 'reading',
      article: 'Maya missed the garden she left in her hometown.',
      articleZh: '玛雅想念她留在故乡的花园。',
      prompt: 'What is the main idea?',
      targetWords: ['garden'],
    }
    const readingResult: PracticeResult = {
      ...result,
      totalQuestions: 1,
      questions: [
        {
          questionId: readingQuestion.id,
          questionType: 'reading',
          userAnswer: 'o-1',
          gradedCorrect: true,
          isMistake: false,
          score: null,
          correctChoiceId: 'o-1',
          correctOptionText: null,
          explanation: 'The passage supports it.',
          referenceContent: null,
          dimensions: [],
          errors: [],
          suggestions: [],
        },
      ],
    }
    const wrapper = mount(PracticeResultView, {
      props: { result: readingResult, questions: [readingQuestion] },
    })
    expect(wrapper.findAll('.practice-article-panel--wide')).toHaveLength(1)
    expect(wrapper.findAll('.practice-question-card .practice-article')).toHaveLength(0)
    expect(wrapper.text()).toContain('玛雅想念她留在故乡的花园。')
    expect(wrapper.find('.spoken-word--target').text()).toBe('garden')
  })

  it('shows one total score and re-renders the submitted options in the result', () => {
    const wrapper = mount(PracticeResultView, { props: { result, questions: [question] } })
    expect(wrapper.text()).toContain('100 分')
    expect(wrapper.text()).not.toContain('得分：100')
    expect(wrapper.findAll('.practice-option')).toHaveLength(2)
    expect(wrapper.text()).toContain('Context points to resilience.')
  })
})
