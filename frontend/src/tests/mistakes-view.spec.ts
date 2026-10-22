import { mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createMemoryHistory, createRouter } from 'vue-router'
import { defineComponent, h } from 'vue'
import MistakesView from '../views/MistakesView.vue'
import type { PagedMistakes } from '../types/learning'

const apiMocks = vi.hoisted(() => ({
  fetchMistakes: vi.fn(),
  restoreWord: vi.fn(),
  setMistakePriority: vi.fn(),
}))

vi.mock('../api/learning', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../api/learning')>()
  return { ...actual, ...apiMocks }
})

// The view renders the contract gate while T-BE-004 is unfrozen, so the
// table-level behaviour is exercised by flipping the gate for this file only.
vi.mock('../api/contract-adapter', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../api/contract-adapter')>()
  return {
    ...actual,
    isContractFrozen: () => true,
    contractCoordinateLabel: () => 'test coordinates',
  }
})

const StubPage = defineComponent({ render: () => h('div') })

function page(overrides: Partial<PagedMistakes> = {}): PagedMistakes {
  return {
    items: [
      {
        stateId: 'state-1',
        headword: 'resilient',
        definition: '有弹性的',
        module: 'flashcard',
        lastMistakeAt: '2026-10-23T01:00:00Z',
        mistakeCount: 2,
        priorityReview: false,
      },
      {
        stateId: 'state-2',
        headword: 'fragile',
        definition: '易碎的',
        module: 'spelling',
        lastMistakeAt: '2026-10-22T09:00:00Z',
        mistakeCount: 1,
        priorityReview: true,
      },
    ],
    total: 2,
    offset: 0,
    limit: 20,
    ...overrides,
  }
}

async function flush(): Promise<void> {
  for (let index = 0; index < 4; index += 1) {
    await Promise.resolve()
  }
}

async function mountView() {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [{ path: '/memory/mistakes', name: 'memory-mistakes', component: StubPage }],
  })
  await router.push('/memory/mistakes')
  await router.isReady()
  const wrapper = mount(MistakesView, { global: { plugins: [router] } })
  await flush()
  return wrapper
}

describe('MistakesView', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    apiMocks.fetchMistakes.mockResolvedValue(page())
    apiMocks.setMistakePriority.mockResolvedValue(undefined)
  })

  it('lists the real mistakes with their source module and count', async () => {
    const wrapper = await mountView()
    const rows = wrapper.findAll('.mistake-table tbody tr')
    expect(rows).toHaveLength(2)
    expect(rows[0].text()).toContain('resilient')
    expect(rows[0].text()).toContain('翻卡')
    expect(rows[1].text()).toContain('拼写')
    expect(rows[1].text()).toContain('1')
  })

  it('shows the priority flag from the server, not from local state', async () => {
    const wrapper = await mountView()
    const toggles = wrapper.findAll('.link-button')
    expect(toggles).toHaveLength(2)
    expect(toggles[0].attributes('aria-pressed')).toBe('false')
    expect(toggles[0].text()).toBe('标为重点')
    expect(toggles[1].attributes('aria-pressed')).toBe('true')
    expect(toggles[1].text()).toBe('已标记重点')
  })

  it('toggles priority through the server and then reloads the same page', async () => {
    const wrapper = await mountView()
    await wrapper.findAll('.link-button')[0].trigger('click')
    await flush()

    expect(apiMocks.setMistakePriority).toHaveBeenCalledWith('state-1', { priorityReview: true })
    // The flag only changes after the server confirms; the view refetches.
    expect(apiMocks.fetchMistakes).toHaveBeenCalledTimes(2)
    expect(apiMocks.fetchMistakes).toHaveBeenLastCalledWith({ offset: 0, limit: 20 })
  })

  it('never reorders or re-flags a row locally before the reload lands', async () => {
    let release: (value: PagedMistakes) => void = () => {}
    apiMocks.fetchMistakes
      .mockResolvedValueOnce(page())
      .mockImplementationOnce(() => new Promise<PagedMistakes>((resolve) => { release = resolve }))

    const wrapper = await mountView()
    await wrapper.findAll('.link-button')[0].trigger('click')
    await flush()

    // Still the original server flag while the refetch is in flight.
    expect(wrapper.findAll('.link-button')[0].attributes('aria-pressed')).toBe('false')

    release(page())
    await flush()
    expect(apiMocks.fetchMistakes).toHaveBeenCalledTimes(2)
  })

  it('keeps a failed priority update visible and leaves the flag untouched', async () => {
    apiMocks.setMistakePriority.mockRejectedValueOnce(new Error('priority rejected'))
    const wrapper = await mountView()
    await wrapper.findAll('.link-button')[0].trigger('click')
    await flush()

    expect(wrapper.text()).toContain('priority rejected')
    expect(wrapper.findAll('.link-button')[0].attributes('aria-pressed')).toBe('false')
    expect(apiMocks.fetchMistakes).toHaveBeenCalledTimes(1)
  })

  it('says when there are no mistakes instead of rendering an empty table', async () => {
    apiMocks.fetchMistakes.mockResolvedValue(page({ items: [], total: 0 }))
    const wrapper = await mountView()
    expect(wrapper.text()).toContain('暂时没有错词')
    expect(wrapper.find('.mistake-table').exists()).toBe(false)
  })
})
