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
    visibility: 'organization',
    status: 'ready',
    version: '3',
    entry_count: 128,
    is_active: false,
    owner_id: null,
    created_by: ownerId,
    created_at: '2026-10-20T10:00:00Z',
    updated_at: '2026-10-22T10:00:00Z',
    ...overrides,
  }
}

const organizationBook = makeBook()
const privateBook = makeBook({
  id: 'f307fcf7-f5df-49bf-a15d-35cfde1ffadd',
  name: 'My Reading Notes',
  description: 'Personal vocabulary',
  visibility: 'private',
  entry_count: 24,
  is_active: true,
  owner_id: ownerId,
  created_by: ownerId,
})

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
  if (!button) {
    throw new Error(`Button not found: ${text}`)
  }
  return button
}

function cardByText(wrapper: VueWrapper, text: string) {
  const card = wrapper.findAll('.wordbook-card').find((candidate) => candidate.text().includes(text))
  if (!card) {
    throw new Error(`Card not found: ${text}`)
  }
  return card
}

describe('WordbooksView', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    localStorage.clear()
    sessionStorage.clear()
    apiMocks.listWordbooks.mockResolvedValue({
      items: [organizationBook, privateBook],
      total: 2,
      offset: 0,
      limit: 12,
    })
    apiMocks.activateWordbook.mockResolvedValue({
      wordbook_id: organizationBook.id,
      is_active: true,
      activated_at: '2026-10-23T01:00:00Z',
    })
  })

  it('loads the documented offset page and renders organization/private books', async () => {
    const wrapper = mountView()
    await flushPromises()

    expect(apiMocks.listWordbooks).toHaveBeenCalledWith({ offset: 0, limit: 12 })
    expect(wrapper.text()).toContain('组织词书')
    expect(wrapper.text()).toContain('Business English')
    expect(wrapper.text()).toContain('我的私有词书')
    expect(wrapper.text()).toContain('My Reading Notes')
    expect(wrapper.text()).toContain('1–2 / 共 2 本')
    expect(wrapper.get('.wordbook-active-banner').text()).toContain('My Reading Notes')
    expect(localStorage.length).toBe(0)
    expect(sessionStorage.length).toBe(0)
  })

  it('guards activation against a double click and refreshes the same offset', async () => {
    const wrapper = mountView('admin')
    await flushPromises()
    const organizationCard = cardByText(wrapper, 'Business English')
    const activateButton = organizationCard
      .findAll('button')
      .find((candidate) => candidate.text().includes('设为主词书'))
    if (!activateButton) {
      throw new Error('Activate button not found')
    }

    void activateButton.trigger('click')
    void activateButton.trigger('click')
    await flushPromises()

    expect(apiMocks.activateWordbook).toHaveBeenCalledTimes(1)
    expect(apiMocks.activateWordbook).toHaveBeenCalledWith(organizationBook.id)
    expect(apiMocks.listWordbooks).toHaveBeenCalledTimes(2)
    expect(apiMocks.listWordbooks).toHaveBeenLastCalledWith({ offset: 0, limit: 12 })
    expect(wrapper.text()).toContain('旧词书和学习数据不会被清除')
  })

  it('uses offset pagination and returns to the previous page with a new request', async () => {
    apiMocks.listWordbooks
      .mockResolvedValueOnce({ items: [organizationBook, privateBook], total: 14, offset: 0, limit: 12 })
      .mockResolvedValueOnce({ items: [makeBook({ id: 'page-two-book', name: 'Page Two' })], total: 14, offset: 12, limit: 12 })
      .mockResolvedValueOnce({ items: [organizationBook, privateBook], total: 14, offset: 0, limit: 12 })

    const wrapper = mountView()
    await flushPromises()
    expect(buttonByText(wrapper, '下一页').attributes('disabled')).toBeUndefined()

    await buttonByText(wrapper, '下一页').trigger('click')
    await flushPromises()
    expect(apiMocks.listWordbooks).toHaveBeenLastCalledWith({ offset: 12, limit: 12 })
    expect(wrapper.text()).toContain('13–13 / 共 14 本')
    expect(wrapper.text()).toContain('Page Two')

    await buttonByText(wrapper, '上一页').trigger('click')
    await flushPromises()
    expect(apiMocks.listWordbooks).toHaveBeenLastCalledWith({ offset: 0, limit: 12 })
  })

  it('labels search and visibility as local current-page filters without another API call', async () => {
    const wrapper = mountView()
    await flushPromises()
    const callsBefore = apiMocks.listWordbooks.mock.calls.length

    await buttonByText(wrapper, '我的私有').trigger('click')
    expect(wrapper.text()).not.toContain('Business English')
    expect(wrapper.text()).toContain('My Reading Notes')
    expect(wrapper.text()).toContain('只作用于本页')
    expect(apiMocks.listWordbooks).toHaveBeenCalledTimes(callsBefore)

    await wrapper.get('input[type="search"]').setValue('Reading')
    expect(wrapper.text()).toContain('My Reading Notes')
    expect(apiMocks.listWordbooks).toHaveBeenCalledTimes(callsBefore)
  })

  it('derives management actions from auth and visibility without a permissions field', async () => {
    const memberWrapper = mountView('member')
    await flushPromises()

    const memberOrganization = cardByText(memberWrapper, 'Business English')
    expect(memberOrganization.text()).toContain('设为主词书')
    expect(memberOrganization.text()).not.toContain('导出')
    expect(memberOrganization.text()).not.toContain('删除')

    const memberPrivate = cardByText(memberWrapper, 'My Reading Notes')
    expect(memberPrivate.text()).toContain('导出')
    expect(memberPrivate.text()).toContain('删除')

    const adminWrapper = mountView('admin')
    await flushPromises()
    const adminOrganization = cardByText(adminWrapper, 'Business English')
    expect(adminOrganization.text()).toContain('导出')
    expect(adminOrganization.text()).toContain('删除')
  })

  it('shows a real server empty state with an import path', async () => {
    apiMocks.listWordbooks.mockResolvedValue({ items: [], total: 0, offset: 0, limit: 12 })
    const wrapper = mountView()
    await flushPromises()

    expect(wrapper.text()).toContain('还没有可见词书')
    expect(wrapper.text()).toContain('不会填充静态示例')
    await wrapper.get('.wordbook-empty button').trigger('click')
    expect(wrapper.find('.wordbook-import-dialog').exists()).toBe(true)
  })

  it('keeps the newest list response when an older request finishes later', async () => {
    let resolveOld!: (value: { items: Wordbook[]; total: number; offset: number; limit: number }) => void
    apiMocks.listWordbooks
      .mockResolvedValueOnce({ items: [organizationBook, privateBook], total: 2, offset: 0, limit: 12 })
      .mockImplementationOnce(() => new Promise((resolve) => {
        resolveOld = resolve
      }))
      .mockResolvedValueOnce({ items: [privateBook], total: 1, offset: 0, limit: 12 })

    const wrapper = mountView()
    await flushPromises()
    const refresh = buttonByText(wrapper, '刷新')

    void refresh.trigger('click')
    await flushPromises()
    await refresh.trigger('click')
    await flushPromises()
    expect(wrapper.text()).toContain('My Reading Notes')
    expect(wrapper.text()).not.toContain('Business English')

    resolveOld({ items: [organizationBook], total: 1, offset: 0, limit: 12 })
    await flushPromises()
    expect(wrapper.text()).toContain('My Reading Notes')
    expect(wrapper.text()).not.toContain('Business English')
  })
})
