import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createMemoryHistory, createRouter } from 'vue-router'
import { defineComponent, h } from 'vue'
import TodayView from '../views/TodayView.vue'
import LearningSettingsView from '../views/LearningSettingsView.vue'
import MemoryPracticeView from '../views/MemoryPracticeView.vue'
import MistakesView from '../views/MistakesView.vue'
import { defaultMemoryConfig } from '../lib/learning-validation'
import type {
  LearningProfile,
  LearningStats,
  MemoryConfig,
  PagedMistakes,
  TodayPlan,
} from '../types/learning'

const apiMocks = vi.hoisted(() => ({
  fetchTodayPlan: vi.fn(),
  ensureTodayPlan: vi.fn(),
  fetchLearningProfile: vi.fn(),
  updateLearningProfile: vi.fn(),
  fetchLearningStats: vi.fn(),
  fetchMemoryConfig: vi.fn(),
  fetchMistakes: vi.fn(),
  restoreWord: vi.fn(),
  setMistakePriority: vi.fn(),
}))

vi.mock('../api/learning', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../api/learning')>()
  return { ...actual, ...apiMocks }
})

const StubPage = defineComponent({ render: () => h('div') })

function makeRouter() {
  return createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/overview', name: 'overview', component: StubPage },
      { path: '/wordbooks', name: 'wordbooks', component: StubPage },
      { path: '/settings', name: 'settings', component: StubPage },
      { path: '/memory', name: 'memory', component: StubPage },
      { path: '/memory/mistakes', name: 'memory-mistakes', component: StubPage },
    ],
  })
}

async function mountWithRouter(component: Parameters<typeof mount>[0]) {
  const router = makeRouter()
  await router.push('/overview')
  await router.isReady()
  const wrapper = mount(component, { global: { plugins: [router] } })
  for (let index = 0; index < 8; index += 1) await Promise.resolve()
  return wrapper
}

const config: MemoryConfig = {
  ...defaultMemoryConfig(),
  choice: { enabled: false, blankType: null },
}

const profile: LearningProfile = {
  examTarget: 'CET6',
  examDate: '2027-06-01',
  dailyNewWords: 20,
  dailyMinutes: 30,
  department: '学习部',
  learningGroup: 'A 组',
  memoryConfig: config,
  needsOnboarding: false,
  planEffectiveFrom: null,
}

const plan: TodayPlan = {
  localDate: '2026-10-23',
  wordbook: { id: 'book-1', name: 'CET-6 核心词' },
  newWords: { completed: 3, target: 20 },
  dueReviews: { completed: 2, target: 8 },
  extraDueAvailable: true,
  extraDueCount: 2,
  minutes: { active: 12, goal: 30 },
  status: 'in_progress',
  aiPractice: { state: 'not_available', message: 'AI practice is not implemented in this milestone.' },
  calculationVersion: 'plan:daily-plan-1.0.0|fsrs-6.3.2',
  generatedAt: '2026-10-23T01:00:00Z',
  shortfallReason: null,
}

const stats: LearningStats = {
  localDate: '2026-10-23',
  activeMinutes: 12,
  goalMinutes: 30,
  goalReached: false,
  streakDays: 3,
  sources: ['心跳 720 秒'],
}

const mistakes: PagedMistakes = { items: [], nextCursor: null, hasMore: false }

describe('learning surfaces with the frozen contract', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
    apiMocks.fetchTodayPlan.mockResolvedValue(plan)
    apiMocks.ensureTodayPlan.mockResolvedValue(plan)
    apiMocks.fetchLearningProfile.mockResolvedValue(profile)
    apiMocks.fetchLearningStats.mockResolvedValue(stats)
    apiMocks.fetchMemoryConfig.mockResolvedValue(config)
    apiMocks.fetchMistakes.mockResolvedValue(mistakes)
  })

  it('renders real today progress returned by the server', async () => {
    const wrapper = await mountWithRouter(TodayView)
    expect(apiMocks.fetchTodayPlan).toHaveBeenCalledTimes(1)
    expect(wrapper.findAll('.today-tile')).toHaveLength(3)
    expect(wrapper.text()).toContain('CET-6 核心词')
    expect(wrapper.text()).toContain('AI 练习尚未开放')
    expect(wrapper.findAll('[role="progressbar"]').length).toBeGreaterThanOrEqual(3)
  })

  it('renders the profile form and real memory preferences', async () => {
    const wrapper = await mountWithRouter(LearningSettingsView)
    expect(apiMocks.fetchLearningProfile).toHaveBeenCalledTimes(1)
    expect(wrapper.find('form').exists()).toBe(true)
    expect(wrapper.find('#daily-new-words').exists()).toBe(true)
    expect(wrapper.text()).toContain('学习部')
    expect(wrapper.text()).toContain('服务端默认')
  })

  it('shows only the modules enabled by the server config', async () => {
    const wrapper = await mountWithRouter(MemoryPracticeView)
    expect(apiMocks.fetchMemoryConfig).toHaveBeenCalledTimes(1)
    const cards = wrapper.findAll('.module-card')
    expect(cards.map((card) => card.text())).toEqual([
      expect.stringContaining('翻卡'),
      expect.stringContaining('拼写'),
    ])
  })

  it('shows the real empty mistakes state', async () => {
    const wrapper = await mountWithRouter(MistakesView)
    expect(apiMocks.fetchMistakes).toHaveBeenCalledTimes(1)
    expect(wrapper.text()).toContain('暂时没有错词')
    expect(wrapper.find('.mistake-table').exists()).toBe(false)
  })
})