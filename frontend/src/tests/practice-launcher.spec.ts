import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createMemoryHistory, createRouter } from 'vue-router'
import { defineComponent, h } from 'vue'
import PracticeLauncher from '../components/PracticeLauncher.vue'

const learningMocks = vi.hoisted(() => ({ fetchMemoryConfig: vi.fn() }))
const practiceMocks = vi.hoisted(() => ({ createPracticeSession: vi.fn() }))

vi.mock('../api/learning', () => learningMocks)
vi.mock('../api/practice', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../api/practice')>()
  return { ...actual, ...practiceMocks }
})

const StubPage = defineComponent({ render: () => h('div') })

function makeRouter() {
  return createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/challenges', name: 'challenges', component: StubPage },
      { path: '/memory', name: 'memory', component: StubPage },
      { path: '/practice/:sessionId', name: 'practice-session', component: StubPage },
    ],
  })
}

const memoryConfig = {
  flashcard: { enabled: true, blankType: null },
  choice: { enabled: true, blankType: null },
  spelling: { enabled: true, blankType: null },
  preferences: {},
}

describe('PracticeLauncher', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    learningMocks.fetchMemoryConfig.mockResolvedValue(memoryConfig)
    practiceMocks.createPracticeSession.mockResolvedValue({ id: 'session-1' })
  })

  it('offers the three memory modes and starts the chosen one', async () => {
    const router = makeRouter()
    await router.push('/challenges')
    const wrapper = mount(PracticeLauncher, { props: { open: true, kind: 'memory' }, global: { plugins: [router] } })
    await flushPromises()

    expect(wrapper.findAll('.launcher-option')).toHaveLength(3)
    await wrapper.findAll('.launcher-option').find((option) => option.text().includes('拼写'))!.trigger('click')
    await vi.waitFor(() => expect(router.currentRoute.value.name).toBe('memory'))

    expect(router.currentRoute.value.query.module).toBe('spelling')
    expect(wrapper.emitted('close')).toBeTruthy()
  })

  it('creates the AI practice with the chosen type and count, then opens it', async () => {
    const router = makeRouter()
    await router.push('/challenges')
    const wrapper = mount(PracticeLauncher, { props: { open: true, kind: 'practice' }, global: { plugins: [router] } })
    await flushPromises()

    await wrapper.findAll('.launcher-type').find((type) => type.text().includes('阅读'))!.trigger('click')
    await wrapper.find('.launcher-actions .button').trigger('click')
    await vi.waitFor(() => expect(router.currentRoute.value.name).toBe('practice-session'))

    expect(practiceMocks.createPracticeSession).toHaveBeenCalledWith(
      expect.objectContaining({ practiceType: 'reading', count: 5, source: 'today_new' }),
      expect.any(String),
    )
    expect(router.currentRoute.value.params.sessionId).toBe('session-1')
  })
})
