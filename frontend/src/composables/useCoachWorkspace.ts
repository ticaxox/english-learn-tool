import { computed, reactive, ref } from 'vue'
import {
  createCoachConversation,
  deleteCoachConversation,
  getCoachActionReceipt,
  getCoachMessage,
  listCoachConversations,
  listCoachMessages,
  renameCoachConversation,
  sendCoachMessage,
  streamCoachMessage,
  undoCoachAction,
  type CoachAccepted,
  type CoachActionReceipt,
  type CoachConversation,
  type CoachMessage,
  type CoachStreamEvent,
  type CoachUndoResult,
} from '../api/coach'
import { ApiError, isApiError } from '../api/errors'

export interface CoachWorkspaceApi {
  listConversations: typeof listCoachConversations
  createConversation: typeof createCoachConversation
  renameConversation: typeof renameCoachConversation
  deleteConversation: typeof deleteCoachConversation
  listMessages: typeof listCoachMessages
  sendMessage: typeof sendCoachMessage
  getMessage: typeof getCoachMessage
  undoAction: typeof undoCoachAction
  getActionReceipt: typeof getCoachActionReceipt
  streamMessage: typeof streamCoachMessage
}

export const defaultCoachWorkspaceApi: CoachWorkspaceApi = {
  listConversations: listCoachConversations,
  createConversation: createCoachConversation,
  renameConversation: renameCoachConversation,
  deleteConversation: deleteCoachConversation,
  listMessages: listCoachMessages,
  sendMessage: sendCoachMessage,
  getMessage: getCoachMessage,
  undoAction: undoCoachAction,
  getActionReceipt: getCoachActionReceipt,
  streamMessage: streamCoachMessage,
}

const CONVERSATION_LIMIT = 20
const MESSAGE_LIMIT = 50

function newIdempotencyKey(): string {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') return crypto.randomUUID()
  return `coach-${Date.now()}-${Math.random().toString(16).slice(2)}`
}

function textData(event: CoachStreamEvent, field: string): string | null {
  const value = event.data[field]
  return typeof value === 'string' ? value : null
}

function numberData(event: CoachStreamEvent, field: string): number | null {
  const value = event.data[field]
  return typeof value === 'number' && Number.isFinite(value) ? value : null
}

function replaceMessage(list: CoachMessage[], updated: CoachMessage): CoachMessage[] {
  const exists = list.some((message) => message.id === updated.id)
  const next = exists
    ? list.map((message) => message.id === updated.id ? updated : message)
    : [...list, updated]
  return next.sort((left, right) => left.sequence - right.sequence)
}

function mergeMessagePage(current: CoachMessage[], incoming: CoachMessage[]): CoachMessage[] {
  const byId = new Map(current.map((message) => [message.id, message]))
  for (const message of incoming) byId.set(message.id, message)
  return [...byId.values()].sort((left, right) => left.sequence - right.sequence)
}

export function useCoachWorkspace(api: CoachWorkspaceApi = defaultCoachWorkspaceApi) {
  const conversations = ref<CoachConversation[]>([])
  const conversationsCursor = ref<string | null>(null)
  const conversationsHasMore = ref(false)
  const conversationsLoading = ref(false)
  const conversationsError = ref<unknown>(null)

  const selectedConversationId = ref<string | null>(null)
  const messages = ref<CoachMessage[]>([])
  const messagesCursor = ref<string | null>(null)
  const messagesHasMore = ref(false)
  const messagesLoading = ref(false)
  const messagesError = ref<unknown>(null)

  const sending = ref(false)
  const sendError = ref<unknown>(null)
  const acceptedNotice = ref('')
  const streamingMessageId = ref<string | null>(null)
  const streamError = ref<unknown>(null)
  const streamNotice = ref('')
  const undoError = ref<unknown>(null)
  const undoingReceiptId = ref<string | null>(null)

  const streamDrafts = reactive<Record<string, string>>({})
  const streamSequences = reactive<Record<string, number>>({})
  const streamTerminals = reactive<Record<string, 'idle' | 'completed' | 'failed'>>({})
  const streamUsages = reactive<Record<string, { quotaKind: string; units: number; limit: number } | null>>({})
  const actionNotices = reactive<Record<string, string>>({})

  const selectedConversation = computed(() =>
    conversations.value.find((conversation) => conversation.id === selectedConversationId.value) ?? null,
  )
  const latestUsage = computed(() => {
    for (let index = messages.value.length - 1; index >= 0; index -= 1) {
      const usage = streamUsages[messages.value[index].id]
      if (usage) return usage
    }
    return null
  })

  let streamController: AbortController | null = null
  let pendingSendKey: string | null = null
  let pendingSendContent = ''

  function cancelStream(): void {
    streamController?.abort()
    streamController = null
    streamingMessageId.value = null
  }

  function clearConversationView(): void {
    cancelStream()
    messages.value = []
    messagesCursor.value = null
    messagesHasMore.value = false
    messagesError.value = null
    sendError.value = null
    acceptedNotice.value = ''
    streamError.value = null
    streamNotice.value = ''
    undoError.value = null
  }

  function applyStreamEvent(messageId: string, event: CoachStreamEvent): void {
    streamSequences[messageId] = event.sequence
    if (event.eventType === 'message.delta') {
      const text = textData(event, 'text')
      if (text) streamDrafts[messageId] = `${streamDrafts[messageId] ?? ''}${text}`
      return
    }
    if (event.eventType === 'usage') {
      const units = numberData(event, 'units')
      const limit = numberData(event, 'limit')
      const quotaKind = textData(event, 'quota_kind')
      if (units !== null && limit !== null && quotaKind) {
        streamUsages[messageId] = { quotaKind, units, limit }
      }
      return
    }
    if (event.eventType === 'action.applied') {
      const summary = textData(event, 'summary')
      actionNotices[messageId] = summary
        ? `教练已应用调整：${summary}`
        : '教练已应用一项调整，正在确认结果…'
      return
    }
    if (event.eventType === 'action.rejected') {
      // The model can propose optional actions the server rejects. That is not a
      // failed user request, so keep the reply clean and leave the audit to the server.
      return
    }
    if (event.eventType === 'error') {
      const code = textData(event, 'code') ?? 'COACH_STREAM_FAILED'
      const message = textData(event, 'message') ?? '教练回复未能完成。'
      const retryable = event.data.retryable === true
      streamError.value = new ApiError(0, code, message, null, null, retryable)
      streamTerminals[messageId] = 'failed'
      return
    }
    if (event.eventType === 'done') {
      streamTerminals[messageId] = 'completed'
    }
  }

  async function refreshMessage(messageId: string): Promise<void> {
    try {
      const finalMessage = await api.getMessage(messageId)
      messages.value = replaceMessage(messages.value, finalMessage)
      if (finalMessage.content !== null) {
        delete streamDrafts[messageId]
      }
      if (finalMessage.status === 'failed' && !streamError.value) {
        streamError.value = new ApiError(
          0,
          finalMessage.errorCode ?? 'COACH_REPLY_FAILED',
          finalMessage.errorMessage ?? '教练回复失败。',
          null,
          null,
          false,
        )
      }
    } catch (error) {
      streamError.value = error
    }
  }

  async function consumeAccepted(accepted: CoachAccepted, after = 0): Promise<void> {
    cancelStream()
    const controller = new AbortController()
    streamController = controller
    streamingMessageId.value = accepted.messageId
    streamError.value = null
    streamNotice.value = '正在接收教练回复…'
    streamTerminals[accepted.messageId] = 'idle'
    streamSequences[accepted.messageId] = after
    try {
      await api.streamMessage(accepted, {
        after,
        signal: controller.signal,
        onEvent: (event) => applyStreamEvent(accepted.messageId, event),
      })
      await refreshMessage(accepted.messageId)
      streamNotice.value = streamTerminals[accepted.messageId] === 'completed'
        ? '教练已回复。'
        : '流式回复已结束。'
    } catch (error) {
      if (!controller.signal.aborted) {
        streamError.value = error
        streamNotice.value = '流式连接中断，已保留当前收到的内容。'
      }
    } finally {
      if (streamController === controller) {
        streamController = null
        streamingMessageId.value = null
      }
    }
  }

  async function resumeActiveReply(): Promise<void> {
    if (!selectedConversationId.value || streamingMessageId.value) return
    const pending = [...messages.value]
      .reverse()
      .find((message) => message.role === 'assistant' && ['queued', 'streaming'].includes(message.status))
    if (!pending) return
    const after = streamSequences[pending.id] ?? 0
    await consumeAccepted({
      messageId: pending.id,
      status: pending.status,
      streamUrl: `/api/v1/coach/streams/${pending.id}`,
    }, after)
  }

  async function loadConversations(reset = true): Promise<void> {
    if (conversationsLoading.value) return
    conversationsLoading.value = true
    conversationsError.value = null
    try {
      const page = await api.listConversations({
        limit: CONVERSATION_LIMIT,
        cursor: reset ? null : conversationsCursor.value,
      })
      conversations.value = reset ? page.items : [
        ...conversations.value,
        ...page.items.filter((item) => !conversations.value.some((current) => current.id === item.id)),
      ]
      conversationsCursor.value = page.nextCursor
      conversationsHasMore.value = page.hasMore
      if (reset && !selectedConversationId.value && conversations.value[0]) {
        await selectConversation(conversations.value[0].id)
      }
    } catch (error) {
      conversationsError.value = error
    } finally {
      conversationsLoading.value = false
    }
  }

  async function loadMoreConversations(): Promise<void> {
    if (!conversationsHasMore.value || !conversationsCursor.value) return
    await loadConversations(false)
  }

  async function loadMessages(reset = true, resume = true): Promise<void> {
    if (!selectedConversationId.value || messagesLoading.value) return
    messagesLoading.value = true
    messagesError.value = null
    if (reset) {
      messages.value = []
      messagesCursor.value = null
      messagesHasMore.value = false
    }
    try {
      const page = await api.listMessages(selectedConversationId.value, {
        limit: MESSAGE_LIMIT,
        cursor: reset ? null : messagesCursor.value,
      })
      messages.value = reset ? page.items.sort((a, b) => a.sequence - b.sequence) : mergeMessagePage(messages.value, page.items)
      messagesCursor.value = page.nextCursor
      messagesHasMore.value = page.hasMore
      if (reset && resume) await resumeActiveReply()
    } catch (error) {
      messagesError.value = error
    } finally {
      messagesLoading.value = false
    }
  }

  async function loadMoreMessages(): Promise<void> {
    if (!messagesHasMore.value || !messagesCursor.value) return
    await loadMessages(false, false)
  }

  async function selectConversation(conversationId: string): Promise<void> {
    if (selectedConversationId.value === conversationId && messages.value.length > 0) return
    selectedConversationId.value = conversationId
    clearConversationView()
    await loadMessages(true, true)
  }

  async function createConversation(title?: string): Promise<CoachConversation | null> {
    conversationsError.value = null
    try {
      const conversation = await api.createConversation(title)
      conversations.value = [conversation, ...conversations.value.filter((item) => item.id !== conversation.id)]
      selectedConversationId.value = conversation.id
      clearConversationView()
      return conversation
    } catch (error) {
      conversationsError.value = error
      return null
    }
  }

  async function renameConversation(conversationId: string, title: string): Promise<boolean> {
    const trimmed = title.trim()
    if (!trimmed) return false
    conversationsError.value = null
    try {
      const updated = await api.renameConversation(conversationId, trimmed)
      conversations.value = conversations.value.map((item) => item.id === updated.id ? updated : item)
      return true
    } catch (error) {
      conversationsError.value = error
      return false
    }
  }

  async function removeConversation(conversationId: string, clearOnly: boolean): Promise<boolean> {
    conversationsError.value = null
    try {
      await api.deleteConversation(conversationId, clearOnly)
      if (clearOnly) {
        conversations.value = conversations.value.map((item) => item.id === conversationId
          ? { ...item, messageCount: 0, lastMessageAt: null }
          : item)
        if (selectedConversationId.value === conversationId) clearConversationView()
      } else {
        conversations.value = conversations.value.filter((item) => item.id !== conversationId)
        if (selectedConversationId.value === conversationId) {
          selectedConversationId.value = conversations.value[0]?.id ?? null
          clearConversationView()
          if (selectedConversationId.value) await loadMessages(true, true)
        }
      }
      return true
    } catch (error) {
      conversationsError.value = error
      return false
    }
  }

  async function sendMessage(content: string): Promise<boolean> {
    const trimmed = content.trim()
    if (!selectedConversationId.value || !trimmed || sending.value || streamingMessageId.value) return false
    if (pendingSendKey && pendingSendContent !== trimmed) {
      pendingSendKey = null
      pendingSendContent = ''
    }
    if (!pendingSendKey) {
      pendingSendKey = newIdempotencyKey()
      pendingSendContent = trimmed
    }
    sending.value = true
    sendError.value = null
    acceptedNotice.value = ''
    try {
      const accepted = await api.sendMessage(
        selectedConversationId.value,
        trimmed,
        pendingSendKey,
        { page_route: '/coach' },
      )
      pendingSendKey = null
      pendingSendContent = ''
      acceptedNotice.value = '消息已发送，正在等待教练回复。'
      await loadMessages(true, false)
      await consumeAccepted(accepted)
      await loadConversations(true)
      return true
    } catch (error) {
      sendError.value = error
      return false
    } finally {
      sending.value = false
    }
  }

  function retryStream(message: CoachMessage): void {
    const after = streamSequences[message.id] ?? 0
    void consumeAccepted({
      messageId: message.id,
      status: message.status,
      streamUrl: `/api/v1/coach/streams/${message.id}`,
    }, after)
  }

  async function undoAction(receipt: CoachActionReceipt): Promise<CoachUndoResult | null> {
    if (undoingReceiptId.value) return null
    undoingReceiptId.value = receipt.id
    undoError.value = null
    try {
      const result = await api.undoAction(receipt.id)
      messages.value = messages.value.map((message) => ({
        ...message,
        actions: message.actions.map((action) => action.id === result.receipt.id ? result.receipt : action),
      }))
      actionNotices[receipt.messageId] = result.message
      return result
    } catch (error) {
      undoError.value = error
      if (isApiError(error) && error.status === 409) {
        try {
          const current = await api.getActionReceipt(receipt.id)
          messages.value = messages.value.map((message) => ({
            ...message,
            actions: message.actions.map((action) => action.id === current.id ? current : action),
          }))
        } catch {
          // The original 409 remains the actionable error; the receipt refresh is best effort.
        }
      }
      return null
    } finally {
      undoingReceiptId.value = null
    }
  }

  function messageText(message: CoachMessage): string {
    const base = message.content ?? ''
    if (base && message.status === 'completed') return base
    const draft = streamDrafts[message.id] ?? ''
    return base && draft.startsWith(base) ? draft : `${base}${draft}`
  }

  return {
    conversations,
    conversationsHasMore,
    conversationsLoading,
    conversationsError,
    selectedConversationId,
    selectedConversation,
    messages,
    messagesHasMore,
    messagesLoading,
    messagesError,
    sending,
    sendError,
    acceptedNotice,
    streamingMessageId,
    streamError,
    streamNotice,
    undoError,
    undoingReceiptId,
    streamDrafts,
    streamSequences,
    streamTerminals,
    streamUsages,
    actionNotices,
    latestUsage,
    loadConversations,
    loadMoreConversations,
    selectConversation,
    loadMessages,
    loadMoreMessages,
    createConversation,
    renameConversation,
    removeConversation,
    sendMessage,
    retryStream,
    undoAction,
    messageText,
    cancelStream,
  }
}
