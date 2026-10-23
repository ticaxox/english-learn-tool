<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import ErrorNotice from '../components/ErrorNotice.vue'
import LoadingState from '../components/LoadingState.vue'
import { COACH_ACTION_LABELS, type CoachActionReceipt, type CoachMessage } from '../api/coach'
import { isApiError } from '../api/errors'
import { useCoachWorkspace } from '../composables/useCoachWorkspace'
import '../coach.css'

const coach = useCoachWorkspace()
const draft = ref('')
const newTitle = ref('')
const showCreate = ref(false)
const renameId = ref<string | null>(null)
const renameTitle = ref('')
const composer = ref<HTMLTextAreaElement | null>(null)
const messageArea = ref<HTMLElement | null>(null)

const lastMessage = computed(() => coach.messages.value[coach.messages.value.length - 1] ?? null)
const streamErrorRetryable = computed(() =>
  isApiError(coach.streamError.value)
  && ['NETWORK_ERROR', 'COACH_STREAM_INTERRUPTED'].includes(coach.streamError.value.code),
)

function formatTime(value: string | null): string {
  if (!value) return '尚未开始'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return new Intl.DateTimeFormat('zh-CN', { dateStyle: 'medium', timeStyle: 'short' }).format(date)
}

function roleLabel(message: CoachMessage): string {
  return message.role === 'user' ? '你' : '学习管家'
}

function actionStatusLabel(receipt: CoachActionReceipt): string {
  if (receipt.status === 'undone') return '已撤销'
  if (receipt.status === 'conflict') return '不可撤销'
  return isExpired(receipt) ? '撤销窗口已过期' : '已应用'
}

function isExpired(receipt: CoachActionReceipt): boolean {
  const expires = Date.parse(receipt.expiresAt)
  return Number.isFinite(expires) && expires <= Date.now()
}

function canUndo(receipt: CoachActionReceipt): boolean {
  return receipt.status === 'applied' && !isExpired(receipt)
}

function usageText(): string {
  const usage = coach.latestUsage.value
  if (!usage) return ''
  return `本次教练用量：${usage.units} / ${usage.limit}（${usage.quotaKind}）`
}

async function focusComposer(): Promise<void> {
  await nextTick()
  composer.value?.focus()
}

async function scrollToBottom(): Promise<void> {
  await nextTick()
  if (messageArea.value) messageArea.value.scrollTop = messageArea.value.scrollHeight
}

async function selectConversation(conversationId: string): Promise<void> {
  renameId.value = null
  await coach.selectConversation(conversationId)
  await focusComposer()
}

async function createConversation(): Promise<void> {
  const title = newTitle.value.trim()
  const created = await coach.createConversation(title || undefined)
  if (created) {
    newTitle.value = ''
    showCreate.value = false
    await focusComposer()
  }
}

function beginRename(conversationId: string, title: string): void {
  renameId.value = conversationId
  renameTitle.value = title
}

async function saveRename(): Promise<void> {
  if (!renameId.value) return
  const saved = await coach.renameConversation(renameId.value, renameTitle.value)
  if (saved) renameId.value = null
}

async function clearConversation(): Promise<void> {
  const conversation = coach.selectedConversation.value
  if (!conversation) return
  if (!window.confirm(`确认清空“${conversation.title}”的全部消息？对话标题会保留。`)) return
  await coach.removeConversation(conversation.id, true)
}

async function deleteConversation(conversationId: string, title: string): Promise<void> {
  if (!window.confirm(`确认删除对话“${title}”？删除后无法恢复。`)) return
  await coach.removeConversation(conversationId, false)
}

async function submitMessage(): Promise<void> {
  const content = draft.value.trim()
  if (!content || coach.sending.value || coach.streamingMessageId.value) return
  const sent = await coach.sendMessage(content)
  if (sent) {
    draft.value = ''
    await focusComposer()
    await scrollToBottom()
  }
}

function onComposerKeydown(event: KeyboardEvent): void {
  if (event.key === 'Enter' && !event.shiftKey && !event.isComposing) {
    event.preventDefault()
    void submitMessage()
  }
}

function retryStream(message: CoachMessage | null): void {
  if (!message || message.role !== 'assistant') return
  coach.retryStream(message)
}

async function undo(receipt: CoachActionReceipt): Promise<void> {
  await coach.undoAction(receipt)
}

watch(
  () => [coach.messages.value.length, lastMessage.value?.id, lastMessage.value?.content, lastMessage.value ? coach.messageText(lastMessage.value) : ''],
  () => { void scrollToBottom() },
)

onMounted(async () => {
  await coach.loadConversations(true)
  await focusComposer()
})

onBeforeUnmount(() => {
  coach.cancelStream()
})
</script>

<template>
  <article class="coach-page">
    <header class="coach-hero">
      <div>
        <p class="eyebrow">Moustache Coach · 长期学习对话</p>
        <h1>AI 教练工作区</h1>
        <p class="lead">
          教练会读取当前账号允许的学习数据，通过真实 SSE 给出建议。只有服务端回执确认的动作才会显示为已应用。
        </p>
      </div>
      <div class="coach-orbit" aria-hidden="true"><span></span></div>
    </header>

    <div class="coach-layout">
      <aside class="panel coach-sidebar" aria-label="教练会话列表">
        <div class="coach-sidebar__heading">
          <div>
            <p class="eyebrow">Conversations</p>
            <h2>长期对话</h2>
          </div>
          <button class="button-secondary button-small" type="button" @click="showCreate = !showCreate">
            新建
          </button>
        </div>

        <form v-if="showCreate" class="coach-create" @submit.prevent="createConversation">
          <label class="field">
            <span>对话标题（可留空）</span>
            <input v-model="newTitle" maxlength="200" placeholder="例如：本周学习计划" />
          </label>
          <div class="button-row">
            <button class="button button-small" type="submit">创建对话</button>
            <button class="button-secondary button-small" type="button" @click="showCreate = false">取消</button>
          </div>
        </form>

        <LoadingState v-if="coach.conversationsLoading.value && coach.conversations.value.length === 0" label="正在读取真实会话…" />
        <ErrorNotice
          v-else-if="coach.conversationsError.value"
          :error="coach.conversationsError.value"
          retry-label="重新读取会话"
          @retry="coach.loadConversations(true)"
        />

        <div v-else-if="coach.conversations.value.length === 0" class="coach-sidebar-empty">
          <p>还没有长期对话。</p>
          <p class="field-hint">创建一个对话后，消息和动作回执才会由服务端持久化。</p>
        </div>

        <ul v-else class="coach-conversation-list">
          <li v-for="conversation in coach.conversations.value" :key="conversation.id">
            <button
              class="coach-conversation"
              :class="{ 'coach-conversation--active': conversation.id === coach.selectedConversationId.value }"
              type="button"
              @click="selectConversation(conversation.id)"
            >
              <span class="coach-conversation__title">{{ conversation.title }}</span>
              <span class="coach-conversation__meta">{{ conversation.messageCount }} 条消息 · {{ formatTime(conversation.lastMessageAt) }}</span>
            </button>
            <div class="coach-conversation__actions">
              <button class="link-button" type="button" @click="beginRename(conversation.id, conversation.title)">改名</button>
              <button class="link-button" type="button" @click="selectConversation(conversation.id).then(clearConversation)">清空</button>
              <button class="link-button link-button--danger" type="button" @click="deleteConversation(conversation.id, conversation.title)">删除</button>
            </div>
            <form v-if="renameId === conversation.id" class="coach-rename" @submit.prevent="saveRename">
              <input v-model="renameTitle" maxlength="200" aria-label="新对话标题" />
              <button class="button button-small" type="submit">保存</button>
              <button class="button-secondary button-small" type="button" @click="renameId = null">取消</button>
            </form>
          </li>
        </ul>

        <button
          v-if="coach.conversationsHasMore.value"
          class="button-secondary button-small coach-load-more"
          type="button"
          :disabled="coach.conversationsLoading.value"
          @click="coach.loadMoreConversations()"
        >
          加载更多会话
        </button>
      </aside>

      <section class="panel coach-main" aria-label="教练对话">
        <div v-if="!coach.selectedConversation.value" class="coach-main-empty">
          <div class="coach-empty-mark" aria-hidden="true">〰</div>
          <h2>从一段长期对话开始</h2>
          <p>选择左侧会话，或新建一个。这里不会用静态回复填充空状态。</p>
          <button class="button" type="button" @click="showCreate = true">新建对话</button>
        </div>

        <template v-else>
          <header class="coach-main-header">
            <div>
              <p class="eyebrow">Current conversation</p>
              <h2>{{ coach.selectedConversation.value.title }}</h2>
              <p class="field-hint">{{ coach.selectedConversation.value.messageCount }} 条消息 · 只对当前账号可见</p>
            </div>
            <div class="button-row">
              <button class="button-secondary button-small" type="button" @click="beginRename(coach.selectedConversation.value.id, coach.selectedConversation.value.title)">改名</button>
              <button class="button-secondary button-small" type="button" @click="clearConversation">清空</button>
            </div>
          </header>

          <form v-if="renameId === coach.selectedConversation.value.id" class="coach-rename coach-rename--main" @submit.prevent="saveRename">
            <input v-model="renameTitle" maxlength="200" aria-label="新对话标题" />
            <button class="button button-small" type="submit">保存</button>
            <button class="button-secondary button-small" type="button" @click="renameId = null">取消</button>
          </form>

          <p v-if="coach.acceptedNotice.value" class="alert alert-success" role="status">{{ coach.acceptedNotice.value }}</p>
          <p v-if="coach.streamNotice.value" class="inline-note" role="status">{{ coach.streamNotice.value }}</p>

          <ErrorNotice
            v-if="coach.messagesError.value"
            :error="coach.messagesError.value"
            retry-label="重新读取消息"
            @retry="coach.loadMessages(true, true)"
          />

          <div ref="messageArea" class="coach-messages" aria-live="polite">
            <LoadingState v-if="coach.messagesLoading.value && coach.messages.value.length === 0" label="正在读取真实消息…" />
            <button
              v-if="coach.messagesHasMore.value"
              class="button-secondary button-small coach-load-older"
              type="button"
              :disabled="coach.messagesLoading.value"
              @click="coach.loadMoreMessages()"
            >
              加载更早消息
            </button>
            <div v-if="coach.messages.value.length === 0 && !coach.messagesLoading.value" class="coach-messages-empty">
              <p>这段对话还没有消息。输入一句学习问题开始。</p>
            </div>

            <article
              v-for="message in coach.messages.value"
              :key="message.id"
              class="coach-message"
              :class="`coach-message--${message.role}`"
            >
              <div class="coach-message__meta">
                <strong>{{ roleLabel(message) }}</strong>
                <span>{{ formatTime(message.createdAt) }}</span>
                <span v-if="message.status === 'streaming' || coach.streamingMessageId.value === message.id" class="coach-streaming-chip">流式接收中</span>
                <span v-else-if="message.status === 'failed'" class="coach-failed-chip">失败</span>
              </div>
              <p class="coach-message__text">{{ coach.messageText(message) || (message.status === 'queued' ? '服务端已排队，等待流式内容…' : '') }}</p>
              <p v-if="message.errorMessage" class="field-error" role="alert">{{ message.errorMessage }}</p>
              <p v-if="coach.actionNotices[message.id]" class="coach-action-notice">{{ coach.actionNotices[message.id] }}</p>

              <section v-if="message.actions.length > 0" class="coach-actions" aria-label="教练动作回执">
                <h3>动作回执</h3>
                <article v-for="receipt in message.actions" :key="receipt.id" class="coach-receipt">
                  <div class="coach-receipt__heading">
                    <strong>{{ COACH_ACTION_LABELS[receipt.actionType] }}</strong>
                    <span class="coach-receipt__status" :class="`coach-receipt__status--${receipt.status}`">{{ actionStatusLabel(receipt) }}</span>
                  </div>
                  <p>{{ receipt.summary }}</p>
                  <p class="field-hint">回执窗口截止：{{ formatTime(receipt.expiresAt) }}</p>
                  <p v-if="receipt.conflictMessage" class="field-error" role="alert">{{ receipt.conflictMessage }}</p>
                  <button
                    v-if="receipt.status === 'applied'"
                    class="button-secondary button-small"
                    type="button"
                    :disabled="!canUndo(receipt) || coach.undoingReceiptId.value === receipt.id"
                    @click="undo(receipt)"
                  >
                    {{ coach.undoingReceiptId.value === receipt.id ? '正在撤销…' : (canUndo(receipt) ? '撤销这次调整' : '撤销窗口已过期') }}
                  </button>
                </article>
              </section>
            </article>

            <ErrorNotice
              v-if="coach.streamError.value"
              :error="coach.streamError.value"
              :show-retry="streamErrorRetryable"
              retry-label="重新连接 SSE"
              @retry="retryStream(lastMessage)"
            />
          </div>

          <p v-if="usageText()" class="coach-usage">{{ usageText() }}</p>
          <ErrorNotice v-if="coach.undoError.value" :error="coach.undoError.value" :show-retry="false" />
          <ErrorNotice v-if="coach.sendError.value" :error="coach.sendError.value" :show-retry="false" />

          <form class="coach-composer" @submit.prevent="submitMessage">
            <label for="coach-message-input">给学习管家发消息</label>
            <textarea
              id="coach-message-input"
              ref="composer"
              v-model="draft"
              maxlength="8000"
              rows="3"
              placeholder="例如：帮我看看今天应该先复习什么？Enter 发送，Shift+Enter 换行。"
              :disabled="coach.sending.value || Boolean(coach.streamingMessageId.value)"
              @keydown="onComposerKeydown"
            />
            <div class="coach-composer__footer">
              <span class="field-hint">{{ draft.length }} / 8000</span>
              <button class="button" type="submit" :disabled="!draft.trim() || coach.sending.value || Boolean(coach.streamingMessageId.value)">
                {{ coach.sending.value || coach.streamingMessageId.value ? '正在接收回复…' : '发送消息' }}
              </button>
            </div>
          </form>
        </template>
      </section>
    </div>
  </article>
</template>
