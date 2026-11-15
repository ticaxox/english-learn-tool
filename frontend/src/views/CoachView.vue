<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import AppIcon from '../components/AppIcon.vue'
import CrumbIcon from '../components/ui/CrumbIcon.vue'
import CoachImage from '../components/CoachImage.vue'
import ErrorNotice from '../components/ErrorNotice.vue'
import LoadingState from '../components/LoadingState.vue'
import CoachMarkdown from '../components/CoachMarkdown.vue'
import CoachDeleteDialog from '../components/CoachDeleteDialog.vue'
import { speak } from '../composables/useSpeechSynthesis'
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
import ArtImage from '../components/ArtImage.vue'

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

const pendingDelete = ref<{ id: string; title: string } | null>(null)

function askDelete(conversation: { id: string; title: string }): void {
  pendingDelete.value = conversation
}

async function confirmDelete(): Promise<void> {
  const target = pendingDelete.value
  pendingDelete.value = null
  if (target) await coach.removeConversation(target.id, false)
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

/** "11月12日 14:02": the day matters once a conversation outlives today. */
function messageStamp(value: string | null): string {
  if (!value) return ''
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return ''
  return new Intl.DateTimeFormat('zh-CN', {
    month: 'numeric',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  }).format(date)
}

const copiedMessageId = ref<string | null>(null)
let copiedTimer = 0

async function copyMessage(message: CoachMessage): Promise<void> {
  const text = coach.messageText(message)
  if (!text) return
  try {
    await navigator.clipboard.writeText(text)
    copiedMessageId.value = message.id
    window.clearTimeout(copiedTimer)
    copiedTimer = window.setTimeout(() => { copiedMessageId.value = null }, 1600)
  } catch {
    // The clipboard can be blocked; the button then does nothing rather than lie.
  }
}

/** Read the whole turn aloud, the same voice the word taps use. */
function speakMessage(message: CoachMessage): void {
  const text = coach.messageText(message)
  if (text) speak(text)
}

/** Put a line back in play: an answer is re-asked, your own line returns to the box. */
async function revertTo(message: CoachMessage): Promise<void> {
  if (message.role === 'assistant') {
    await retryStream(message)
    return
  }
  draft.value = coach.messageText(message)
  await focusComposer()
}
</script>

<template>
  <article class="coach-page member-coach-page coach-workspace workspace-page">

    <div class="coach-layout" :class="{ 'coach-layout--with-history': isPage }">
      <aside v-if="isPage" class="coach-history" aria-label="历史记录">
        <header class="coach-history__head">
          <ArtImage class="coach-history__mark" :set="illustration.hob" />
          <strong class="coach-history__name">AI 教练</strong>
        </header>

        <DivButton
          class="coach-history__new"
          type="button"
          @click="startConversation"
        >
          <span class="coach-history__new-disc"><AppIcon name="plus" /></span>
          <span class="coach-history__new-label">新对话</span>
        </DivButton>

        <ErrorNotice v-if="coach.conversationsError.value" :error="coach.conversationsError.value" :show-retry="false" />
        <p v-if="!coach.conversationsLoading.value && coach.conversations.value.length === 0" class="field-hint">还没有历史对话。</p>

        <div class="coach-history__scroll">
          <ul class="coach-history__list">
            <li
              v-for="conversation in coach.conversations.value"
              :key="conversation.id"
              class="coach-history__item"
              :class="{ 'is-active': conversation.id === coach.selectedConversationId.value }"
            >
              <button type="button" class="coach-history__open" @click="openConversation(conversation.id)">
                <span class="coach-history__title">{{ conversation.title }}</span>
              </button>
              <DivButton
                class="coach-history__delete"
                type="button"
                :aria-label="`删除 ${conversation.title}`"
                @click="askDelete(conversation)"
              ><CrumbIcon name="remove" :size="16" /></DivButton>
            </li>
          </ul>
          <DivButton
            v-if="coach.conversationsHasMore.value"
            class="coach-history__more"
            type="button"
            :disabled="coach.conversationsLoading.value"
            @click="coach.loadMoreConversations()"
          >加载更早的对话</DivButton>
        </div>
      </aside>

      <section class="coach-main" :class="{ panel: !isPage }" aria-label="教练对话">
        <div v-if="!coach.selectedConversation.value" class="coach-main-empty">
          <ArtImage class="coach-empty-art" :set="illustration.empty" />
          <div class="coach-main-empty__copy">
            <h2>和 Mr. Whisker 聊聊</h2>
            <p class="coach-empty-lede">学习计划、复习顺序，或者一句想改得更自然的英文。</p>
            <div class="coach-suggested-prompts" aria-label="建议提问">
              <DivButton v-for="prompt in suggestedPrompts" :key="prompt" type="button" @click="useSuggestedPrompt(prompt)">
                <span class="coach-suggested-prompts__arrow" aria-hidden="true"></span>{{ prompt }}
              </DivButton>
            </div>
            <p class="coach-empty-scope">教练能读你的词书、错题、练习记录和记忆进度，只能读你自己的。</p>
            <DivButton class="coach-empty-start" type="button" @click="startConversation">开始对话 <AppIcon name="arrow" /></DivButton>
          </div>
        </div>

        <template v-else>
          <!-- The drawer has no history rail, so it names the conversation itself. -->
          <header v-if="!isPage" class="coach-drawer-head">
            <strong>{{ coach.selectedConversation.value.title }}</strong>
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
              class="coach-load-older"
              type="button"
              :disabled="coach.messagesLoading.value"
              @click="coach.loadMoreMessages()"
            >
              加载更早消息
            </DivButton>

            <!-- An empty conversation is the same moment as no conversation:
                 the blank page, with the same invitation and the same lines. -->
            <div v-if="coach.messages.value.length === 0 && !coach.messagesLoading.value" class="coach-messages-empty">
              <ArtImage class="coach-empty-art" :set="illustration.empty" />
              <div class="coach-main-empty__copy">
                <strong>和 Mr. Whisker 聊聊</strong>
                <p class="coach-empty-lede">学习计划、复习顺序，或者一句想改得更自然的英文。</p>
                <div class="coach-suggested-prompts" aria-label="建议提问">
                  <DivButton v-for="prompt in suggestedPrompts" :key="prompt" type="button" @click="useSuggestedPrompt(prompt)">
                    <span class="coach-suggested-prompts__arrow" aria-hidden="true"></span>{{ prompt }}
                  </DivButton>
                </div>
              </div>
            </div>

            <article
              v-for="message in coach.messages.value"
              :key="message.id"
              class="coach-message"
              :class="`coach-message--${message.role}`"
            >
              <span class="coach-message-avatar" :class="`coach-message-avatar--${message.role}`" aria-hidden="true">
                <ArtImage v-if="message.role === 'assistant'" class="coach-message-avatar__art" :set="illustration.hob" />
                <span v-else class="coach-message-avatar__you">你</span>
              </span>

              <div class="coach-message-body">
                <div class="coach-message__bubble">
                  <div
                    v-if="(message.status === 'queued' || message.status === 'streaming' || coach.streamingMessageId.value === message.id) && !coach.messageText(message)"
                    class="coach-thinking"
                    role="status"
                    aria-label="AI 教练正在思考"
                  >
                    <span></span><span></span><span></span>
                  </div>
                  <CoachMarkdown v-else :text="coach.messageText(message)" />

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
                    <DivButton class="coach-message__error-retry" type="button" @click="retryStream(message)">重新连接</DivButton>
                  </div>

                  <p v-if="coach.actionNotices[message.id]" class="coach-action-notice">{{ coach.actionNotices[message.id] }}</p>
                </div>

                <div class="coach-message__meta">
                  <span v-if="message.status === 'failed'" class="coach-failed-chip">发送失败</span>
                  <span class="coach-message__stamp">{{ messageStamp(message.createdAt) }}</span>
                  <DivButton
                    class="coach-message__act"
                    type="button"
                    aria-label="朗读这条"
                    title="朗读"
                    @click="speakMessage(message)"
                  >
                    <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M11 5 6 9H3v6h3l5 4V5Z"/><path d="M15 9a4 4 0 0 1 0 6M18 6a8 8 0 0 1 0 12"/></svg>
                  </DivButton>
                  <DivButton
                    class="coach-message__act"
                    type="button"
                    :aria-label="copiedMessageId === message.id ? '已复制' : '复制这条'"
                    :title="copiedMessageId === message.id ? '已复制' : '复制'"
                    @click="copyMessage(message)"
                  >
                    <svg viewBox="0 0 24 24" aria-hidden="true"><rect x="9" y="9" width="11" height="11" rx="2"/><path d="M15 5.5A1.5 1.5 0 0 0 13.5 4H6a2 2 0 0 0-2 2v7.5A1.5 1.5 0 0 0 5.5 15"/></svg>
                  </DivButton>
                  <DivButton
                    class="coach-message__act"
                    type="button"
                    :aria-label="message.role === 'assistant' ? '重新回答这条' : '把这条放回输入框'"
                    title="回退"
                    @click="revertTo(message)"
                  >
                    <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 9h10a5 5 0 0 1 0 10h-3"/><path d="m8 5-4 4 4 4"/></svg>
                  </DivButton>
                </div>
              </div>

              <section v-if="appliedActions(message).length > 0" class="coach-actions" aria-label="已执行的调整">
                <article v-for="receipt in appliedActions(message)" :key="receipt.id" class="coach-receipt">
                  <div class="coach-receipt__body">
                    <strong class="coach-receipt__label">{{ COACH_ACTION_LABELS[receipt.actionType] }}</strong>
                    <p class="coach-receipt__summary">{{ receipt.summary }}</p>
                    <p v-if="canUndo(receipt)" class="coach-receipt__hint">可撤销至 {{ formatTime(receipt.expiresAt) }}</p>
                  </div>
                  <span class="coach-receipt__status" :class="`coach-receipt__status--${receipt.status}`">{{ actionStatusLabel(receipt) }}</span>
                  <DivButton
                    v-if="receipt.status === 'applied'"
                    class="coach-receipt__undo"
                    type="button"
                    :disabled="!canUndo(receipt) || coach.undoingReceiptId.value === receipt.id"
                    @click="undo(receipt)"
                  >
                    {{ coach.undoingReceiptId.value === receipt.id ? '正在撤销…' : (canUndo(receipt) ? '撤销' : '已无法撤销') }}
                  </DivButton>
                </article>
              </section>
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
            <label class="visually-hidden" for="coach-message-input">给 AI 教练发消息</label>
            <input
              ref="attachmentInput"
              class="visually-hidden"
              type="file"
              accept="image/png,image/jpeg,image/webp,.docx,.pdf,.txt,.md"
              multiple
              @change="onAttachmentChange"
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
                ><CrumbIcon name="remove" :size="16" /></DivButton>
              </figure>
            </div>

            <div class="coach-composer__row">
              <DivButton
                class="coach-composer__tool coach-attach"
                type="button"
                aria-label="添加附件"
                title="添加附件（图片、DOCX、TXT、Markdown）"
                :disabled="uploadingAttachment || coach.sending.value || Boolean(coach.streamingMessageId.value)"
                @click="chooseAttachments"
              >
                <AppIcon name="paperclip" />
              </DivButton>

              <div class="coach-composer__field">
                <textarea
                  id="coach-message-input"
                  ref="composer"
                  v-model="draft"
                  maxlength="8000"
                  rows="1"
                  :disabled="coach.sending.value || Boolean(coach.streamingMessageId.value)"
                  @keydown="onComposerKeydown"
                />
              </div>

              <DivButton
                v-if="dictation.supported.value"
                class="coach-composer__tool coach-dictate"
                :class="{ 'is-listening': dictation.listening.value }"
                type="button"
                :aria-pressed="dictation.listening.value"
                :aria-label="dictation.listening.value ? '正在听…' : '语音输入'"
                :title="dictation.listening.value ? '正在听…' : '语音输入'"
                :disabled="coach.sending.value || Boolean(coach.streamingMessageId.value)"
                @click="dictation.toggle()"
              >
                <AppIcon name="microphone" />
              </DivButton>

              <DivButton
                class="coach-composer__send"
                type="submit"
                aria-label="发送消息"
                title="发送"
                :disabled="(!draft.trim() && pendingAttachments.length === 0) || coach.sending.value || Boolean(coach.streamingMessageId.value)"
              >
                <AppIcon name="send" />
              </DivButton>
            </div>

            <p v-if="dictation.error.value" class="field-hint coach-dictate-error" role="status">{{ dictation.error.value }}</p>
          </form>
        </template>
      </section>
    </div>

    <CoachDeleteDialog
      v-if="pendingDelete"
      :title="pendingDelete.title"
      @close="pendingDelete = null"
      @confirm="confirmDelete"
    />
  </article>
</template>
