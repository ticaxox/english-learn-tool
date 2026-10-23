import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { apiClient } from '../api/client'
import { ContractError } from '../api/errors'
import {
  buildNotificationQuery,
  fetchNotificationPreferences,
  fetchUnreadNotificationCount,
  listNotifications,
  markAllNotificationsRead,
  markNotificationRead,
  parseNotificationItem,
  parseNotificationList,
  serializeNotificationPreferences,
  updateNotificationPreferences,
  type NotificationPreferences,
} from '../api/notifications'

const notificationPayload = {
  id: '4d2fbf5a-f49d-4fe4-8f30-11d05f111111',
  category: 'due_review',
  title: '该复习了',
  body: '有 8 个单词到达复习时间。\n现在开始刚刚好。',
  status: 'sent',
  dedupe_key: 'user:1:due-review:2026-10-23',
  business_ref_type: null,
  business_ref_id: null,
  metadata: {},
  scheduled_at: '2026-10-23T02:00:00Z',
  sent_at: '2026-10-23T02:00:01Z',
  read_at: null,
  expires_at: '2026-11-22T02:00:00Z',
  created_at: '2026-10-23T02:00:00Z',
}

const preferencesPayload = {
  categories: {
    due_review: true,
    today_incomplete: true,
    streak_risk: false,
    ai_completed: true,
    ai_failed: true,
    plan_adjusted: true,
    ai_action: false,
  },
  dnd_start: '22:30',
  dnd_end: '07:45',
  daily_limit: 4,
  timezone: 'Asia/Shanghai',
}

const preferences: NotificationPreferences = {
  categories: {
    dueReview: true,
    todayIncomplete: false,
    streakRisk: true,
    aiCompleted: true,
    aiFailed: true,
    planAdjusted: false,
    aiAction: true,
  },
  dndStart: '23:00',
  dndEnd: '07:00',
  dailyLimit: 5,
  timezone: 'Asia/Shanghai',
}

function jsonResponse(payload: unknown, status = 200, requestId = 'notification-request'): Response {
  return new Response(JSON.stringify(payload), {
    status,
    headers: { 'Content-Type': 'application/json', 'X-Request-ID': requestId },
  })
}

describe('notification API contract', () => {
  beforeEach(() => {
    apiClient.clearCredentials()
    localStorage.clear()
    sessionStorage.clear()
  })

  afterEach(() => vi.unstubAllGlobals())

  it('parses snake_case notification records and preserves plain text', () => {
    const parsed = parseNotificationItem(notificationPayload)
    expect(parsed).toMatchObject({
      id: notificationPayload.id,
      category: 'due_review',
      title: '该复习了',
      readAt: null,
      businessRefType: null,
    })
    expect(parsed.body).toContain('\n')
    expect(parsed.body).not.toContain('<')
  })

  it('rejects unknown categories and malformed list envelopes', () => {
    expect(() => parseNotificationItem({ ...notificationPayload, category: 'email_push' })).toThrow(ContractError)
    expect(() => parseNotificationList({ items: null })).toThrow(ContractError)
  })

  it('builds cursor queries without inventing a default unread filter', () => {
    expect(buildNotificationQuery()).toBe('limit=20')
    expect(buildNotificationQuery({ limit: 10, cursor: 'abc+/=', unreadOnly: true }))
      .toBe('limit=10&cursor=abc%2B%2F%3D&unread_only=true')
  })

  it('loads the first page from the frozen list endpoint', async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({
      items: [notificationPayload],
      next_cursor: 'cursor-2',
      has_more: true,
    }))
    vi.stubGlobal('fetch', fetchMock)

    const page = await listNotifications({ limit: 10, unreadOnly: true })

    expect(page.items).toHaveLength(1)
    expect(page.nextCursor).toBe('cursor-2')
    expect(page.hasMore).toBe(true)
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/v1/notifications?limit=10&unread_only=true',
      expect.objectContaining({ method: 'GET' }),
    )
  })

  it('marks one item read only after parsing the server response', async () => {
    const readPayload = { ...notificationPayload, read_at: '2026-10-23T03:00:00Z' }
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(readPayload))
    vi.stubGlobal('fetch', fetchMock)

    const result = await markNotificationRead(notificationPayload.id)

    expect(result.readAt).toBe('2026-10-23T03:00:00Z')
    expect(fetchMock).toHaveBeenCalledWith(
      `/api/v1/notifications/${notificationPayload.id}/read`,
      expect.objectContaining({ method: 'PATCH', body: undefined }),
    )
  })

  it('reads unread count and marks all notifications read through documented routes', async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(jsonResponse({ unread_count: 7 }))
      .mockResolvedValueOnce(jsonResponse({ updated_count: 7 }))
    vi.stubGlobal('fetch', fetchMock)

    expect((await fetchUnreadNotificationCount()).unreadCount).toBe(7)
    expect((await markAllNotificationsRead()).updatedCount).toBe(7)
    expect(fetchMock.mock.calls[0]?.[0]).toBe('/api/v1/notifications/unread-count')
    expect(fetchMock.mock.calls[1]?.[0]).toBe('/api/v1/notifications/read-all')
    expect((fetchMock.mock.calls[1]?.[1] as RequestInit).method).toBe('POST')
  })

  it('loads and replaces preferences using the complete PUT payload', async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(jsonResponse(preferencesPayload))
      .mockResolvedValueOnce(jsonResponse(preferencesPayload))
    vi.stubGlobal('fetch', fetchMock)

    const loaded = await fetchNotificationPreferences()
    expect(loaded.categories.streakRisk).toBe(false)
    expect(loaded.dndStart).toBe('22:30')

    const saved = await updateNotificationPreferences(preferences)
    expect(saved.dailyLimit).toBe(4)
    const [url, init] = fetchMock.mock.calls[1] as [string, RequestInit]
    expect(url).toBe('/api/v1/notifications/preferences')
    expect(init.method).toBe('PUT')
    expect(JSON.parse(String(init.body))).toEqual({
      categories: {
        due_review: true,
        today_incomplete: false,
        streak_risk: true,
        ai_completed: true,
        ai_failed: true,
        plan_adjusted: false,
        ai_action: true,
      },
      dnd_start: '23:00',
      dnd_end: '07:00',
      daily_limit: 5,
      timezone: 'Asia/Shanghai',
    })
  })

  it('serializes every frozen category key', () => {
    expect(Object.keys(serializeNotificationPreferences(preferences).categories as Record<string, unknown>).sort())
      .toEqual([
        'ai_action',
        'ai_completed',
        'ai_failed',
        'due_review',
        'plan_adjusted',
        'streak_risk',
        'today_incomplete',
      ])
  })
})
