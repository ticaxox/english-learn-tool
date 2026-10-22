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

function makeBook(overrides: Partial<Wordbook> = {}): Wordbook {
  return {
    id: '0a872f28-9b2f-47f1-8492-23f982e5bf78',
    name: 'Business English',
    description: 'Working English for product teams',
    visibility: 'organization',
    status: 'ready',
    entry_count: 128,
    is_active: false,
    owner_id: null,
    owner_display_name: null,
    created_at: '2026-10-20T10:00:00Z',
    updated_at: '2026-10-22T10:00:00Z',
    import_progress: null,
    import_error: null,
    permissions: { can_activate: true, can_export: true, can_delete: true },
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
  owner_id: '9ad81de0-83b0-44ba-a67c-ad817f73eb7d',
  owner_display_name: '成员',
  permissions: { can_activate: false, can_export: true, can_delete: true },
})

function user(role: CurrentUser['role']): CurrentUser {
  return {
    id: '9ad81de0-83b0-44ba-a67c-ad817f73eb7d',
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

interface Deferred<T> {
  promise: Promise<T>
  resolve: (value: T) => void
}

function deferred<T>(): Deferred<T> {
  let resolve!: (value: T) => void
  const promise = new Promise<T>((next) => {
    resolve = next
  })
  return { promise, resolve }
}

describe('WordbooksView', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    localStorage.clear()
    sessionStorage.clear()
    apiMocks.listWordbooks.mockResolvedValue({
      items: [organizationBook, privateBook],
      next_cursor: null,
      has_more: false,
    })
    apiMocks.activateWordbook.mockResolvedValue({ active_wordbook_id: organizationBook.id, wordbook: null })
  })

  it('renders real organization and private wordbooks with the active book', async () => {
    const wrapper = mountView()
    await flushPromises()

    expect(apiMocks.listWordbooks).toHaveBeenCalledWith({
      search: '',
      visibility: '',
      cursor: null,
      limit: 12,
    })
    expect(wrapper.text()).toContain('组织词书')
    expect(wrapper.text()).toContain('Business English')
    expect(wrapper.text()).toContain('我的私有词书')
    expect(wrapper.text()).toContain('My Reading Notes')
    expect(wrapper.get('.wordbook-active-banner').text()).toContain('My Reading Notes')
    expect(localStorage.length).toBe(0)
    expect(sessionStorage.length).toBe(0)
  })

  it('guards activation against a double click and refreshes after success', async () => {
    const wrapper = mountView()
    await flushPromises()
    const activateButton = buttonByText(wrapper, '设为主词书')

    void activateButton.trigger('click')
    void activateButton.trigger('click')
    await flushPromises()

    expect(apiMocks.activateWordbook).toHaveBeenCalledTimes(1)
    expect(apiMocks.activateWordbook).toHaveBeenCalledWith(expect.any(String), expect.any(String))
    expect(apiMocks.listWordbooks).toHaveBeenCalledTimes(2)
    expect(wrapper.text()).toContain('旧词书和学习数据不会被清除')
  })

  it('only offers private import to members and both scopes to administrators', async () => {
    const memberWrapper = mountView('member')
    await flushPromises()
    await buttonByText(memberWrapper, '导入词书').trigger('click')
    const memberSelect = memberWrapper.get('.wordbook-import-dialog select')
    expect(memberSelect.text()).toContain('我的私有词书')
    expect(memberSelect.text()).not.toContain('组织词书')

    const adminWrapper = mountView('admin')
    await flushPromises()
    await buttonByText(adminWrapper, '导入词书').trigger('click')
    const adminSelect = adminWrapper.get('.wordbook-import-dialog select')
    expect(adminSelect.text()).toContain('组织词书')
    expect(adminSelect.text()).toContain('我的私有词书')
  })

  it('requires the exact organization wordbook name before deletion', async () => {
    const wrapper = mountView()
    await flushPromises()
    await buttonByText(wrapper, '删除').trigger('click')

    const confirmButton = buttonByText(wrapper, '确认启动删除')
    expect(confirmButton.attributes('disabled')).toBeDefined()

    const confirmation = wrapper.get('.wordbook-dialog input[autocomplete="off"]')
    await confirmation.setValue('Business')
    expect(confirmButton.attributes('disabled')).toBeDefined()
    await confirmation.setValue('Business English')
    expect(confirmButton.attributes('disabled')).toBeUndefined()
  })

  it('shows a real empty state with an import path', async () => {
    apiMocks.listWordbooks.mockResolvedValue({ items: [], next_cursor: null, has_more: false })
    const wrapper = mountView()
    await flushPromises()

    expect(wrapper.text()).toContain('当前筛选下还没有词书')
    expect(wrapper.text()).toContain('不会填充静态示例')
    await wrapper.get('.wordbook-empty button').trigger('click')
    expect(wrapper.find('.wordbook-import-dialog').exists()).toBe(true)
  })
  it('ignores a slower filter response after a newer filter has rendered', async () => {
    const organizationPage = deferred<{ items: Wordbook[]; next_cursor: null; has_more: false }>()
    const privatePage = deferred<{ items: Wordbook[]; next_cursor: null; has_more: false }>()
    apiMocks.listWordbooks
      .mockResolvedValueOnce({ items: [organizationBook, privateBook], next_cursor: null, has_more: false })
      .mockImplementationOnce(() => organizationPage.promise)
      .mockImplementationOnce(() => privatePage.promise)

    const wrapper = mountView()
    await flushPromises()

    await buttonByText(wrapper, '组织词书').trigger('click')
    await buttonByText(wrapper, '我的私有').trigger('click')

    privatePage.resolve({ items: [privateBook], next_cursor: null, has_more: false })
    await flushPromises()
    expect(wrapper.text()).toContain('My Reading Notes')

    organizationPage.resolve({ items: [organizationBook], next_cursor: null, has_more: false })
    await flushPromises()
    expect(wrapper.text()).toContain('My Reading Notes')
    expect(wrapper.text()).not.toContain('Business English')
  })
})
