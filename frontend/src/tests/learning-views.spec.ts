import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createMemoryHistory, createRouter } from 'vue-router'
import { defineComponent, h } from 'vue'
import TodayView from '../views/TodayView.vue'
import LearningSettingsView from '../views/LearningSettingsView.vue'
import MemoryPracticeView from '../views/MemoryPracticeView.vue'
import MistakesView from '../views/MistakesView.vue'

/**
 * While T-BE-004 stays unfrozen, every learning surface must render the
 * contract gate and must NOT call the API. A page that quietly fetched would
 * be one bad deploy away from showing invented progress.
 */
const apiMocks = vi.hoisted(() => ({
  fetchTodayPlan: vi.fn(),
  ensureTodayPlan: vi.fn(),
  fetchLearningProfile: vi.fn(),
  updateLearningProfile: vi.fn(),
  fetchMemoryConfig: vi.fn(),
  fetchMistakes: vi.fn(),
  restoreWord: vi.fn(),
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
  return mount(component, { global: { plugins: [router] } })
}

describe('learning surfaces before the contract is frozen', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
  })

  it('today view shows the contract gate and never calls the API', async () => {
    const wrapper = await mountWithRouter(TodayView)
    expect(wrapper.find('.contract-gate').exists()).toBe(true)
    expect(wrapper.text()).toContain('未冻结')
    expect(wrapper.text()).toContain('/learning/today')
    expect(apiMocks.fetchTodayPlan).not.toHaveBeenCalled()
    expect(apiMocks.ensureTodayPlan).not.toHaveBeenCalled()
  })

  it('today view does not render invented progress tiles', async () => {
    const wrapper = await mountWithRouter(TodayView)
    expect(wrapper.findAll('.today-tile')).toHaveLength(0)
    expect(wrapper.find('[role="progressbar"]').exists()).toBe(false)
  })

  it('settings view shows the gate and never sends a profile request', async () => {
    const wrapper = await mountWithRouter(LearningSettingsView)
    expect(wrapper.find('.contract-gate').exists()).toBe(true)
    expect(wrapper.text()).toContain('/users/me/profile')
    expect(apiMocks.fetchLearningProfile).not.toHaveBeenCalled()
    expect(apiMocks.updateLearningProfile).not.toHaveBeenCalled()
  })

  it('settings view does not render a fake profile form', async () => {
    const wrapper = await mountWithRouter(LearningSettingsView)
    expect(wrapper.find('form').exists()).toBe(false)
    expect(wrapper.find('#daily-new-words').exists()).toBe(false)
  })

  it('memory view shows the gate and never starts a session', async () => {
    const wrapper = await mountWithRouter(MemoryPracticeView)
    expect(wrapper.find('.contract-gate').exists()).toBe(true)
    expect(wrapper.text()).toContain('/memory/config')
    expect(apiMocks.fetchMemoryConfig).not.toHaveBeenCalled()
    expect(wrapper.findAll('.module-card')).toHaveLength(0)
  })

  it('mistakes view shows the gate and never fetches mistakes', async () => {
    const wrapper = await mountWithRouter(MistakesView)
    expect(wrapper.find('.contract-gate').exists()).toBe(true)
    expect(wrapper.text()).toContain('/memory/mistakes')
    expect(apiMocks.fetchMistakes).not.toHaveBeenCalled()
    expect(wrapper.find('.mistake-table').exists()).toBe(false)
  })

  it('names every endpoint that still needs calibration', async () => {
    const wrapper = await mountWithRouter(MemoryPracticeView)
    const text = wrapper.text()
    for (const endpoint of [
      'GET /memory/config',
      'POST /memory/sessions',
      'GET /memory/sessions/{id}',
      'POST /memory/sessions/{id}/events',
      'POST /memory/sessions/{id}/complete',
      'PATCH /memory/words/{state_id}/master',
      'POST /learning/heartbeat',
    ]) {
      expect(text).toContain(endpoint)
    }
  })

  it('states plainly that no placeholder data is used', async () => {
    const wrapper = await mountWithRouter(TodayView)
    expect(wrapper.text()).toContain('不会')
    expect(wrapper.text()).toContain('示例卡片')
    expect(wrapper.text()).toContain('假评分')
    expect(wrapper.text()).toContain('假计时')
  })
})
