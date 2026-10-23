import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { apiClient } from '../api/client'
import { ApiError, ContractError } from '../api/errors'
import {
  buildCoachQuery,
  createCoachConversation,
  deleteCoachConversation,
  parseCoachMessage,
  parseCoachSseBlock,
  readCoachSse,
  sendCoachMessage,
  streamCoachMessage,
  undoCoachAction,
  type CoachAccepted,
  type CoachStreamEvent,
} from '../api/coach'

const conversationPayload = {
  id: 'conversation-1',
  title: '本周学习计划',
  status: 'active',
  message_count: 4,
  last_message_at: '2026-10-23T06:00:00Z',
  created_at: '2026-10-23T05:00:00Z',
  updated_at: '2026-10-23T06:00:00Z',
}

const receiptPayload = {
  id: 'receipt-1',
  message_id: 'assistant-1',
  action_index: 0,
  action_type: 'adjust_daily_plan',
  summary: '把每日新词从 20 调整为 12。',
  status: 'applied',
  before_state: { new_words: 20 },
  after_state: { new_words: 12 },
  parameters: {},
  conflict_code: null,
  conflict_message: null,
  created_at: '2026-10-23T06:00:01Z',
  expires_at: '2026-10-24T06:00:01Z',
  undone_at: null,
}

const messagePayload = {
  id: 'assistant-1',
  conversation_id: 'conversation-1',
  role: 'assistant',
  status: 'completed',
  sequence: 4,
  content: '建议先完成到期复习。',
  error_code: null,
  error_message: null,
  actions: [receiptPayload],
  created_at: '2026-10-23T06:00:00Z',
  completed_at: '2026-10-23T06:00:02Z',
}

function jsonResponse(payload: unknown, status = 200): Response {
  return new Response(JSON.stringify(payload), {
    status,
    headers: { 'Content-Type': 'application/json', 'X-Request-ID': 'coach-request' },
  })
}

function sseResponse(blocks: string[]): Response {
  return new Response(blocks.join(''), {
    status: 200,
    headers: { 'Content-Type': 'text/event-stream', 'X-Request-ID': 'coach-stream' },
  })
}

function frame(sequence: number, event: string, data: Record<string, unknown>): string {
  return `id: ${sequence}\nevent: ${event}\ndata: ${JSON.stringify(data)}\n\n`
}

describe('coach API contract', () => {
  beforeEach(() => {
    apiClient.clearCredentials()
    localStorage.clear()
    sessionStorage.clear()
  })

  afterEach(() => {
    vi.useRealTimers()
    vi.restoreAllMocks()
    vi.unstubAllGlobals()
  })

  it('parses messages and action receipts without dropping server state', () => {
    const message = parseCoachMessage(messagePayload)
    expect(message).toMatchObject({
      id: 'assistant-1',
      role: 'assistant',
      status: 'completed',
      sequence: 4,
      content: '建议先完成到期复习。',
    })
    expect(message.actions[0]).toMatchObject({
      actionType: 'adjust_daily_plan',
      status: 'applied',
      summary: '把每日新词从 20 调整为 12。',
    })
  })

  it('rejects unknown roles and malformed SSE sequence ids', () => {
    expect(() => parseCoachMessage({ ...messagePayload, role: 'system' })).toThrow(ContractError)
    expect(() => parseCoachSseBlock('event: message.delta\ndata: {"text":"x"}')).toThrow(ContractError)
  })

  it('parses SSE event names, ids, and JSON data', () => {
    const event = parseCoachSseBlock('id: 7\nevent: usage\ndata: {"quota_kind":"coach_messages","units":1,"limit":50}')
    expect(event).toEqual({
      sequence: 7,
      eventType: 'usage',
      data: { quota_kind: 'coach_messages', units: 1, limit: 50 },
    })
  })

  it('streams SSE chunks in server order', async () => {
    const response = sseResponse([
      frame(1, 'message.delta', { text: '第一段' }),
      frame(2, 'message.delta', { text: '第二段' }),
      frame(3, 'done', { status: 'completed' }),
    ])
    const events = []
    for await (const event of readCoachSse(response)) events.push(event)
    expect(events.map((event) => event.sequence)).toEqual([1, 2, 3])
    expect(events[0].data.text).toBe('第一段')
  })

  it('builds query strings and sends message idempotency headers', async () => {
    const accepted = { message_id: 'assistant-1', status: 'queued', stream_url: '/api/v1/coach/streams/assistant-1' }
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(accepted, 202))
    vi.stubGlobal('fetch', fetchMock)

    expect(buildCoachQuery({ limit: 50, cursor: 'abc+/=' })).toBe('limit=50&cursor=abc%2B%2F%3D')
    const result = await sendCoachMessage('conversation-1', '帮我安排复习', 'coach-key', { page_route: '/coach' })
    expect(result).toMatchObject({ messageId: 'assistant-1', status: 'queued' })
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit]
    expect(url).toBe('/api/v1/coach/conversations/conversation-1/messages')
    expect(init.method).toBe('POST')
    expect((init.headers as Headers).get('Idempotency-Key')).toBe('coach-key')
    expect(JSON.parse(String(init.body))).toEqual({
      content: '帮我安排复习',
      page_context: { page_route: '/coach' },
    })
  })

  it('creates, clears, and undoes through documented routes', async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(jsonResponse(conversationPayload, 201))
      .mockResolvedValueOnce(new Response(null, { status: 204 }))
      .mockResolvedValueOnce(jsonResponse({ receipt: { ...receiptPayload, status: 'undone', undone_at: '2026-10-23T06:05:00Z' }, message: 'The action was undone.' }))
    vi.stubGlobal('fetch', fetchMock)

    expect((await createCoachConversation()).title).toBe('本周学习计划')
    await deleteCoachConversation('conversation-1', true)
    const undo = await undoCoachAction('receipt-1')
    expect(undo.receipt.status).toBe('undone')
    expect(fetchMock.mock.calls[1]?.[0]).toBe('/api/v1/coach/conversations/conversation-1?clear=true')
    expect(fetchMock.mock.calls[2]?.[0]).toBe('/api/v1/coach/action-receipts/receipt-1/undo')
  })

  it('reconnects after an interrupted stream and deduplicates event ids', async () => {
    vi.useFakeTimers()
    const first = sseResponse([
      frame(1, 'message.delta', { text: 'A' }),
      frame(2, 'message.delta', { text: 'B' }),
    ])
    const second = sseResponse([
      frame(2, 'message.delta', { text: 'B' }),
      frame(3, 'usage', { quota_kind: 'coach_messages', units: 1, limit: 50 }),
      frame(4, 'done', { status: 'completed' }),
    ])
    const streamSpy = vi.spyOn(apiClient, 'stream')
      .mockResolvedValueOnce(first)
      .mockResolvedValueOnce(second)
    const received: CoachStreamEvent[] = []
    const accepted: CoachAccepted = {
      messageId: 'assistant-1',
      status: 'queued',
      streamUrl: '/api/v1/coach/streams/assistant-1',
    }
    const pending = streamCoachMessage(accepted, {
      onEvent: (event) => received.push(event),
      maxReconnectAttempts: 1,
    })
    await vi.advanceTimersByTimeAsync(300)
    const cursor = await pending

    expect(cursor).toBe(4)
    expect(received.map((event) => event.sequence)).toEqual([1, 2, 3, 4])
    expect(received[2].eventType).toBe('usage')
    expect(streamSpy.mock.calls[1]?.[0]).toBe('/coach/streams/assistant-1?after=2')
    expect((streamSpy.mock.calls[1]?.[1]?.headers as HeadersInit)).toEqual({ 'Last-Event-ID': '2' })
  })

  it('ignores an absolute stream_url and uses the local message route', async () => {
    const streamSpy = vi.spyOn(apiClient, 'stream').mockResolvedValue(sseResponse([
      frame(1, 'done', { status: 'completed' }),
    ]))
    await streamCoachMessage({ messageId: 'assistant-1', streamUrl: 'https://evil.example/stream' }, {
      onEvent: () => undefined,
    })
    expect(streamSpy.mock.calls[0]?.[0]).toBe('/coach/streams/assistant-1')
  })

  it('does not retry non-retryable HTTP failures', async () => {
    const streamSpy = vi.spyOn(apiClient, 'stream').mockRejectedValue(new ApiError(403, 'COACH_FORBIDDEN', 'Denied.', null, 'req-403', false))
    await expect(streamCoachMessage({ messageId: 'assistant-1', streamUrl: '/api/v1/coach/streams/assistant-1' }, {
      onEvent: () => undefined,
      maxReconnectAttempts: 3,
    })).rejects.toMatchObject({ code: 'COACH_FORBIDDEN' })
    expect(streamSpy).toHaveBeenCalledTimes(1)
  })
})
