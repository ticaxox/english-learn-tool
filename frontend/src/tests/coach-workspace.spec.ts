import { beforeEach, describe, expect, it, vi } from 'vitest'
import { useCoachWorkspace, type CoachWorkspaceApi } from '../composables/useCoachWorkspace'
import { ApiError } from '../api/errors'
import type {
  CoachAccepted,
  CoachActionReceipt,
  CoachConversation,
  CoachConversationPage,
  CoachMessage,
  CoachMessagePage,
} from '../api/coach'

const conversation: CoachConversation = {
  id: 'conversation-1', title: '本周学习计划', status: 'active', scope: 'panel', messageCount: 2,
  lastMessageAt: '2026-10-23T06:00:00Z', createdAt: '2026-10-23T05:00:00Z', updatedAt: '2026-10-23T06:00:00Z',
}
const secondConversation: CoachConversation = {
  ...conversation, id: 'conversation-2', title: '阅读训练', messageCount: 0, lastMessageAt: null,
}
const userMessage: CoachMessage = {
  id: 'user-1', conversationId: conversation.id, role: 'user', status: 'completed', sequence: 1,
  content: '帮我安排今天的复习。', errorCode: null, errorMessage: null, actions: [],
  createdAt: '2026-10-23T05:59:00Z', completedAt: '2026-10-23T05:59:00Z',
}
const receipt: CoachActionReceipt = {
  id: 'receipt-1', messageId: 'assistant-1', actionIndex: 0, actionType: 'adjust_daily_plan',
  summary: '把每日新词从 20 调整为 12。', status: 'applied',
  beforeState: { new_words: 20 }, afterState: { new_words: 12 }, parameters: {},
  conflictCode: null, conflictMessage: null,
  createdAt: '2026-10-23T06:00:00Z', expiresAt: '2099-10-24T06:00:00Z', undoneAt: null,
}
const queuedAssistant: CoachMessage = {
  id: 'assistant-1', conversationId: conversation.id, role: 'assistant', status: 'queued', sequence: 2,
  content: null, errorCode: null, errorMessage: null, actions: [],
  createdAt: '2026-10-23T06:00:00Z', completedAt: null,
}
const completedAssistant: CoachMessage = {
  ...queuedAssistant, status: 'completed', content: '先完成到期复习，再做 12 个新词。', actions: [receipt],
  completedAt: '2026-10-23T06:00:03Z',
}
const accepted: CoachAccepted = {
  messageId: 'assistant-1', status: 'queued', streamUrl: '/api/v1/coach/streams/assistant-1',
}
const conversationPage: CoachConversationPage = { items: [conversation], nextCursor: null, hasMore: false }
const emptyMessagePage: CoachMessagePage = { items: [], nextCursor: null, hasMore: false }
const sentMessagePage: CoachMessagePage = { items: [queuedAssistant, userMessage], nextCursor: null, hasMore: false }

function makeApi(): CoachWorkspaceApi {
  return {
    listConversations: vi.fn(async () => conversationPage),
    createConversation: vi.fn(async () => secondConversation),
    renameConversation: vi.fn(async (_id, title) => ({ ...conversation, title })),
    deleteConversation: vi.fn(async () => undefined),
    listMessages: vi.fn(async () => emptyMessagePage),
    sendMessage: vi.fn(async () => accepted),
    getMessage: vi.fn(async () => completedAssistant),
    undoAction: vi.fn(async () => ({ receipt: { ...receipt, status: 'undone' as const, undoneAt: '2026-10-23T06:05:00Z' }, message: 'The action was undone.' })),
    getActionReceipt: vi.fn(async () => receipt),
    streamMessage: vi.fn(async (_accepted, options) => {
      options.onEvent({ sequence: 1, eventType: 'message.delta', data: { text: '先完成' } })
      options.onEvent({ sequence: 2, eventType: 'message.delta', data: { text: '到期复习。' } })
      options.onEvent({ sequence: 3, eventType: 'usage', data: { quota_kind: 'coach_messages', units: 1, limit: 50 } })
      options.onEvent({ sequence: 4, eventType: 'action.applied', data: { receipt_id: 'receipt-1', action_type: 'adjust_daily_plan', summary: '把每日新词从 20 调整为 12。' } })
      options.onEvent({ sequence: 5, eventType: 'done', data: { status: 'completed' } })
      return 5
    }),
  }
}

describe('coach workspace orchestration', () => {
  let api: CoachWorkspaceApi

  beforeEach(() => {
    api = makeApi()
  })

  it('loads a conversation and resumes a server-side streaming reply after refresh', async () => {
    const streamingAssistant: CoachMessage = { ...queuedAssistant, status: 'streaming' }
    vi.mocked(api.listMessages).mockResolvedValueOnce({ items: [streamingAssistant, userMessage], nextCursor: null, hasMore: false })
    const workspace = useCoachWorkspace(api)

    await workspace.loadConversations(true)
    await Promise.resolve()
    await Promise.resolve()

    expect(workspace.selectedConversationId.value).toBe('conversation-1')
    expect(api.streamMessage).toHaveBeenCalledWith(
      expect.objectContaining({ messageId: 'assistant-1' }),
      expect.objectContaining({ after: 0 }),
    )
    expect(workspace.messageText(completedAssistant)).toBe('先完成到期复习，再做 12 个新词。')
    expect(workspace.streamUsages['assistant-1']).toMatchObject({ units: 1, limit: 50 })
  })

  it('accepts a 202, streams deltas in order, and replaces them with final server content', async () => {
    vi.mocked(api.listMessages).mockResolvedValueOnce(emptyMessagePage).mockResolvedValueOnce(sentMessagePage)
    const workspace = useCoachWorkspace(api)
    await workspace.loadConversations(true)

    const sent = await workspace.sendMessage('帮我安排今天的复习。')

    expect(sent).toBe(true)
    expect(api.sendMessage).toHaveBeenCalledWith(
      'conversation-1', '帮我安排今天的复习。', expect.any(String), { page_route: '/coach' }, { attachmentIds: [] },
    )
    expect(workspace.messages.value.filter((message) => message.id === 'assistant-1')).toHaveLength(1)
    expect(workspace.messages.value.find((message) => message.id === 'assistant-1')?.content).toBe('先完成到期复习，再做 12 个新词。')
    expect(workspace.messages.value.find((message) => message.id === 'assistant-1')?.actions[0].status).toBe('applied')
    expect(workspace.latestUsage.value).toMatchObject({ units: 1, limit: 50 })
    expect(workspace.actionNotices['assistant-1']).toContain('把每日新词从 20 调整为 12')
    expect(workspace.actionNotices['assistant-1']).not.toContain('没有生效')
  })

  it('reuses the same idempotency key when retrying an unaccepted send', async () => {
    vi.mocked(api.listMessages).mockResolvedValueOnce(emptyMessagePage).mockResolvedValueOnce(sentMessagePage)
    vi.mocked(api.sendMessage)
      .mockRejectedValueOnce(new ApiError(0, 'NETWORK_ERROR', 'Offline.', null, null, true))
      .mockResolvedValueOnce(accepted)
    const workspace = useCoachWorkspace(api)
    await workspace.loadConversations(true)

    expect(await workspace.sendMessage('同一问题')).toBe(false)
    expect(await workspace.sendMessage('同一问题')).toBe(true)

    const calls = vi.mocked(api.sendMessage).mock.calls
    expect(calls).toHaveLength(2)
    expect(calls[0][2]).toBe(calls[1][2])
  })

  it('keeps a terminal SSE error visible instead of marking the reply complete', async () => {
    vi.mocked(api.listMessages).mockResolvedValueOnce(emptyMessagePage).mockResolvedValueOnce(sentMessagePage)
    const failedAssistant: CoachMessage = {
      ...queuedAssistant, status: 'failed', errorCode: 'AI_PROVIDER_UNAVAILABLE', errorMessage: 'Provider unavailable.',
    }
    vi.mocked(api.getMessage).mockResolvedValueOnce(failedAssistant)
    vi.mocked(api.streamMessage).mockImplementationOnce(async (_accepted, options) => {
      options.onEvent({ sequence: 1, eventType: 'message.delta', data: { text: '不完整内容' } })
      options.onEvent({ sequence: 2, eventType: 'error', data: { code: 'AI_PROVIDER_UNAVAILABLE', message: 'Provider unavailable.', retryable: true } })
      return 2
    })
    const workspace = useCoachWorkspace(api)
    await workspace.loadConversations(true)

    await workspace.sendMessage('触发失败')

    expect(workspace.streamError.value).toMatchObject({ code: 'AI_PROVIDER_UNAVAILABLE' })
    expect(workspace.messages.value.find((message) => message.id === 'assistant-1')?.status).toBe('failed')
    expect(workspace.streamTerminals['assistant-1']).toBe('failed')
  })

  it('updates a receipt to conflict after a 409 undo response', async () => {
    const assistantWithAction = { ...completedAssistant }
    vi.mocked(api.listMessages).mockResolvedValueOnce({ items: [assistantWithAction, userMessage], nextCursor: null, hasMore: false })
    vi.mocked(api.undoAction).mockRejectedValueOnce(
      new ApiError(409, 'COACH_ACTION_STATE_CHANGED', 'Changed.', null, 'undo-409', false),
    )
    vi.mocked(api.getActionReceipt).mockResolvedValueOnce({
      ...receipt,
      status: 'conflict',
      conflictCode: 'COACH_ACTION_STATE_CHANGED',
      conflictMessage: 'The resource changed.',
    })
    const workspace = useCoachWorkspace(api)
    await workspace.loadConversations(true)
    await Promise.resolve()
    await Promise.resolve()

    const result = await workspace.undoAction(receipt)

    expect(result).toBeNull()
    expect(workspace.undoError.value).toMatchObject({ requestId: 'undo-409' })
    const assistant = workspace.messages.value.find((message) => message.id === 'assistant-1')
    expect(assistant?.actions[0].status).toBe('conflict')
  })

  it('creates, renames, clears, and deletes only through the API', async () => {
    const workspace = useCoachWorkspace(api)
    await workspace.loadConversations(true)

    const created = await workspace.createConversation('阅读训练')
    expect(created?.id).toBe('conversation-2')
    expect(workspace.selectedConversationId.value).toBe('conversation-2')

    await workspace.renameConversation('conversation-2', '新的标题')
    expect(api.renameConversation).toHaveBeenCalledWith('conversation-2', '新的标题')

    await workspace.removeConversation('conversation-2', true)
    expect(api.deleteConversation).toHaveBeenCalledWith('conversation-2', true)

    await workspace.removeConversation('conversation-2', false)
    expect(api.deleteConversation).toHaveBeenCalledWith('conversation-2', false)
  })
})
