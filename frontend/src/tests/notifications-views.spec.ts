import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createMemoryHistory, createRouter } from 'vue-router'
import { defineComponent, h } from 'vue'
import NotificationsView from '../views/NotificationsView.vue'
import NotificationPreferencesView from '../views/NotificationPreferencesView.vue'
import { ApiError } from '../api/errors'
import type { NotificationItem, NotificationList, NotificationPreferences } from '../api/notifications'

const notificationMocks = vi.hoisted(() => ({
  listNotifications: vi.fn(),
  fetchUnreadNotificationCount: vi.fn(),
  markNotificationRead: vi.fn(),
  markAllNotificationsRead: vi.fn(),
  fetchNotificationPreferences: vi.fn(),
  updateNotificationPreferences: vi.fn(),
}))

vi.mock('../api/notifications', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../api/notifications')>()
  return { ...actual, ...notificationMocks }
})

const StubPage = defineComponent({ render: () => h('div') })
function makeRouter() {
  return createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/notifications', name: 'notifications', component: StubPage },
      { path: '/notifications/preferences', name: 'notification-preferences', component: StubPage },
      { path: '/overview', name: 'overview', component: StubPage },
      { path: '/practice', name: 'practice', component: StubPage },
      { path: '/coach', name: 'coach', component: StubPage },
    ],
  })
}

async function mountRoute(component: Parameters<typeof mount>[0], path: string) {
  const router = makeRouter()
  await router.push(path)
  await router.isReady()
  const wrapper = mount(component, { global: { plugins: [router] } })
  await flushPromises()
  return { wrapper, router }
}

const unreadNotification: NotificationItem = {
  id: '4d2fbf5a-f49d-4fe4-8f30-11d05f111111',
  category: 'due_review',
  title: '该复习了',
  body: '<b>有 8 个单词</b>到达复习时间。\n<script>alert(1)</script>',
  status: 'sent',
  dedupeKey: 'user:1:due-review:2026-10-23',
  businessRefType: null,
  businessRefId: null,
  metadata: {},
  scheduledAt: '2026-10-23T02:00:00Z',
  sentAt: '2026-10-23T02:00:01Z',
  readAt: null,
  expiresAt: '2026-11-22T02:00:00Z',
  createdAt: '2026-10-23T02:00:00Z',
}

const readNotification: NotificationItem = {
  ...unreadNotification,
  readAt: '2026-10-23T03:00:00Z',
}

const firstPage: NotificationList = {
  items: [unreadNotification],
  nextCursor: 'cursor-page-2',
  hasMore: true,
}

const preferences: NotificationPreferences = {
  categories: {
    dueReview: true,
    todayIncomplete: true,
    streakRisk: true,
    aiCompleted: true,
    aiFailed: true,
    planAdjusted: true,
    aiAction: true,
  },
  dndStart: '22:00',
  dndEnd: '08:00',
  dailyLimit: 3,
  timezone: 'Asia/Shanghai',
}

describe('notification views', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    notificationMocks.listNotifications.mockResolvedValue(firstPage)
    notificationMocks.fetchUnreadNotificationCount.mockResolvedValue({ unreadCount: 1 })
    notificationMocks.markNotificationRead.mockResolvedValue(readNotification)
    notificationMocks.markAllNotificationsRead.mockResolvedValue({ updatedCount: 1 })
    notificationMocks.fetchNotificationPreferences.mockResolvedValue(preferences)
    notificationMocks.updateNotificationPreferences.mockImplementation(async (value: NotificationPreferences) => value)
  })

  it('renders notification text as escaped plain text, never HTML or scripts', async () => {
    const { wrapper } = await mountRoute(NotificationsView, '/notifications')
    expect(wrapper.get('.notification-plain-text').text()).toContain('<b>有 8 个单词</b>')
    expect(wrapper.find('.notification-item b').exists()).toBe(false)
    expect(wrapper.find('.notification-item script').exists()).toBe(false)
    expect(wrapper.html()).toContain('&lt;script&gt;alert(1)&lt;/script&gt;')
  })

  it('loads cursor pages and re-queries when the unread filter changes', async () => {
    notificationMocks.listNotifications
      .mockResolvedValueOnce(firstPage)
      .mockResolvedValueOnce({ items: [readNotification], nextCursor: null, hasMore: false })
      .mockResolvedValueOnce({ items: [], nextCursor: null, hasMore: false })
    const { wrapper } = await mountRoute(NotificationsView, '/notifications')

    await wrapper.findAll('button').find((button) => button.text().includes('加载更多通知'))!.trigger('click')
    await flushPromises()
    expect(notificationMocks.listNotifications).toHaveBeenLastCalledWith({
      limit: 20,
      cursor: 'cursor-page-2',
      unreadOnly: false,
    })

    await wrapper.get('.notification-toggle input').setValue(true)
    await flushPromises()
    expect(notificationMocks.listNotifications).toHaveBeenLastCalledWith({ limit: 20, unreadOnly: true })
    expect(wrapper.text()).toContain('没有未读通知')
  })

  it('updates one notification only after the server confirms it is read', async () => {
    const { wrapper } = await mountRoute(NotificationsView, '/notifications')
    const button = wrapper.findAll('button').find((candidate) => candidate.text() === '标记已读')!
    await button.trigger('click')
    await flushPromises()

    expect(notificationMocks.markNotificationRead).toHaveBeenCalledWith(unreadNotification.id)
    expect(wrapper.text()).toContain('已标记为已读')
    expect(wrapper.findAll('button').some((candidate) => candidate.text() === '标记已读')).toBe(false)
  })

  it('marks all read through the server and reloads the inbox', async () => {
    const { wrapper } = await mountRoute(NotificationsView, '/notifications')
    await wrapper.findAll('button').find((button) => button.text().includes('全部已读'))!.trigger('click')
    await flushPromises()

    expect(notificationMocks.markAllNotificationsRead).toHaveBeenCalledOnce()
    expect(notificationMocks.listNotifications.mock.calls.length).toBeGreaterThanOrEqual(2)
    expect(wrapper.text()).toContain('已将 1 条通知标为已读')
  })

  it('surfaces 401 on inbox load with request id', async () => {
    notificationMocks.listNotifications.mockRejectedValueOnce(
      new ApiError(401, 'AUTH_REQUIRED', 'Session expired.', null, 'notification-401', false),
    )
    const { wrapper } = await mountRoute(NotificationsView, '/notifications')
    expect(wrapper.text()).toContain('认证状态已失效')
    expect(wrapper.text()).toContain('notification-401')
  })

  it('surfaces 429 when unread count is temporarily rate-limited', async () => {
    notificationMocks.fetchUnreadNotificationCount.mockRejectedValueOnce(
      new ApiError(429, 'RATE_LIMITED', 'Too many requests.', null, 'notification-429', true),
    )
    const { wrapper } = await mountRoute(NotificationsView, '/notifications')
    expect(wrapper.text()).toContain('请求过于频繁')
    expect(wrapper.text()).toContain('notification-429')
    expect(wrapper.text()).toContain('该复习了')
  })

  it('surfaces 403 on mark-all and leaves the list visible', async () => {
    notificationMocks.markAllNotificationsRead.mockRejectedValueOnce(
      new ApiError(403, 'FORBIDDEN', 'Notification action denied.', null, 'notification-403', false),
    )
    const { wrapper } = await mountRoute(NotificationsView, '/notifications')
    await wrapper.findAll('button').find((button) => button.text().includes('全部已读'))!.trigger('click')
    await flushPromises()
    expect(wrapper.text()).toContain('权限不足或操作被拒绝')
    expect(wrapper.text()).toContain('notification-403')
    expect(wrapper.text()).toContain('该复习了')
  })

  it('loads real preferences and saves category and quiet-hour changes', async () => {
    const { wrapper } = await mountRoute(NotificationPreferencesView, '/notifications/preferences')
    expect(wrapper.findAll('.notification-category-option')).toHaveLength(7)
    expect(wrapper.findAll('input[type="checkbox"]')).toHaveLength(7)
    expect(wrapper.text()).toContain('仅站内')
    expect(wrapper.text()).toContain('AI 任务提醒不受免打扰和每日上限影响')

    const streakRisk = wrapper.findAll('input[type="checkbox"]')[2]
    await streakRisk.setValue(false)
    await wrapper.get('#notification-daily-limit').setValue('5')
    await wrapper.get('form').trigger('submit')
    await flushPromises()

    expect(notificationMocks.updateNotificationPreferences).toHaveBeenCalledWith(expect.objectContaining({
      categories: expect.objectContaining({ streakRisk: false }),
      dailyLimit: 5,
    }))
    expect(wrapper.text()).toContain('设置已保存')
  })

  it('surfaces 422 validation issues on preference save', async () => {
    notificationMocks.updateNotificationPreferences.mockRejectedValueOnce(
      new ApiError(422, 'VALIDATION_ERROR', 'Invalid preferences.', {
        issues: [{ path: 'dnd_start', message: 'time must use HH:MM' }],
      }, 'notification-422', false),
    )
    const { wrapper } = await mountRoute(NotificationPreferencesView, '/notifications/preferences')
    await wrapper.findAll('input[type="checkbox"]')[0].setValue(false)
    await wrapper.get('form').trigger('submit')
    await flushPromises()

    expect(wrapper.text()).toContain('提交内容有误')
    expect(wrapper.text()).toContain('time must use HH:MM')
    expect(wrapper.text()).toContain('notification-422')
  })
})
