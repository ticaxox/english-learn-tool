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
      { path: '/practice/records/:recordId', name: 'practice-record', component: StubPage },
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

  it('offers the generated exercise types as books', async () => {
    const { wrapper } = await mountRoute(PracticeHubView, '/practice')
    const labels = wrapper.findAll('.practice-shelf .shelf-book').map((book) => book.text())
    for (const kind of ['填空', '阅读', '翻译', '对话', '作文']) {
      expect(labels.some((text) => text.includes(kind))).toBe(true)
    }
    // 设置 sits at the end of the shelf but opens the drill settings, not a drill.
    expect(labels.some((text) => text.includes('设置'))).toBe(true)
    // The form is not on the page until a book is picked.
    expect(wrapper.find('.practice-config-dialog').exists()).toBe(false)
  })

  it('offers the memory drills as cards, apart from the exercise books', async () => {
    const { wrapper } = await mountRoute(PracticeHubView, '/practice')
    const labels = wrapper.findAll('.shelf--cards .shelf-book').map((card) => card.text())
    expect(labels.some((text) => text.includes('翻卡'))).toBe(true)
    expect(labels.some((text) => text.includes('选择'))).toBe(true)
    expect(labels.some((text) => text.includes('拼写'))).toBe(true)
    // Speaking is an exercise now: it belongs on the books shelf, not here.
    expect(labels.some((text) => text.includes('对话'))).toBe(false)
    // The card row sits on its own board now that it carries real covers.
    expect(wrapper.find('.shelf--cards .shelf-board').exists()).toBe(true)
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

  it('keeps the drill settings at the end of the shelf instead of a mixed book', async () => {
    const { wrapper } = await mountRoute(PracticeHubView, '/practice')
    const settings = wrapper
      .findAll('.practice-shelf .shelf-book')
      .find((book) => book.text().includes('设置'))
    expect(settings).toBeTruthy()
    await settings!.trigger('click')
    await flushPromises()
    expect(wrapper.find('.practice-config-dialog').exists()).toBe(true)
    // 设置 configures a drill; it must not start a session by itself.
    expect(practiceMocks.createPracticeSession).not.toHaveBeenCalled()
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

  it('filters records by type from the URL and bulk deletes the selected record', async () => {
    vi.spyOn(window, 'confirm').mockReturnValueOnce(true)
    const { wrapper, router } = await mountRoute(PracticeRecordsView, '/practice/records')
    expect(wrapper.findAll('.records-row')).toHaveLength(1)
    await router.push('/practice/records?type=fill_blank')
    await flushPromises()
    expect(practiceMocks.listPracticeRecords).toHaveBeenLastCalledWith(expect.objectContaining({ practiceType: 'fill_blank', offset: 0 }))
    await wrapper.get('.records-row input[type="checkbox"]').setValue(true)
    await wrapper.findAll('[role="button"]').find((button) => button.text().includes('删除'))!.trigger('click')
    await flushPromises()
    expect(practiceMocks.deletePracticeRecords).toHaveBeenCalledWith(['record-1'], expect.any(String))
  })

  it('opens a record on its own page instead of beside the list', async () => {
    const { wrapper, router } = await mountRoute(PracticeRecordsView, '/practice/records')
    // The list is a list: nothing is fetched until a record is picked.
    expect(practiceMocks.getPracticeRecord).not.toHaveBeenCalled()
    await wrapper.get('.records-row__open').trigger('click')
    await flushPromises()
    expect(router.currentRoute.value.name).toBe('practice-record')
    expect(router.currentRoute.value.params.recordId).toBe('record-1')
  })

  it('groups the mistake book by date, then by type inside each date', async () => {
    practiceMocks.listPracticeMistakes.mockResolvedValueOnce({
      items: [
        { ...recordPage.items[0], id: 'm1', practiceType: 'reading', wrongCount: 1, submittedAt: '2026-10-24T04:00:00Z' },
        { ...recordPage.items[0], id: 'm2', practiceType: 'fill_blank', wrongCount: 1, submittedAt: '2026-10-24T06:00:00Z' },
        { ...recordPage.items[0], id: 'm3', practiceType: 'reading', wrongCount: 2, submittedAt: '2026-10-24T08:00:00Z' },
        { ...recordPage.items[0], id: 'm4', practiceType: 'reading', wrongCount: 2, submittedAt: '2026-10-23T04:00:00Z' },
      ],
      total: 4,
      offset: 0,
      limit: 100,
    })
    const { wrapper } = await mountRoute(PracticeRecordsView, '/practice/mistakes', { onlyMistakes: true })
    await flushPromises()
    const days = wrapper.findAll('.records-group')
    // Newest day first; each day keeps the fixed type order.
    expect(days).toHaveLength(2)
    expect(days[0].findAll('.records-subgroup h3').map((heading) => heading.text())).toEqual(['填空', '阅读'])
    expect(days[1].findAll('.records-subgroup h3').map((heading) => heading.text())).toEqual(['阅读'])
    // Inside a type the newest practice leads: 08:00 (two wrong) before 04:00 (one).
    const readingMetas = days[0].findAll('.records-subgroup')[1].findAll('.records-row__meta').map((meta) => meta.text())
    expect(readingMetas[0]).toContain('错 2')
    expect(readingMetas[1]).toContain('错 1')
  })

  it('keeps only the date groups when one type is picked', async () => {
    practiceMocks.listPracticeMistakes.mockResolvedValueOnce({
      items: [
        { ...recordPage.items[0], id: 'm1', practiceType: 'reading', wrongCount: 1, submittedAt: '2026-10-24T04:00:00Z' },
      ],
      total: 1,
      offset: 0,
      limit: 100,
    })
    const { wrapper } = await mountRoute(PracticeRecordsView, '/practice/mistakes?type=reading', { onlyMistakes: true })
    await flushPromises()
    expect(practiceMocks.listPracticeMistakes).toHaveBeenLastCalledWith(
      expect.objectContaining({ practiceType: 'reading' }),
    )
    expect(wrapper.findAll('.records-group').length).toBe(1)
    expect(wrapper.findAll('.records-subgroup')).toHaveLength(0)
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
