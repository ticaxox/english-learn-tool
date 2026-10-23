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

const StubPage = defineComponent({ render: () => h('div') })

function page(overrides: Partial<PagedMistakes> = {}): PagedMistakes {
  return {
    items: [
      {
        entryId: 'entry-1',
        stateId: 'state-1',
        headword: 'resilient',
        definition: '有弹性的',
        module: null,
        lastMistakeAt: '2026-10-23T01:00:00Z',
        mistakeCount: 2,
        priorityReview: false,
        status: 'relearning',
      },
      {
        entryId: 'entry-2',
        stateId: 'state-2',
        headword: 'fragile',
        definition: '易碎的',
        module: null,
        lastMistakeAt: '2026-10-22T09:00:00Z',
        mistakeCount: 1,
        priorityReview: true,
        status: 'review',
      },
    ],
    nextCursor: null,
    hasMore: false,
    ...overrides,
  }
}

async function flush(): Promise<void> {
  for (let index = 0; index < 5; index += 1) await Promise.resolve()
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

  it('lists real memory mistakes without inventing a source module', async () => {
    const wrapper = await mountView()
    const rows = wrapper.findAll('.mistake-table tbody tr')
    expect(rows).toHaveLength(2)
    expect(rows[0].text()).toContain('resilient')
    expect(rows[0].text()).toContain('背词训练')
    expect(rows[0].text()).toContain('重新学习')
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

  it('toggles priority by entry id and reloads the same cursor', async () => {
    const wrapper = await mountView()
    await wrapper.findAll('.link-button')[0].trigger('click')
    await flush()

    expect(apiMocks.setMistakePriority).toHaveBeenCalledWith('entry-1', { priorityReview: true })
    expect(apiMocks.fetchMistakes).toHaveBeenCalledTimes(2)
    expect(apiMocks.fetchMistakes).toHaveBeenLastCalledWith({ cursor: null, limit: 50 })
  })

  it('never re-flags a row locally before the reload lands', async () => {
    let release: (value: PagedMistakes) => void = () => {}
    apiMocks.fetchMistakes
      .mockResolvedValueOnce(page())
      .mockImplementationOnce(() => new Promise<PagedMistakes>((resolve) => { release = resolve }))

    const wrapper = await mountView()
    await wrapper.findAll('.link-button')[0].trigger('click')
    await flush()

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

  it('uses the server cursor for the next page', async () => {
    apiMocks.fetchMistakes
      .mockResolvedValueOnce(page({ nextCursor: 'cursor-2', hasMore: true }))
      .mockResolvedValueOnce(page({ items: [] }))
    const wrapper = await mountView()
    const next = wrapper.findAll('.pager button').find((button) => button.text() === '下一页')
    await next!.trigger('click')
    await flush()
    expect(apiMocks.fetchMistakes).toHaveBeenLastCalledWith({ cursor: 'cursor-2', limit: 50 })
  })

  it('says when there are no mistakes instead of rendering an empty table', async () => {
    apiMocks.fetchMistakes.mockResolvedValue(page({ items: [], hasMore: false }))
    const wrapper = await mountView()
    expect(wrapper.text()).toContain('暂时没有错词')
    expect(wrapper.find('.mistake-table').exists()).toBe(false)
  })
})