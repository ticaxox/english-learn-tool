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
  sourceText: null, sourceLanguage: null, targetLanguage: null, requirements: [], targetEntryIds: [],
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
    const { wrapper } = await mountRoute(PracticeHubView, '/practice')
    await wrapper.get('form').trigger('submit')
    await flushPromises()
    expect(wrapper.text()).toContain('请求过于频繁')
    expect(wrapper.text()).toContain('quota-request')
  })

  it('surfaces 403 on the records page', async () => {
    practiceMocks.listPracticeRecords.mockRejectedValueOnce(new ApiError(403, 'FORBIDDEN', 'Practice access denied.', null, 'forbidden-practice', false))
    const { wrapper } = await mountRoute(PracticeRecordsView, '/practice/records')
    expect(wrapper.text()).toContain('权限不足或操作被拒绝')
    expect(wrapper.text()).toContain('forbidden-practice')
  })

  it('offers all four practice types and creates a writing session with one question', async () => {
    const { wrapper, router } = await mountRoute(PracticeHubView, '/practice')
    expect(wrapper.findAll('.practice-type-card')).toHaveLength(4)
    await wrapper.findAll('.practice-type-card').find((card) => card.text().includes('作文'))!.trigger('click')
    expect((wrapper.get('#practice-count').element as HTMLSelectElement).value).toBe('1')
    await wrapper.get('form').trigger('submit')
    await flushPromises()
    expect(practiceMocks.createPracticeSession).toHaveBeenCalledWith(expect.objectContaining({ practiceType: 'writing', count: 1 }), expect.any(String))
    expect(router.currentRoute.value.name).toBe('practice-session')
  })

  it('renders a choice question without any answer or explanation fields', () => {
    const wrapper = mount(PracticeQuestionCard, { props: { question, modelValue: '', index: 0, total: 1 } })
    expect(wrapper.findAll('input[type="radio"]')).toHaveLength(2)
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
    await wrapper.findAll('button').find((button) => button.text().includes('删除选中'))!.trigger('click')
    await flushPromises()
    expect(practiceMocks.deletePracticeRecords).toHaveBeenCalledWith(['record-1'], expect.any(String))
  })

  it('uses the mistakes endpoint on the dedicated mistakes view', async () => {
    await mountRoute(PracticeRecordsView, '/practice/mistakes', { onlyMistakes: true })
    expect(practiceMocks.listPracticeMistakes).toHaveBeenCalled()
    expect(practiceMocks.listPracticeRecords).not.toHaveBeenCalled()
  })

  it('keeps the answering view English-only and explains in Chinese on review', () => {
    const answering = mount(PracticeQuestionCard, { props: { question, modelValue: '', index: 0, total: 1 } })
    expect(answering.text()).toContain('The team remained ____.')
    expect(answering.text()).not.toContain('有韧性的')
    expect(answering.text()).not.toContain('源语言')

    const review = mount(PracticeQuestionCard, {
      props: { question, modelValue: 'o-2', index: 0, total: 1, review: { selected: 'o-2', correct: 'o-1' } },
    })
    expect(review.find('.practice-option--wrong').exists()).toBe(true)
    expect(review.find('.practice-option--correct').exists()).toBe(true)
    expect(review.text()).toContain('有韧性的')
    expect(review.text()).toContain('正确')
  })

  it('shows one total score and re-renders the submitted options in the result', () => {
    const wrapper = mount(PracticeResultView, { props: { result, questions: [question] } })
    expect(wrapper.text()).toContain('100 分')
    expect(wrapper.text()).not.toContain('得分：100')
    expect(wrapper.findAll('.practice-option')).toHaveLength(2)
    expect(wrapper.text()).toContain('Context points to resilience.')
  })
})
