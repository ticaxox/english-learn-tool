<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import AppIcon from '../components/AppIcon.vue'
import CoachImage from '../components/CoachImage.vue'
import ErrorNotice from '../components/ErrorNotice.vue'
import WhiskerCrumbMark from '../components/WhiskerCrumbMark.vue'
import LoadingState from '../components/LoadingState.vue'
import SpokenText from '../components/SpokenText.vue'
import {
  COACH_ACTION_LABELS,
  uploadCoachAttachment,
  type CoachActionReceipt,
  type CoachMessage,
} from '../api/coach'
import { isApiError } from '../api/errors'
import { useCoachWorkspace } from '../composables/useCoachWorkspace'
import { useSpeechRecognition } from '../composables/useSpeechRecognition'
import '../coach.css'
import { illustration } from '../assets/halloween'

const props = withDefaults(defineProps<{ surface?: 'panel' | 'page' }>(), { surface: 'panel' })
const isPage = computed(() => props.surface === 'page')
// The full-screen page keeps its own history; the floating panel never shows one.
const coach = useCoachWorkspace(undefined, props.surface)
const draft = ref('')
const dictation = useSpeechRecognition((text) => {
  draft.value = draft.value.trim() ? `${draft.value.trim()} ${text}` : text
  void focusComposer()
})

const MAX_ATTACHMENTS = 4
const MAX_IMAGE_BYTES = 5 * 1024 * 1024
const IMAGE_TYPES = ['image/png', 'image/jpeg', 'image/webp']
const DOC_EXTENSION = /\.(docx|pdf|txt|md)$/i
const attachmentInput = ref<HTMLInputElement | null>(null)
const pendingAttachments = ref<
  Array<{ id: string; filename: string; kind: 'image' | 'doc'; preview: string | null }>
>([])
const uploadingAttachment = ref(false)
const attachmentError = ref<string | null>(null)

function chooseAttachments(): void {
  attachmentInput.value?.click()
}

function clearAttachments(): void {
  for (const item of pendingAttachments.value) {
    if (item.preview) URL.revokeObjectURL(item.preview)
  }
  pendingAttachments.value = []
}

function removeAttachment(index: number): void {
  const [removed] = pendingAttachments.value.splice(index, 1)
  if (removed?.preview) URL.revokeObjectURL(removed.preview)
}

async function onAttachmentChange(event: Event): Promise<void> {
  const input = event.target as HTMLInputElement
  const files = Array.from(input.files ?? [])
  input.value = ''
  const conversation = coach.selectedConversation.value
  if (!conversation || files.length === 0) return
  attachmentError.value = null
  const room = MAX_ATTACHMENTS - pendingAttachments.value.length
  if (room <= 0) {
    attachmentError.value = '一条消息最多 4 张图片'
    return
  }
  uploadingAttachment.value = true
  try {
    for (const file of files.slice(0, room)) {
      const image = IMAGE_TYPES.includes(file.type)
      const document = DOC_EXTENSION.test(file.name)
      if (!image && !document) {
        attachmentError.value = '只支持图片、Word、PDF、TXT 或 Markdown 附件'
        continue
      }
      if (file.size > MAX_IMAGE_BYTES) {
        attachmentError.value = '单个附件不能超过 5 MB'
        continue
      }
      try {
        const uploaded = await uploadCoachAttachment(conversation.id, file)
        pendingAttachments.value.push({
          id: uploaded.id,
          filename: uploaded.filename,
          kind: image ? 'image' : 'doc',
          preview: image ? URL.createObjectURL(file) : null,
        })
      } catch {
        attachmentError.value = '附件上传失败，请重试'
      }
    }
  } finally {
    uploadingAttachment.value = false
  }
}
const composer = ref<HTMLTextAreaElement | null>(null)
const messageArea = ref<HTMLElement | null>(null)
const suggestedPrompts = [
  '帮我看看今天应该先复习什么？',
  '用一个真实场景解释我今天遇到的词。',
  '给我一个不焦虑的 10 分钟学习计划。',
]

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

/** Bracket numbers the reply actually cited; the source list lives in the admin page. */
function citedNumbers(message: CoachMessage): number[] {
  if (message.role !== 'assistant') return []
  const text = coach.messageText(message)
  const found = new Set<number>()
  for (const match of text.matchAll(/\[(\d{1,2})\]/g)) {
    const value = Number(match[1])
    if (value > 0 && value <= 6) found.add(value)
  }
  return [...found].sort((left, right) => left - right)
}

function roleLabel(message: CoachMessage): string {
  return message.role === 'user' ? '你' : 'AI 教练'
}

function actionStatusLabel(receipt: CoachActionReceipt): string {
  if (receipt.status === 'undone') return '已撤销'
  if (receipt.status === 'conflict') return '不可撤销'
  return isExpired(receipt) ? '已无法撤销' : '已应用'
}

function isExpired(receipt: CoachActionReceipt): boolean {
  const expires = Date.parse(receipt.expiresAt)
  return Number.isFinite(expires) && expires <= Date.now()
}

function canUndo(receipt: CoachActionReceipt): boolean {
  return receipt.status === 'applied' && !isExpired(receipt)
}

function appliedActions(message: CoachMessage): CoachActionReceipt[] {
  // Only actions that actually changed something are worth showing.
  return message.actions.filter((receipt) => receipt.status !== 'conflict')
}

async function focusComposer(): Promise<void> {
  await nextTick()
  composer.value?.focus()
}

async function useSuggestedPrompt(prompt: string): Promise<void> {
  draft.value = prompt
  await focusComposer()
}

async function scrollToBottom(): Promise<void> {
  await nextTick()
  if (messageArea.value) messageArea.value.scrollTop = messageArea.value.scrollHeight
}

async function startConversation(): Promise<void> {
  const created = await coach.createConversation()
  if (created) await focusComposer()
}

async function openConversation(conversationId: string): Promise<void> {
  await coach.selectConversation(conversationId)
}

async function removeConversation(conversationId: string): Promise<void> {
  if (!window.confirm('删除这段对话？记录会保留在历史里但不再显示。')) return
  await coach.removeConversation(conversationId, false)
}

function conversationTime(value: string | null): string {
  if (!value) return ''
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return ''
  return new Intl.DateTimeFormat('zh-CN', { month: 'numeric', day: 'numeric' }).format(date)
}

async function submitMessage(): Promise<void> {
  const content = draft.value.trim()
  const attachmentIds = pendingAttachments.value.map((item) => item.id)
  if ((!content && attachmentIds.length === 0) || coach.sending.value || coach.streamingMessageId.value) return
  // Clear the box as soon as it is sent; the reply may take a while.
  draft.value = ''
  await scrollToBottom()
  const sent = await coach.sendMessage(content, attachmentIds)
  if (!sent) draft.value = content
  else clearAttachments()
  await focusComposer()
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

watch(
  () => coach.selectedConversationId.value,
  () => {
    clearAttachments()
    attachmentError.value = null
  },
)

onBeforeUnmount(() => {
  coach.cancelStream()
  clearAttachments()
})
</script>

<template>
  <article class="coach-page member-coach-page coach-workspace workspace-page">

    <div class="coach-layout" :class="{ 'coach-layout--with-history': isPage }">
      <aside v-if="isPage" class="coach-history" aria-label="历史记录">
        <header class="coach-history__head">
          <strong>历史记录</strong>
          <DivButton class="button-secondary button-small" type="button" @click="startConversation">新对话</DivButton>
        </header>
        <ErrorNotice v-if="coach.conversationsError.value" :error="coach.conversationsError.value" :show-retry="false" />
        <p v-if="!coach.conversationsLoading.value && coach.conversations.value.length === 0" class="field-hint">还没有历史对话。</p>
        <ul class="coach-history__list">
          <li
            v-for="conversation in coach.conversations.value"
            :key="conversation.id"
            class="coach-history__item"
            :class="{ 'is-active': conversation.id === coach.selectedConversationId.value }"
          >
            <button type="button" class="coach-history__open" @click="openConversation(conversation.id)">
              <span class="coach-history__title">{{ conversation.title }}</span>
              <small>{{ conversation.messageCount }} 条 · {{ conversationTime(conversation.updatedAt) }}</small>
            </button>
            <DivButton
              class="coach-history__delete"
              type="button"
              :aria-label="`删除 ${conversation.title}`"
              @click="removeConversation(conversation.id)"
            >×</DivButton>
          </li>
        </ul>
        <DivButton
          v-if="coach.conversationsHasMore.value"
          class="button-secondary button-small"
          type="button"
          :disabled="coach.conversationsLoading.value"
          @click="coach.loadMoreConversations()"
        >加载更早的对话</DivButton>
      </aside>

      <section class="coach-main" :class="{ panel: !isPage }" aria-label="教练对话">
        <div v-if="!coach.selectedConversation.value" class="coach-main-empty">
          <img class="coach-empty-art" :src="illustration.empty.day" alt="" />
          <p class="eyebrow">AI 教练</p>
          <h2>和 Mr. Whisker 聊聊</h2>
          <p>学习计划、复习顺序，或者一句想改得更自然的英文。</p>
          <div class="coach-suggested-prompts" aria-label="建议提问">
            <DivButton v-for="prompt in suggestedPrompts" :key="prompt" type="button" @click="useSuggestedPrompt(prompt)">{{ prompt }}</DivButton>
          </div>
          <DivButton class="button member-primary-button" type="button" @click="startConversation">开始对话 <AppIcon name="arrow" /></DivButton>
        </div>

        <template v-else>
          <header class="coach-main-header">
            <div>
              <p class="eyebrow">当前对话</p>
              <h2>{{ coach.selectedConversation.value.title }}</h2>
              <p class="field-hint">{{ coach.selectedConversation.value.messageCount }} 条消息 · 只对当前账号可见</p>
            </div>
          </header>

          <ErrorNotice
            v-if="coach.messagesError.value"
            :error="coach.messagesError.value"
            retry-label="重新读取消息"
            @retry="coach.loadMessages(true, true)"
          />

          <div ref="messageArea" class="coach-messages" aria-live="polite">
            <LoadingState v-if="coach.messagesLoading.value && coach.messages.value.length === 0" label="正在加载消息…" />
            <DivButton
              v-if="coach.messagesHasMore.value"
              class="button-secondary button-small coach-load-older"
              type="button"
              :disabled="coach.messagesLoading.value"
              @click="coach.loadMoreMessages()"
            >
              加载更早消息
            </DivButton>
            <div v-if="coach.messages.value.length === 0 && !coach.messagesLoading.value" class="coach-messages-empty">
              <strong>和 Mr. Whisker 聊聊</strong>
              <p>学习计划、复习顺序，或者一句想改得更自然的英文。</p>
            </div>

            <article
              v-for="message in coach.messages.value"
              :key="message.id"
              class="coach-message"
              :class="`coach-message--${message.role}`"
            >
              <span class="coach-message-avatar" :class="`coach-message-avatar--${message.role}`" aria-hidden="true">
                <WhiskerCrumbMark v-if="message.role === 'assistant'" size="small" />
                <span v-else>你</span>
              </span>
              <div class="coach-message-body">
                <div class="coach-message__meta">
                  <strong>{{ roleLabel(message) }}</strong>
                  <span v-if="message.status === 'failed'" class="coach-failed-chip">发送失败</span>
                </div>
                <div
                  v-if="(message.status === 'queued' || message.status === 'streaming' || coach.streamingMessageId.value === message.id) && !coach.messageText(message)"
                  class="coach-thinking"
                  role="status"
                  aria-label="AI 教练正在思考"
                >
                  <span></span><span></span><span></span>
                </div>
                <SpokenText v-else class="coach-message__text" :text="coach.messageText(message)" />
                <p v-if="message.role === 'assistant' && citedNumbers(message).length" class="coach-message__citations">
                  <span>引用了知识库：</span>
                  <span v-for="number in citedNumbers(message)" :key="number" class="coach-citation">[{{ number }}]</span>
                </p>
                <div v-if="message.attachments?.length" class="coach-message__attachments">
                  <CoachImage
                    v-for="attachment in message.attachments ?? []"
                    :key="attachment.id"
                    :attachment="attachment"
                  />
                </div>
                <div v-if="message.errorMessage" class="coach-message__error">
                  <p class="field-error" role="alert" :title="message.errorMessage">这次没有收到教练回复。</p>
                  <DivButton class="button-secondary button-small" type="button" @click="retryStream(message)">重新连接</DivButton>
                </div>
                <p v-if="coach.actionNotices[message.id]" class="coach-action-notice">{{ coach.actionNotices[message.id] }}</p>

                <section v-if="appliedActions(message).length > 0" class="coach-actions" aria-label="已执行的调整">
                  <h3>已执行的调整</h3>
                  <article v-for="receipt in appliedActions(message)" :key="receipt.id" class="coach-receipt">
                    <div class="coach-receipt__heading">
                      <strong>{{ COACH_ACTION_LABELS[receipt.actionType] }}</strong>
                      <span class="coach-receipt__status" :class="`coach-receipt__status--${receipt.status}`">{{ actionStatusLabel(receipt) }}</span>
                    </div>
                    <p>{{ receipt.summary }}</p>
                    <p v-if="canUndo(receipt)" class="field-hint">可撤销至 {{ formatTime(receipt.expiresAt) }}</p>
                    <DivButton
                      v-if="receipt.status === 'applied'"
                      class="button-secondary button-small"
                      type="button"
                      :disabled="!canUndo(receipt) || coach.undoingReceiptId.value === receipt.id"
                      @click="undo(receipt)"
                    >
                      {{ coach.undoingReceiptId.value === receipt.id ? '正在撤销…' : (canUndo(receipt) ? '撤销这次调整' : '已无法撤销') }}
                    </DivButton>
                  </article>
                </section>
              </div>
            </article>

            <ErrorNotice
              v-if="coach.streamError.value && !coach.messages.value.some((item) => item.errorMessage)"
              :error="coach.streamError.value"
              :show-retry="streamErrorRetryable"
              retry-label="重新连接"
              @retry="retryStream(lastMessage)"
            />
          </div>

          <ErrorNotice v-if="coach.undoError.value" :error="coach.undoError.value" :show-retry="false" />
          <ErrorNotice v-if="coach.sendError.value" :error="coach.sendError.value" :show-retry="false" />

          <form class="coach-composer" @submit.prevent="submitMessage">
            <label for="coach-message-input">给 AI 教练发消息</label>
            <input
              ref="attachmentInput"
              class="visually-hidden"
              type="file"
              accept="image/png,image/jpeg,image/webp,.docx,.pdf,.txt,.md"
              multiple
              @change="onAttachmentChange"
            />
            <textarea
              id="coach-message-input"
              ref="composer"
              v-model="draft"
              maxlength="8000"
              rows="3"
              :disabled="coach.sending.value || Boolean(coach.streamingMessageId.value)"
              @keydown="onComposerKeydown"
            />
            <div v-if="pendingAttachments.length > 0" class="coach-composer__attachments">
              <figure v-for="(item, index) in pendingAttachments" :key="item.id" class="coach-attachment">
                <img v-if="item.kind === 'image' && item.preview" :src="item.preview" :alt="item.filename" />
                <span v-else class="coach-attachment__file">{{ item.filename }}</span>
                <DivButton
                  class="coach-attachment__remove"
                  type="button"
                  :aria-label="`移除 ${item.filename}`"
                  @click="removeAttachment(index)"
                >×</DivButton>
              </figure>
            </div>
            <div class="coach-composer__footer">
              <DivButton
                class="button-secondary button-small coach-attach"
                type="button"
                aria-label="添加附件"
                title="添加附件（图片、DOCX、TXT、Markdown）"
                :disabled="uploadingAttachment || coach.sending.value || Boolean(coach.streamingMessageId.value)"
                @click="chooseAttachments"
              >
                <AppIcon name="paperclip" />
              </DivButton>
              <DivButton
                v-if="dictation.supported.value"
                class="button-secondary button-small coach-dictate"
                :class="{ 'is-listening': dictation.listening.value }"
                type="button"
                :aria-pressed="dictation.listening.value"
                :disabled="coach.sending.value || Boolean(coach.streamingMessageId.value)"
                @click="dictation.toggle()"
              >
                <AppIcon name="speaker" />
                {{ dictation.listening.value ? '正在听…' : '语音输入' }}
              </DivButton>
              <DivButton class="button member-primary-button" type="submit" :disabled="(!draft.trim() && pendingAttachments.length === 0) || coach.sending.value || Boolean(coach.streamingMessageId.value)">
                {{ coach.sending.value || coach.streamingMessageId.value ? '正在接收回复…' : '发送消息' }} <AppIcon name="send" />
              </DivButton>
            </div>
            <p v-if="dictation.error.value" class="field-hint coach-dictate-error" role="status">{{ dictation.error.value }}</p>
          </form>
        </template>
      </section>
    </div>
  </article>
</template>
