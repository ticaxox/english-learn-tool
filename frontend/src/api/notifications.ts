/**
 * T-FE-007 notification client.
 *
 * Frozen contract: fe52cf2b3c1a7b5fe6e7bb0dd9ba8ee67796c7bc
 * OpenAPI raw: 8309ee0357078fd33a3aa2a86fe295be3066cfefa8e64eeb8a1e39a43e7feb26
 * OpenAPI semantic: 82a0889527c26881013f62e211228cb63866216a3ef27b558c8122f58dfd1aa8
 *
 * The server is the only source of truth for inbox items, read state, unread
 * counts, and preferences. This module never persists business state locally.
 */
import { apiClient } from './client'
import { ContractError } from './errors'

export type NotificationCategory =
  | 'due_review'
  | 'today_incomplete'
  | 'streak_risk'
  | 'ai_completed'
  | 'ai_failed'
  | 'plan_adjusted'
  | 'ai_action'

export type NotificationStatus = 'pending' | 'sent' | 'suppressed' | 'merged' | 'expired'

export interface NotificationItem {
  id: string
  category: NotificationCategory
  title: string
  body: string
  status: NotificationStatus
  dedupeKey: string
  businessRefType: string | null
  businessRefId: string | null
  metadata: Record<string, unknown>
  scheduledAt: string
  sentAt: string | null
  readAt: string | null
  expiresAt: string
  createdAt: string
}

export interface NotificationList {
  items: NotificationItem[]
  nextCursor: string | null
  hasMore: boolean
}

export interface NotificationCategoryPreferences {
  dueReview: boolean
  todayIncomplete: boolean
  streakRisk: boolean
  aiCompleted: boolean
  aiFailed: boolean
  planAdjusted: boolean
  aiAction: boolean
}

export interface NotificationPreferences {
  categories: NotificationCategoryPreferences
  dndStart: string
  dndEnd: string
  dailyLimit: number
  timezone: string
}

export interface NotificationQuery {
  limit?: number
  cursor?: string | null
  unreadOnly?: boolean
}

export interface NotificationReadAllResult {
  updatedCount: number
}

export interface NotificationUnreadCount {
  unreadCount: number
}

export const NOTIFICATION_CATEGORY_LABELS: Record<NotificationCategory, string> = {
  due_review: '到期复习',
  today_incomplete: '今日任务',
  streak_risk: '学习节奏',
  ai_completed: 'AI 任务完成',
  ai_failed: 'AI 任务失败',
  plan_adjusted: '学习计划调整',
  ai_action: 'AI 教练建议',
}

export const NOTIFICATION_CATEGORY_ORDER: NotificationCategory[] = [
  'due_review',
  'today_incomplete',
  'streak_risk',
  'ai_completed',
  'ai_failed',
  'plan_adjusted',
  'ai_action',
]

const CATEGORY_KEYS: Array<[keyof NotificationCategoryPreferences, NotificationCategory]> = [
  ['dueReview', 'due_review'],
  ['todayIncomplete', 'today_incomplete'],
  ['streakRisk', 'streak_risk'],
  ['aiCompleted', 'ai_completed'],
  ['aiFailed', 'ai_failed'],
  ['planAdjusted', 'plan_adjusted'],
  ['aiAction', 'ai_action'],
]

const CATEGORIES = new Set<NotificationCategory>(NOTIFICATION_CATEGORY_ORDER)
const STATUSES = new Set<NotificationStatus>(['pending', 'sent', 'suppressed', 'merged', 'expired'])

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function requiredString(value: unknown, field: string): string {
  if (typeof value !== 'string') {
    throw new ContractError(`通知接口响应缺少字符串字段 ${field}。`)
  }
  return value
}

function optionalString(value: unknown, field: string): string | null {
  if (value === null || value === undefined) return null
  if (typeof value !== 'string') {
    throw new ContractError(`通知接口响应字段 ${field} 必须是字符串或 null。`)
  }
  return value
}

function requiredBoolean(value: unknown, field: string): boolean {
  if (typeof value !== 'boolean') {
    throw new ContractError(`通知接口响应字段 ${field} 必须是布尔值。`)
  }
  return value
}

function defaultedBoolean(value: unknown, field: string): boolean {
  if (value === undefined) return true
  return requiredBoolean(value, field)
}

function requiredNumber(value: unknown, field: string): number {
  if (typeof value !== 'number' || !Number.isFinite(value)) {
    throw new ContractError(`通知接口响应字段 ${field} 必须是数字。`)
  }
  return value
}

function defaultedNumber(value: unknown, field: string, fallback: number): number {
  if (value === undefined) return fallback
  return requiredNumber(value, field)
}

function defaultedString(value: unknown, field: string, fallback: string): string {
  if (value === undefined) return fallback
  return requiredString(value, field)
}

function parseCategory(value: unknown): NotificationCategory {
  if (typeof value !== 'string' || !CATEGORIES.has(value as NotificationCategory)) {
    throw new ContractError('通知接口返回了未在冻结契约中声明的 category。')
  }
  return value as NotificationCategory
}

function parseStatus(value: unknown): NotificationStatus {
  if (typeof value !== 'string' || !STATUSES.has(value as NotificationStatus)) {
    throw new ContractError('通知接口返回了未在冻结契约中声明的 status。')
  }
  return value as NotificationStatus
}

function parseCategoryPreferences(value: unknown): NotificationCategoryPreferences {
  if (!isRecord(value)) {
    throw new ContractError('通知偏好接口缺少 categories 对象。')
  }
  return {
    dueReview: defaultedBoolean(value.due_review, 'categories.due_review'),
    todayIncomplete: defaultedBoolean(value.today_incomplete, 'categories.today_incomplete'),
    streakRisk: defaultedBoolean(value.streak_risk, 'categories.streak_risk'),
    aiCompleted: defaultedBoolean(value.ai_completed, 'categories.ai_completed'),
    aiFailed: defaultedBoolean(value.ai_failed, 'categories.ai_failed'),
    planAdjusted: defaultedBoolean(value.plan_adjusted, 'categories.plan_adjusted'),
    aiAction: defaultedBoolean(value.ai_action, 'categories.ai_action'),
  }
}

export function parseNotificationItem(value: unknown): NotificationItem {
  if (!isRecord(value)) {
    throw new ContractError('通知列表包含非对象条目。')
  }
  const metadata = value.metadata === undefined ? {} : value.metadata
  if (!isRecord(metadata)) {
    throw new ContractError('通知接口字段 metadata 必须是对象。')
  }
  return {
    id: requiredString(value.id, 'id'),
    category: parseCategory(value.category),
    title: requiredString(value.title, 'title'),
    body: requiredString(value.body, 'body'),
    status: parseStatus(value.status),
    dedupeKey: requiredString(value.dedupe_key, 'dedupe_key'),
    businessRefType: optionalString(value.business_ref_type, 'business_ref_type'),
    businessRefId: optionalString(value.business_ref_id, 'business_ref_id'),
    metadata,
    scheduledAt: requiredString(value.scheduled_at, 'scheduled_at'),
    sentAt: optionalString(value.sent_at, 'sent_at'),
    readAt: optionalString(value.read_at, 'read_at'),
    expiresAt: requiredString(value.expires_at, 'expires_at'),
    createdAt: requiredString(value.created_at, 'created_at'),
  }
}

export function parseNotificationList(value: unknown): NotificationList {
  if (!isRecord(value) || !Array.isArray(value.items)) {
    throw new ContractError('通知列表接口缺少 items 数组。')
  }
  return {
    items: value.items.map(parseNotificationItem),
    nextCursor: optionalString(value.next_cursor, 'next_cursor'),
    hasMore: value.has_more === undefined ? false : requiredBoolean(value.has_more, 'has_more'),
  }
}

export function parseNotificationPreferences(value: unknown): NotificationPreferences {
  if (!isRecord(value)) {
    throw new ContractError('通知偏好接口未返回对象。')
  }
  return {
    categories: parseCategoryPreferences(value.categories),
    dndStart: defaultedString(value.dnd_start, 'dnd_start', '22:00'),
    dndEnd: defaultedString(value.dnd_end, 'dnd_end', '08:00'),
    dailyLimit: defaultedNumber(value.daily_limit, 'daily_limit', 3),
    timezone: defaultedString(value.timezone, 'timezone', 'Asia/Shanghai'),
  }
}

export function parseReadAllResult(value: unknown): NotificationReadAllResult {
  if (!isRecord(value)) {
    throw new ContractError('全部已读接口未返回对象。')
  }
  return { updatedCount: requiredNumber(value.updated_count, 'updated_count') }
}

export function parseUnreadCount(value: unknown): NotificationUnreadCount {
  if (!isRecord(value)) {
    throw new ContractError('未读数接口未返回对象。')
  }
  return { unreadCount: requiredNumber(value.unread_count, 'unread_count') }
}

export function buildNotificationQuery(query: NotificationQuery = {}): string {
  const params = new URLSearchParams()
  params.set('limit', String(query.limit ?? 20))
  if (query.cursor) params.set('cursor', query.cursor)
  if (query.unreadOnly) params.set('unread_only', 'true')
  return params.toString()
}

export function serializeNotificationPreferences(
  preferences: NotificationPreferences,
): Record<string, unknown> {
  const categories = Object.fromEntries(
    CATEGORY_KEYS.map(([key, apiKey]) => [apiKey, preferences.categories[key]]),
  )
  return {
    categories,
    dnd_start: preferences.dndStart,
    dnd_end: preferences.dndEnd,
    daily_limit: preferences.dailyLimit,
    timezone: preferences.timezone,
  }
}

export async function listNotifications(
  query: NotificationQuery = {},
  options: { signal?: AbortSignal } = {},
): Promise<NotificationList> {
  const payload = await apiClient.get(`/notifications?${buildNotificationQuery(query)}`, {
    signal: options.signal,
  })
  return parseNotificationList(payload)
}

export async function fetchUnreadNotificationCount(
  options: { signal?: AbortSignal } = {},
): Promise<NotificationUnreadCount> {
  const payload = await apiClient.get('/notifications/unread-count', { signal: options.signal })
  return parseUnreadCount(payload)
}

export async function markNotificationRead(
  notificationId: string,
  options: { signal?: AbortSignal } = {},
): Promise<NotificationItem> {
  const payload = await apiClient.patch(
    `/notifications/${encodeURIComponent(notificationId)}/read`,
    undefined,
    { signal: options.signal, retryCount: 0 },
  )
  return parseNotificationItem(payload)
}

export async function markAllNotificationsRead(
  options: { signal?: AbortSignal } = {},
): Promise<NotificationReadAllResult> {
  const payload = await apiClient.post('/notifications/read-all', undefined, {
    signal: options.signal,
    retryCount: 0,
  })
  return parseReadAllResult(payload)
}

export async function fetchNotificationPreferences(
  options: { signal?: AbortSignal } = {},
): Promise<NotificationPreferences> {
  const payload = await apiClient.get('/notifications/preferences', { signal: options.signal })
  return parseNotificationPreferences(payload)
}

export async function updateNotificationPreferences(
  preferences: NotificationPreferences,
  options: { signal?: AbortSignal } = {},
): Promise<NotificationPreferences> {
  const payload = await apiClient.put(
    '/notifications/preferences',
    serializeNotificationPreferences(preferences),
    { signal: options.signal, retryCount: 0 },
  )
  return parseNotificationPreferences(payload)
}
