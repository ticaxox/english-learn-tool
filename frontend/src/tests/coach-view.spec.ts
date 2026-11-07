import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import CoachView from '../views/CoachView.vue'
import { ApiError } from '../api/errors'
import type {
  CoachAccepted,
  CoachActionReceipt,
  CoachConversation,
  CoachMessage,
} from '../api/coach'

const coachMocks = vi.hoisted(() => ({
  listCoachConversations: vi.fn(),
  createCoachConversation: vi.fn(),
  renameCoachConversation: vi.fn(),
  deleteCoachConversation: vi.fn(),
  listCoachMessages: vi.fn(),
  sendCoachMessage: vi.fn(),
  getCoachMessage: vi.fn(),
  undoCoachAction: vi.fn(),
  getCoachActionReceipt: vi.fn(),
  streamCoachMessage: vi.fn(),
}))

vi.mock('../api/coach', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../api/coach')>()
  return { ...actual, ...coachMocks }
})

const conversation: CoachConversation = {
  id: 'conversation-1', title: '本周学习计划', status: 'active', scope: 'panel', messageCount: 2,
  lastMessageAt: '2026-10-23T06:00:00Z', createdAt: '2026-10-23T05:00:00Z', updatedAt: '2026-10-23T06:00:00Z',
}
const receipt: CoachActionReceipt = {
  id: 'receipt-1', messageId: 'assistant-1', actionIndex: 0, actionType: 'adjust_daily_plan',
  summary: '把每日新词从 20 调整为 12。', status: 'applied',
  beforeState: { new_words: 20 }, afterState: { new_words: 12 }, parameters: {},
  conflictCode: null, conflictMessage: null,
  createdAt: '2026-10-23T06:00:00Z', expiresAt: '2099-10-24T06:00:00Z', undoneAt: null,
}
const userMessage: CoachMessage = {
  id: 'user-1', conversationId: conversation.id, role: 'user', status: 'completed', sequence: 1,
  content: '帮我安排今天的复习。', errorCode: null, errorMessage: null, actions: [],
  createdAt: '2026-10-23T05:59:00Z', completedAt: '2026-10-23T05:59:00Z',
}
const assistantMessage: CoachMessage = {
  id: 'assistant-1', conversationId: conversation.id, role: 'assistant', status: 'completed', sequence: 2,
  content: '先完成到期复习，再做 12 个新词。', errorCode: null, errorMessage: null, actions: [receipt],
  createdAt: '2026-10-23T06:00:00Z', completedAt: '2026-10-23T06:00:02Z',
}
const accepted: CoachAccepted = {
  messageId: 'assistant-1', status: 'queued', streamUrl: '/api/v1/coach/streams/assistant-1',
}

async function mountView() {
  const wrapper = mount(CoachView)
  await flushPromises()
  return wrapper
}

describe('coach view', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    coachMocks.listCoachConversations.mockResolvedValue({ items: [conversation], nextCursor: null, hasMore: false })
    coachMocks.listCoachMessages.mockResolvedValue({ items: [assistantMessage, userMessage], nextCursor: null, hasMore: false })
    coachMocks.createCoachConversation.mockResolvedValue({ ...conversation, id: 'conversation-2', title: '阅读训练', messageCount: 0, lastMessageAt: null })
    coachMocks.renameCoachConversation.mockImplementation(async (_id: string, title: string) => ({ ...conversation, title }))
    coachMocks.deleteCoachConversation.mockResolvedValue(undefined)
    coachMocks.sendCoachMessage.mockResolvedValue(accepted)
    coachMocks.getCoachMessage.mockResolvedValue(assistantMessage)
    coachMocks.undoCoachAction.mockResolvedValue({
      receipt: { ...receipt, status: 'undone', undoneAt: '2026-10-23T06:05:00Z' },
      message: 'The action was undone.',
    })
    coachMocks.getCoachActionReceipt.mockResolvedValue(receipt)
    coachMocks.streamCoachMessage.mockImplementation(async (_accepted: CoachAccepted, options: { onEvent: (event: unknown) => void }) => {
      options.onEvent({ sequence: 1, eventType: 'message.delta', data: { text: '先完成到期复习，再做 12 个新词。' } })
      options.onEvent({ sequence: 2, eventType: 'usage', data: { quota_kind: 'coach_messages', units: 1, limit: 50 } })
      options.onEvent({ sequence: 3, eventType: 'done', data: { status: 'completed' } })
      return 3
    })
  })

  it('renders real conversation history and action receipts', async () => {
    const wrapper = await mountView()
    expect(wrapper.text()).toContain('本周学习计划')
    expect(wrapper.text()).toContain('先完成到期复习')
    expect(wrapper.text()).toContain('调整学习计划')
    expect(wrapper.text()).toContain('把每日新词从 20 调整为 12')
    expect(wrapper.get('.coach-receipt').text()).toContain('撤销这次调整')
  })

  it('lists conversation history only on the full coach page', async () => {
    const page = mount(CoachView, { props: { surface: 'page' } })
    await flushPromises()
    expect(page.find('.coach-history').exists()).toBe(true)
    expect(page.get('.coach-history').text()).toContain('本周学习计划')
    expect(coachMocks.listCoachConversations).toHaveBeenCalledWith(
      expect.objectContaining({ scope: 'page' }),
    )

    const panel = await mountView()
    expect(panel.find('.coach-history').exists()).toBe(false)
    expect(coachMocks.listCoachConversations).toHaveBeenCalledWith(
      expect.objectContaining({ scope: 'panel' }),
    )
  })

  it('sends on Enter and displays the final server reply and usage', async () => {
    coachMocks.listCoachMessages.mockResolvedValue({ items: [], nextCursor: null, hasMore: false })
    const wrapper = await mountView()
    coachMocks.listCoachMessages.mockResolvedValue({ items: [assistantMessage, userMessage], nextCursor: null, hasMore: false })
    const textarea = wrapper.get('#coach-message-input')
    await textarea.setValue('帮我安排今天的复习。')
    await textarea.trigger('keydown', { key: 'Enter', shiftKey: false, isComposing: false })
    await flushPromises()

    expect(coachMocks.sendCoachMessage).toHaveBeenCalledWith(
      'conversation-1', '帮我安排今天的复习。', expect.any(String), { page_route: '/coach' }, { attachmentIds: [] },
    )
    expect(wrapper.text()).toContain('先完成到期复习，再做 12 个新词。')
    expect(wrapper.text()).not.toContain('本次可用')
  })

  it('no longer offers a clear-chat button', async () => {
    const wrapper = await mountView()
    expect(wrapper.find('.coach-clear-toggle').exists()).toBe(false)
  })

  it('undoes an action only after the server confirms', async () => {
    const wrapper = await mountView()
    await wrapper.get('.coach-receipt [role="button"]').trigger('click')
    await flushPromises()
    expect(coachMocks.undoCoachAction).toHaveBeenCalledWith('receipt-1')
    expect(wrapper.get('.coach-receipt').text()).toContain('已撤销')
  })

  it('disables undo after the 24-hour receipt window expires', async () => {
    coachMocks.listCoachMessages.mockResolvedValueOnce({
      items: [{ ...assistantMessage, actions: [{ ...receipt, expiresAt: '2020-01-01T00:00:00Z' }] }, userMessage],
      nextCursor: null,
      hasMore: false,
    })
    const wrapper = await mountView()
    const button = wrapper.get('.coach-receipt [role="button"]')
    expect(button.attributes('aria-disabled')).toBeDefined()
    expect(button.text()).toBe('已无法撤销')
    expect(wrapper.get('.coach-receipt').text()).toContain('已无法撤销')
  })
  it('shows quota errors with request id and keeps the draft', async () => {
    coachMocks.listCoachMessages.mockResolvedValue({ items: [], nextCursor: null, hasMore: false })
    coachMocks.sendCoachMessage.mockRejectedValueOnce(
      new ApiError(429, 'AI_QUOTA_EXHAUSTED', 'Daily quota exhausted.', null, 'coach-quota-429', true),
    )
    const wrapper = await mountView()
    const textarea = wrapper.get('#coach-message-input')
    await textarea.setValue('再问一个问题')
    await wrapper.get('.coach-composer').trigger('submit')
    await flushPromises()

    expect(wrapper.text()).toContain('今天的 AI 次数已用完')
    expect(wrapper.text()).toContain('coach-quota-429')
    expect((textarea.element as HTMLTextAreaElement).value).toBe('再问一个问题')
  })
})
