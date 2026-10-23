/**
 * T-FE-008 coach client.
 *
 * Frozen contract: 44f49ca23e45f359f2bf6d026e9195575685e041
 * OpenAPI raw: 99026f88…ffb3d
 * OpenAPI semantic: dfe1ca30…55a7
 *
 * All conversation/message/receipt state comes from the server. The browser
 * never stores conversation content, stream events, receipts, or undo state.
 */
import { apiClient } from './client'
import { ApiError, ContractError, isApiError } from './errors'

export type CoachConversationStatus = 'active' | 'deleted'
export type CoachMessageRole = 'user' | 'assistant'
export type CoachMessageStatus = 'queued' | 'streaming' | 'completed' | 'failed'
export type CoachActionType =
  | 'adjust_daily_plan'
  | 'adjust_notification_preferences'
  | 'start_practice'
  | 'activate_wordbook'
  | 'mark_review_focus'
export type CoachActionStatus = 'applied' | 'undone' | 'conflict'

export interface CoachConversation {
  id: string
  title: string
  status: CoachConversationStatus
  messageCount: number
  lastMessageAt: string | null
  createdAt: string
  updatedAt: string
}

export interface CoachConversationPage {
  items: CoachConversation[]
  nextCursor: string | null
  hasMore: boolean
}

export interface CoachActionReceipt {
  id: string
  messageId: string
  actionIndex: number
  actionType: CoachActionType
  summary: string
  status: CoachActionStatus
  beforeState: Record<string, unknown>
  afterState: Record<string, unknown>
  parameters: Record<string, unknown>
  conflictCode: string | null
  conflictMessage: string | null
  createdAt: string
  expiresAt: string
  undoneAt: string | null
}

export interface CoachMessage {
  id: string
  conversationId: string
  role: CoachMessageRole
  status: CoachMessageStatus
  sequence: number
  content: string | null
  errorCode: string | null
  errorMessage: string | null
  actions: CoachActionReceipt[]
  createdAt: string
  completedAt: string | null
}

export interface CoachMessagePage {
  items: CoachMessage[]
  nextCursor: string | null
  hasMore: boolean
}

export interface CoachAccepted {
  messageId: string
  status: CoachMessageStatus
  streamUrl: string
}

export interface CoachStreamEvent {
  sequence: number
  eventType: string
  data: Record<string, unknown>
}

export interface PersistedCoachStreamEvent extends CoachStreamEvent {
  id: string
  messageId: string
  createdAt: string
}

export interface CoachUndoResult {
  receipt: CoachActionReceipt
  message: string
}

export interface CoachListQuery {
  limit?: number
  cursor?: string | null
}

export interface CoachStreamOptions {
  after?: number
  signal?: AbortSignal
  maxReconnectAttempts?: number
  onEvent: (event: CoachStreamEvent) => void
}

const CONVERSATION_STATUSES = new Set<CoachConversationStatus>(['active', 'deleted'])
const MESSAGE_ROLES = new Set<CoachMessageRole>(['user', 'assistant'])
const MESSAGE_STATUSES = new Set<CoachMessageStatus>(['queued', 'streaming', 'completed', 'failed'])
const ACTION_TYPES = new Set<CoachActionType>([
  'adjust_daily_plan',
  'adjust_notification_preferences',
  'start_practice',
  'activate_wordbook',
  'mark_review_focus',
])
const ACTION_STATUSES = new Set<CoachActionStatus>(['applied', 'undone', 'conflict'])

export const COACH_ACTION_LABELS: Record<CoachActionType, string> = {
  adjust_daily_plan: '调整学习计划',
  adjust_notification_preferences: '调整通知偏好',
  start_practice: '启动练习',
  activate_wordbook: '激活词书',
  mark_review_focus: '设置重点复习',
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function requiredString(value: unknown, field: string): string {
  if (typeof value !== 'string') throw new ContractError(`教练接口响应缺少字符串字段 ${field}。`)
  return value
}

function optionalString(value: unknown, field: string): string | null {
  if (value === null || value === undefined) return null
  if (typeof value !== 'string') throw new ContractError(`教练接口响应字段 ${field} 必须是字符串或 null。`)
  return value
}

function requiredNumber(value: unknown, field: string): number {
  if (typeof value !== 'number' || !Number.isFinite(value)) {
    throw new ContractError(`教练接口响应字段 ${field} 必须是数字。`)
  }
  return value
}

function requiredBoolean(value: unknown, field: string): boolean {
  if (typeof value !== 'boolean') throw new ContractError(`教练接口响应字段 ${field} 必须是布尔值。`)
  return value
}

function objectValue(value: unknown, field: string): Record<string, unknown> {
  if (value === undefined) return {}
  if (!isRecord(value)) throw new ContractError(`教练接口响应字段 ${field} 必须是对象。`)
  return value
}

function enumValue<T extends string>(value: unknown, allowed: Set<T>, field: string): T {
  if (typeof value !== 'string' || !allowed.has(value as T)) {
    throw new ContractError(`教练接口返回了未声明的 ${field}。`)
  }
  return value as T
}

export function parseCoachActionReceipt(value: unknown): CoachActionReceipt {
  if (!isRecord(value)) throw new ContractError('教练 action receipt 不是对象。')
  return {
    id: requiredString(value.id, 'receipt.id'),
    messageId: requiredString(value.message_id, 'receipt.message_id'),
    actionIndex: requiredNumber(value.action_index, 'receipt.action_index'),
    actionType: enumValue(value.action_type, ACTION_TYPES, 'action_type'),
    summary: requiredString(value.summary, 'receipt.summary'),
    status: enumValue(value.status, ACTION_STATUSES, 'receipt.status'),
    beforeState: objectValue(value.before_state, 'receipt.before_state'),
    afterState: objectValue(value.after_state, 'receipt.after_state'),
    parameters: objectValue(value.parameters, 'receipt.parameters'),
    conflictCode: optionalString(value.conflict_code, 'receipt.conflict_code'),
    conflictMessage: optionalString(value.conflict_message, 'receipt.conflict_message'),
    createdAt: requiredString(value.created_at, 'receipt.created_at'),
    expiresAt: requiredString(value.expires_at, 'receipt.expires_at'),
    undoneAt: optionalString(value.undone_at, 'receipt.undone_at'),
  }
}

export function parseCoachConversation(value: unknown): CoachConversation {
  if (!isRecord(value)) throw new ContractError('教练会话不是对象。')
  return {
    id: requiredString(value.id, 'conversation.id'),
    title: requiredString(value.title, 'conversation.title'),
    status: enumValue(value.status, CONVERSATION_STATUSES, 'conversation.status'),
    messageCount: requiredNumber(value.message_count, 'conversation.message_count'),
    lastMessageAt: optionalString(value.last_message_at, 'conversation.last_message_at'),
    createdAt: requiredString(value.created_at, 'conversation.created_at'),
    updatedAt: requiredString(value.updated_at, 'conversation.updated_at'),
  }
}

export function parseCoachConversationPage(value: unknown): CoachConversationPage {
  if (!isRecord(value) || !Array.isArray(value.items)) {
    throw new ContractError('教练会话列表缺少 items 数组。')
  }
  return {
    items: value.items.map(parseCoachConversation),
    nextCursor: optionalString(value.next_cursor, 'conversation.next_cursor'),
    hasMore: value.has_more === undefined ? false : requiredBoolean(value.has_more, 'conversation.has_more'),
  }
}

export function parseCoachMessage(value: unknown): CoachMessage {
  if (!isRecord(value)) throw new ContractError('教练消息不是对象。')
  const actions = value.actions === undefined ? [] : value.actions
  if (!Array.isArray(actions)) throw new ContractError('教练消息 actions 必须是数组。')
  return {
    id: requiredString(value.id, 'message.id'),
    conversationId: requiredString(value.conversation_id, 'message.conversation_id'),
    role: enumValue(value.role, MESSAGE_ROLES, 'message.role'),
    status: enumValue(value.status, MESSAGE_STATUSES, 'message.status'),
    sequence: requiredNumber(value.sequence, 'message.sequence'),
    content: optionalString(value.content, 'message.content'),
    errorCode: optionalString(value.error_code, 'message.error_code'),
    errorMessage: optionalString(value.error_message, 'message.error_message'),
    actions: actions.map(parseCoachActionReceipt),
    createdAt: requiredString(value.created_at, 'message.created_at'),
    completedAt: optionalString(value.completed_at, 'message.completed_at'),
  }
}

export function parseCoachMessagePage(value: unknown): CoachMessagePage {
  if (!isRecord(value) || !Array.isArray(value.items)) {
    throw new ContractError('教练消息列表缺少 items 数组。')
  }
  return {
    items: value.items.map(parseCoachMessage),
    nextCursor: optionalString(value.next_cursor, 'message.next_cursor'),
    hasMore: value.has_more === undefined ? false : requiredBoolean(value.has_more, 'message.has_more'),
  }
}

export function parseCoachAccepted(value: unknown): CoachAccepted {
  if (!isRecord(value)) throw new ContractError('教练 202 响应不是对象。')
  return {
    messageId: requiredString(value.message_id, 'accepted.message_id'),
    status: enumValue(value.status, MESSAGE_STATUSES, 'accepted.status'),
    streamUrl: requiredString(value.stream_url, 'accepted.stream_url'),
  }
}

export function parseCoachUndo(value: unknown): CoachUndoResult {
  if (!isRecord(value)) throw new ContractError('教练撤销响应不是对象。')
  return {
    receipt: parseCoachActionReceipt(value.receipt),
    message: requiredString(value.message, 'undo.message'),
  }
}

export function parsePersistedCoachStreamEvent(value: unknown): PersistedCoachStreamEvent {
  if (!isRecord(value)) throw new ContractError('教练持久化流事件不是对象。')
  return {
    id: requiredString(value.id, 'event.id'),
    messageId: requiredString(value.message_id, 'event.message_id'),
    sequence: requiredNumber(value.sequence, 'event.sequence'),
    eventType: requiredString(value.event_type, 'event.event_type'),
    data: objectValue(value.data, 'event.data'),
    createdAt: requiredString(value.created_at, 'event.created_at'),
  }
}

export function buildCoachQuery(query: CoachListQuery = {}): string {
  const params = new URLSearchParams()
  params.set('limit', String(query.limit ?? 20))
  if (query.cursor) params.set('cursor', query.cursor)
  return params.toString()
}

export async function listCoachConversations(
  query: CoachListQuery = {},
  options: { signal?: AbortSignal } = {},
): Promise<CoachConversationPage> {
  const payload = await apiClient.get(`/coach/conversations?${buildCoachQuery(query)}`, options)
  return parseCoachConversationPage(payload)
}

export async function createCoachConversation(
  title?: string,
  options: { signal?: AbortSignal } = {},
): Promise<CoachConversation> {
  const payload = await apiClient.post('/coach/conversations', title ? { title } : {}, {
    ...options,
    retryCount: 0,
  })
  return parseCoachConversation(payload)
}

export async function renameCoachConversation(
  conversationId: string,
  title: string,
  options: { signal?: AbortSignal } = {},
): Promise<CoachConversation> {
  const payload = await apiClient.patch(
    `/coach/conversations/${encodeURIComponent(conversationId)}`,
    { title },
    { ...options, retryCount: 0 },
  )
  return parseCoachConversation(payload)
}

export async function deleteCoachConversation(
  conversationId: string,
  clearOnly = false,
  options: { signal?: AbortSignal } = {},
): Promise<void> {
  const suffix = clearOnly ? '?clear=true' : ''
  await apiClient.delete(
    `/coach/conversations/${encodeURIComponent(conversationId)}${suffix}`,
    { ...options, retryCount: 0 },
  )
}

export async function listCoachMessages(
  conversationId: string,
  query: CoachListQuery = {},
  options: { signal?: AbortSignal } = {},
): Promise<CoachMessagePage> {
  const payload = await apiClient.get(
    `/coach/conversations/${encodeURIComponent(conversationId)}/messages?${buildCoachQuery({ limit: 50, ...query })}`,
    options,
  )
  return parseCoachMessagePage(payload)
}

export async function sendCoachMessage(
  conversationId: string,
  content: string,
  idempotencyKey: string,
  pageContext: Record<string, unknown> = {},
  options: { signal?: AbortSignal } = {},
): Promise<CoachAccepted> {
  const body = Object.keys(pageContext).length > 0
    ? { content, page_context: pageContext }
    : { content }
  const payload = await apiClient.post(
    `/coach/conversations/${encodeURIComponent(conversationId)}/messages`,
    body,
    {
      ...options,
      retryCount: 0,
      headers: { 'Idempotency-Key': idempotencyKey },
    },
  )
  return parseCoachAccepted(payload)
}

export async function getCoachMessage(
  messageId: string,
  options: { signal?: AbortSignal } = {},
): Promise<CoachMessage> {
  const payload = await apiClient.get(`/coach/messages/${encodeURIComponent(messageId)}`, options)
  return parseCoachMessage(payload)
}

export async function getCoachActionReceipt(
  receiptId: string,
  options: { signal?: AbortSignal } = {},
): Promise<CoachActionReceipt> {
  const payload = await apiClient.get(`/coach/action-receipts/${encodeURIComponent(receiptId)}`, options)
  return parseCoachActionReceipt(payload)
}

export async function undoCoachAction(
  receiptId: string,
  options: { signal?: AbortSignal } = {},
): Promise<CoachUndoResult> {
  const payload = await apiClient.post(
    `/coach/action-receipts/${encodeURIComponent(receiptId)}/undo`,
    undefined,
    { ...options, retryCount: 0 },
  )
  return parseCoachUndo(payload)
}

export async function listCoachMessageEvents(
  messageId: string,
  after = 0,
  options: { signal?: AbortSignal } = {},
): Promise<PersistedCoachStreamEvent[]> {
  const payload = await apiClient.get(
    `/coach/messages/${encodeURIComponent(messageId)}/events?after=${Math.max(0, after)}`,
    options,
  )
  if (!Array.isArray(payload)) throw new ContractError('教练流事件接口未返回数组。')
  return payload.map(parsePersistedCoachStreamEvent)
}

export function parseCoachSseBlock(block: string): CoachStreamEvent | null {
  const lines = block.split('\n')
  let eventType = 'message'
  let id = ''
  const dataLines: string[] = []

  for (const rawLine of lines) {
    if (!rawLine || rawLine.startsWith(':')) continue
    const colon = rawLine.indexOf(':')
    const field = colon === -1 ? rawLine : rawLine.slice(0, colon)
    let value = colon === -1 ? '' : rawLine.slice(colon + 1)
    if (value.startsWith(' ')) value = value.slice(1)
    if (field === 'event') eventType = value
    else if (field === 'id') id = value
    else if (field === 'data') dataLines.push(value)
  }

  if (dataLines.length === 0) return null
  if (!id) throw new ContractError('教练 SSE 事件缺少 id。')
  const sequence = Number(id)
  if (!Number.isInteger(sequence) || sequence < 0) {
    throw new ContractError('教练 SSE 事件缺少合法 sequence id。')
  }
  let data: unknown
  try {
    data = JSON.parse(dataLines.join('\n'))
  } catch {
    throw new ContractError('教练 SSE 事件 data 不是合法 JSON。')
  }
  if (!isRecord(data)) throw new ContractError('教练 SSE 事件 data 必须是对象。')
  return { sequence, eventType, data }
}

export async function* readCoachSse(response: Response): AsyncGenerator<CoachStreamEvent> {
  if (!response.body) throw new ContractError('教练 SSE 响应没有可读取的 body。')
  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  try {
    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })
      buffer = buffer.replace(/\r\n/g, '\n').replace(/\r/g, '\n')
      let boundary = buffer.indexOf('\n\n')
      while (boundary >= 0) {
        const block = buffer.slice(0, boundary)
        buffer = buffer.slice(boundary + 2)
        const event = parseCoachSseBlock(block)
        if (event) yield event
        boundary = buffer.indexOf('\n\n')
      }
    }
    buffer += decoder.decode()
    buffer = buffer.replace(/\r\n/g, '\n').replace(/\r/g, '\n')
    if (buffer.trim()) {
      const event = parseCoachSseBlock(buffer)
      if (event) yield event
    }
  } finally {
    await reader.cancel().catch(() => undefined)
    reader.releaseLock()
  }
}

function abortError(): Error {
  const error = new Error('The coach stream was aborted.')
  error.name = 'AbortError'
  return error
}

function isAbort(error: unknown, signal?: AbortSignal): boolean {
  return Boolean(signal?.aborted) || (error instanceof Error && error.name === 'AbortError')
}

function wait(milliseconds: number): Promise<void> {
  return new Promise((resolve) => window.setTimeout(resolve, milliseconds))
}

function streamPath(streamUrl: string, messageId: string, after: number): string {
  const expectedPrefix = '/api/v1/coach/streams/'
  let path = streamUrl.startsWith(expectedPrefix)
    ? streamUrl.slice('/api/v1'.length)
    : `/coach/streams/${encodeURIComponent(messageId)}`
  if (after > 0) {
    const separator = path.includes('?') ? '&' : '?'
    path += `${separator}after=${after}`
  }
  return path
}

export async function streamCoachMessage(
  accepted: Pick<CoachAccepted, 'messageId' | 'streamUrl'>,
  options: CoachStreamOptions,
): Promise<number> {
  let cursor = options.after ?? 0
  let attempts = 0
  const maxAttempts = options.maxReconnectAttempts ?? 2

  while (true) {
    if (options.signal?.aborted) throw abortError()
    try {
      const headers: HeadersInit = cursor > 0 ? { 'Last-Event-ID': String(cursor) } : {}
      const response = await apiClient.stream(streamPath(accepted.streamUrl, accepted.messageId, cursor), {
        headers,
        signal: options.signal,
      })
      let terminal = false
      for await (const event of readCoachSse(response)) {
        if (event.sequence <= cursor) continue
        cursor = event.sequence
        options.onEvent(event)
        if (event.eventType === 'done' || event.eventType === 'error') {
          terminal = true
          break
        }
      }
      if (terminal) return cursor
      throw new ApiError(
        0,
        'COACH_STREAM_INTERRUPTED',
        'The coach stream ended before a terminal event.',
        null,
        apiClient.getLastRequestId(),
        true,
      )
    } catch (error) {
      if (isAbort(error, options.signal)) throw abortError()
      if (attempts >= maxAttempts) throw error
      if (isApiError(error) && !error.retryable) throw error
      attempts += 1
      await wait(300 * attempts)
    }
  }
}
