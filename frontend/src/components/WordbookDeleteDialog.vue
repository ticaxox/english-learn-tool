<script setup lang="ts">
import { computed, onUnmounted, ref } from 'vue'
import { isApiError } from '../api/errors'
import {
  deleteWordbook,
  getWordbookDetail,
  WordbookTaskError,
  type Wordbook,
} from '../api/wordbooks'
import { useDialogA11y } from '../composables/useDialogA11y'
import ErrorNotice from './ErrorNotice.vue'

const props = defineProps<{
  wordbook: Wordbook
}>()

const emit = defineEmits<{
  close: []
  started: [wordbookId: string]
  completed: [wordbookId: string]
}>()

const confirmation = ref('')
const privateConfirmed = ref(false)
const submitting = ref(false)
const completed = ref(false)
const error = ref<unknown>(null)
const requestKey = ref<string | null>(null)
const requestSignature = ref<string | null>(null)
let active = true
const dialogRef = ref<HTMLElement | null>(null)

const exactNameRequired = computed(() => props.wordbook.visibility === 'organization')
const canSubmit = computed(() => {
  if (submitting.value || completed.value) {
    return false
  }
  return exactNameRequired.value
    ? confirmation.value === props.wordbook.name
    : privateConfirmed.value
})

function createKey(): string {
  return globalThis.crypto?.randomUUID?.() || `${Date.now()}-${Math.random()}`
}

function sleep(milliseconds: number): Promise<void> {
  return new Promise((resolve) => window.setTimeout(resolve, milliseconds))
}

async function confirmDelete(): Promise<void> {
  if (!canSubmit.value) {
    return
  }
  submitting.value = true
  error.value = null
  const signature = JSON.stringify({
    wordbook_id: props.wordbook.id,
    confirmation: confirmation.value.trim(),
  })
  if (requestSignature.value !== signature) {
    requestKey.value = createKey()
    requestSignature.value = signature
  }
  const requestIdempotencyKey = requestKey.value ?? createKey()
  requestKey.value = requestIdempotencyKey

  try {
    const receipt = await deleteWordbook(props.wordbook, confirmation.value, requestIdempotencyKey)
    emit('started', props.wordbook.id)

    if (receipt.status === 'completed') {
      completed.value = true
      requestKey.value = null
      requestSignature.value = null
      emit('completed', props.wordbook.id)
      return
    }

    for (let attempt = 0; attempt < 120 && active; attempt += 1) {
      try {
        const detail = await getWordbookDetail(props.wordbook.id)
        if (!active) {
          return
        }
        if (detail.wordbook.status === 'failed') {
          throw new WordbookTaskError(
            'WORD_BOOK_DELETE_FAILED',
            detail.wordbook.import_error || '删除清理失败，请稍后重试并查看服务端任务状态。',
          )
        }
      } catch (requestError) {
        if (isApiError(requestError) && requestError.status === 404) {
          completed.value = true
          requestKey.value = null
          requestSignature.value = null
          emit('completed', props.wordbook.id)
          return
        }
        throw requestError
      }
      if (attempt < 119) {
        await sleep(1000)
      }
    }

    throw new WordbookTaskError(
      'WORD_BOOK_DELETE_POLL_TIMEOUT',
      '在限定时间内没有确认清理完成。页面不会把超时当作删除成功，请刷新后查看真实状态。',
    )
  } catch (requestError) {
    error.value = requestError
  } finally {
    submitting.value = false
  }
}

function close(): void {
  active = false
  emit('close')
}

useDialogA11y(dialogRef, { onClose: close })

onUnmounted(() => {
  active = false
})
</script>

<template>
  <div class="dialog-backdrop" @click.self="close">
    <section
      ref="dialogRef"
      class="dialog-card wordbook-dialog"
      tabindex="-1"
      role="dialog"
      aria-modal="true"
      aria-labelledby="wordbook-delete-title"
    >
      <header class="dialog-heading">
        <div>
          <p class="eyebrow">危险操作</p>
          <h2 id="wordbook-delete-title">删除「{{ props.wordbook.name }}」</h2>
        </div>
        <button class="icon-button" type="button" aria-label="关闭删除窗口" @click="close">×</button>
      </header>

      <div class="alert alert-warning">
        <strong>删除会启动真实后台清理，不会立即从前端伪造成功。</strong>
        <ul>
          <li>词书将进入 <code>deleting</code> 状态，并阻止激活、学习会话和导出。</li>
          <li>清理范围包括该词书词条及服务端定义的关联数据；最终结果以清理任务为准。</li>
          <li v-if="props.wordbook.is_active">这是当前主词书，清理后需要重新选择或导入主词书。</li>
          <li>当前词条数：{{ props.wordbook.entry_count.toLocaleString('zh-CN') }}。</li>
        </ul>
      </div>

      <label v-if="exactNameRequired" class="field">
        <span>输入完整词书名以确认</span>
        <input v-model="confirmation" autocomplete="off" :placeholder="props.wordbook.name" :disabled="submitting || completed" />
        <span class="field-hint">必须与服务端返回的名称完全一致。</span>
      </label>

      <label v-else class="wordbook-check">
        <input v-model="privateConfirmed" type="checkbox" :disabled="submitting || completed" />
        <span>我确认删除这本私有词书及其关联学习数据。</span>
      </label>

      <ErrorNotice v-if="error" :error="error" :show-retry="false" />

      <div v-if="completed" class="alert alert-success" role="status">
        <strong>清理已完成</strong>
        <p>服务端已不再返回该词书；列表将刷新为真实状态。</p>
      </div>

      <div v-else-if="submitting" class="wordbook-task-card" role="status" aria-live="polite">
        <div class="wordbook-task-heading">
          <strong>正在等待清理完成</strong>
          <span class="spinner" aria-hidden="true"></span>
        </div>
        <p class="field-hint">只有服务端完成清理后，页面才会确认成功。关闭窗口不会把任务标记为完成。</p>
      </div>

      <footer class="dialog-actions button-row">
        <button v-if="!completed" class="button-danger" type="button" :disabled="!canSubmit" @click="confirmDelete">
          {{ submitting ? '正在删除…' : '确认启动删除' }}
        </button>
        <button class="button-secondary" type="button" @click="close">{{ completed ? '完成' : '取消' }}</button>
      </footer>
    </section>
  </div>
</template>