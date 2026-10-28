import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { CurrentUser } from '../api/contracts'
import type { Wordbook } from '../api/wordbooks'
import { useAuthStore } from '../stores/auth'
import WordbooksView from '../views/WordbooksView.vue'

const apiMocks = vi.hoisted(() => ({
  listWordbooks: vi.fn(),
  activateWordbook: vi.fn(),
}))

vi.mock('../api/wordbooks', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../api/wordbooks')>()
  return { ...actual, ...apiMocks }
})

const ownerId = '9ad81de0-83b0-44ba-a67c-ad817f73eb7d'

function makeBook(overrides: Partial<Wordbook> = {}): Wordbook {
  return {
    id: '0a872f28-9b2f-47f1-8492-23f982e5bf78',
    name: 'Business English',
    description: 'Working English for product teams',
    visibility: 'private',
    status: 'ready',
    version: '3',
    entry_count: 128,
    is_active: false,
    owner_id: ownerId,
    created_by: ownerId,
    created_at: '2026-10-20T10:00:00Z',
    updated_at: '2026-10-22T10:00:00Z',
    ...overrides,
  }
}

const organizationBook = makeBook({
  id: 'organization-only',
  visibility: 'organization',
  owner_id: null,
})
const privateBook = makeBook({ name: 'My Reading Notes' })

function user(role: CurrentUser['role']): CurrentUser {
  return {
    id: ownerId,
    username: role === 'admin' ? 'admin_user' : 'member_user',
    display_name: role === 'admin' ? '管理员' : '成员',
    role,
    must_change_password: false,
  }
}

function mountView(role: CurrentUser['role'] = 'member') {
  const pinia = createPinia()
  setActivePinia(pinia)
  const auth = useAuthStore(pinia)
  auth.user = user(role)
  auth.status = 'authenticated'
  auth.initialized = true
  return mount(WordbooksView, { global: { plugins: [pinia] } })
}

function buttonByText(wrapper: VueWrapper, text: string) {
  const button = wrapper.findAll('button').find((candidate) => candidate.text().includes(text))
  if (!button) throw new Error(`Button not found: ${text}`)
  return button
}

function cardByText(wrapper: VueWrapper, text: string) {
  const card = wrapper.findAll('.wordbook-card').find((candidate) => candidate.text().includes(text))
  if (!card) throw new Error(`Card not found: ${text}`)
  return card
}

describe('WordbooksView personal shelf', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    localStorage.clear()
    sessionStorage.clear()
    apiMocks.listWordbooks.mockResolvedValue({
      items: [organizationBook, privateBook],
      total: 2,
      offset: 0,
      limit: 100,
    })
    apiMocks.activateWordbook.mockResolvedValue({
      wordbook_id: privateBook.id,
      is_active: true,
      activated_at: '2026-10-23T01:00:00Z',
    })
  })

  it('loads the personal catalog and hides organization books defensively', async () => {
    const wrapper = mountView()
    await flushPromises()

    expect(apiMocks.listWordbooks).toHaveBeenCalledWith({ offset: 0, limit: 100 })
    expect(wrapper.text()).not.toContain('Business English')
    expect(wrapper.text()).not.toContain('组织词书')
    expect(wrapper.text()).toContain('个人词书')
    expect(wrapper.text()).toContain('1–1 / 共 1 本')
    expect(localStorage.length).toBe(0)
    expect(sessionStorage.length).toBe(0)
  })

  it('guards activation against a double click and refreshes the personal catalog', async () => {
    const wrapper = mountView('admin')
    await flushPromises()
    const activateButton = cardByText(wrapper, 'My Reading Notes')
      .findAll('button')
      .find((candidate) => candidate.text().includes('设为主词书'))
    if (!activateButton) throw new Error('Activate button not found')

    void activateButton.trigger('click')
    void activateButton.trigger('click')
    await flushPromises()

    expect(apiMocks.activateWordbook).toHaveBeenCalledTimes(1)
    expect(apiMocks.activateWordbook).toHaveBeenCalledWith(privateBook.id)
    expect(apiMocks.listWordbooks).toHaveBeenCalledTimes(2)
    expect(wrapper.text()).toContain('旧词书和学习数据不会被清除')
  })

  it('paginates the full personal catalog without another API request', async () => {
    const books = [privateBook, ...Array.from({ length: 12 }, (_, index) => makeBook({
      id: `private-${index + 2}`,
      name: `Wordbook ${index + 2}`,
    }))]
    apiMocks.listWordbooks.mockResolvedValue({ items: books, total: books.length, offset: 0, limit: 100 })

    const wrapper = mountView()
    await flushPromises()
    expect(buttonByText(wrapper, '下一页').attributes('disabled')).toBeUndefined()

    const callsBefore = apiMocks.listWordbooks.mock.calls.length
    await buttonByText(wrapper, '下一页').trigger('click')
    await flushPromises()
    expect(apiMocks.listWordbooks).toHaveBeenCalledTimes(callsBefore)
    expect(wrapper.text()).toContain('13–13 / 共 13 本')
    expect(wrapper.text()).toContain('Wordbook 13')

    await buttonByText(wrapper, '上一页').trigger('click')
    await flushPromises()
    expect(wrapper.text()).toContain('1–12 / 共 13 本')
  })

  it('searches every loaded personal book without another API call', async () => {
    const wrapper = mountView()
    await flushPromises()
    const callsBefore = apiMocks.listWordbooks.mock.calls.length

    await wrapper.get('input[type="search"]').setValue('Reading')
    expect(wrapper.text()).toContain('My Reading Notes')
    expect(wrapper.text()).not.toContain('组织词书')
    expect(apiMocks.listWordbooks).toHaveBeenCalledTimes(callsBefore)
  })

  it('uses personal ownership for actions for both member and admin accounts', async () => {
    for (const role of ['member', 'admin'] as const) {
      const wrapper = mountView(role)
      await flushPromises()
      const card = cardByText(wrapper, 'My Reading Notes')
      expect(card.text()).toContain('设为主词书')
      expect(card.text()).toContain('导出')
      expect(card.text()).toContain('删除')
      wrapper.unmount()
    }
  })

  it('shows a real empty state with an import path', async () => {
    apiMocks.listWordbooks.mockResolvedValue({ items: [], total: 0, offset: 0, limit: 100 })
    const wrapper = mountView()
    await flushPromises()

    expect(wrapper.text()).toContain('还没有词书')
    expect(wrapper.text()).toContain('导入一本词书')
    await wrapper.get('.wordbook-empty button').trigger('click')
    expect(wrapper.find('.wordbook-import-dialog').exists()).toBe(true)
  })

  it('keeps the newest refreshed catalog when an older request finishes later', async () => {
    let resolveOld!: (value: { items: Wordbook[]; total: number; offset: number; limit: number }) => void
    apiMocks.listWordbooks
      .mockResolvedValueOnce({ items: [privateBook], total: 1, offset: 0, limit: 100 })
      .mockImplementationOnce(() => new Promise((resolve) => { resolveOld = resolve }))
      .mockResolvedValueOnce({
        items: [makeBook({ name: 'Newest Personal Book' })],
        total: 1,
        offset: 0,
        limit: 100,
      })

    const wrapper = mountView()
    await flushPromises()
    const refresh = buttonByText(wrapper, '刷新')
    void refresh.trigger('click')
    await flushPromises()
    await refresh.trigger('click')
    await flushPromises()
    expect(wrapper.text()).toContain('Newest Personal Book')

    resolveOld({ items: [privateBook], total: 1, offset: 0, limit: 100 })
    await flushPromises()
    expect(wrapper.text()).toContain('Newest Personal Book')
  })
})
