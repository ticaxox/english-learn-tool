<script setup lang="ts">
import { computed, onUnmounted, ref } from 'vue'
import {
  deleteWordbook,
  getWordbookJob,
  WordbookTaskError,
  type Wordbook,
  type WordbookJob,
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
const error = ref<unknown>(null)
const job = ref<WordbookJob | null>(null)
const completed = ref(false)
const requestKey = ref<string | null>(null)
const requestSignature = ref<string | null>(null)
const dialogRef = ref<HTMLElement | null>(null)
let active = true

const exactNameRequired = computed(() => props.wordbook.visibility === 'organization')
const confirmationMatches = computed(() => confirmation.value.trim() === props.wordbook.name.trim())
const canSubmit = computed(() => Boolean(
  !submitting.value
  && !completed.value
  && job.value?.status !== 'queued'
  && job.value?.status !== 'running'
  && (exactNameRequired.value ? confirmationMatches.value : privateConfirmed.value),
))
const statusLabel = computed(() => {
  if (!job.value) {
    return '尚未创建任务'
  }
  return {
    queued: '删除任务排队中',
    running: '正在清理',
    succeeded: '清理成功',
    failed: '清理失败',
    cancelled: '清理已取消',
  }[job.value.status]
})

function sleep(milliseconds: number): Promise<void> {
  return new Promise((resolve) => window.setTimeout(resolve, milliseconds))
}

function createKey(): string {
  return globalThis.crypto?.randomUUID?.() || `${Date.now()}-${Math.random()}`
}

async function confirmDelete(): Promise<void> {
  if (!canSubmit.value) {
    return
  }
  submitting.value = true
  error.value = null
  completed.value = false
  job.value = null

  const signature = JSON.stringify({
    wordbook_id: props.wordbook.id,
    confirm_name: exactNameRequired.value ? props.wordbook.name : null,
  })
  if (requestSignature.value !== signature) {
    requestKey.value = createKey()
    requestSignature.value = signature
  }
  const requestIdempotencyKey = requestKey.value ?? createKey()
  requestKey.value = requestIdempotencyKey

  try {
    const creation = await deleteWordbook(
      props.wordbook,
      exactNameRequired.value ? confirmation.value : '',
      requestIdempotencyKey,
    )
    job.value = creation
    emit('started', props.wordbook.id)

    for (let attempt = 0; attempt < 120 && active; attempt += 1) {
      const current = await getWordbookJob(creation.job_id)
      if (!active) {
        return
      }
      job.value = current

      if (current.status === 'succeeded') {
        completed.value = true
        requestKey.value = null
        requestSignature.value = null
        emit('completed', props.wordbook.id)
        return
      }
      if (current.status === 'failed' || current.status === 'cancelled') {
        // The backend resolves a reused key to the same terminal job, so a retry needs a new key.
        requestKey.value = null
        requestSignature.value = null
        throw new WordbookTaskError(
          current.error_code || `DELETE_${current.status.toUpperCase()}`,
          current.error_message || (current.status === 'cancelled' ? '删除任务已取消。' : '删除清理任务失败。'),
        )
      }
      if (attempt < 119) {
        await sleep(1000)
      }
    }

    throw new WordbookTaskError(
      'DELETE_POLL_TIMEOUT',
      '在限定时间内没有确认清理完成。页面不会把超时当作删除成功，请关闭后刷新查看真实任务状态。',
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
          <p class="eyebrow">危险操作 · 后台清理</p>
          <h2 id="wordbook-delete-title">删除「{{ props.wordbook.name }}」</h2>
        </div>
        <button class="icon-button" type="button" aria-label="关闭删除窗口" :disabled="submitting" @click="close">×</button>
      </header>

      <div class="alert alert-warning">
        <strong>删除会在后台执行，完成后列表会自动更新。</strong>
        <ul>
          <li>共享词书需要再次输入完整名称；私人词书勾选确认即可。</li>
          <li v-if="props.wordbook.is_active">这是当前主词书，删除后需要重新选择或导入一本。</li>
          <li>当前词条数：{{ props.wordbook.entry_count.toLocaleString('zh-CN') }}。</li>
        </ul>
      </div>

      <label v-if="exactNameRequired" class="field">
        <span>输入完整词书名以确认</span>
        <input v-model="confirmation" autocomplete="off" :placeholder="props.wordbook.name" :disabled="submitting || completed" />
        <span class="field-hint">必须与词书名称完全一致。</span>
      </label>

      <label v-else class="wordbook-check">
        <input v-model="privateConfirmed" type="checkbox" :disabled="submitting || completed" />
        <span>我确认删除这本词书。</span>
      </label>

      <ErrorNotice v-if="error" :error="error" :show-retry="false" />

      <div v-if="submitting || job" class="wordbook-task-card" role="status" aria-live="polite">
        <div class="wordbook-task-heading">
          <strong>{{ completed ? '清理已完成' : statusLabel }}</strong>
          <span>{{ job ? `${job.progress}%` : '等待任务' }}</span>
        </div>
        <div class="progress-track" role="progressbar" :aria-valuenow="job?.progress ?? 0" aria-valuemin="0" aria-valuemax="100">
          <span :style="{ width: `${job?.progress ?? 0}%` }"></span>
        </div>
        <p v-if="job" class="field-hint">已处理 {{ job.progress }}%</p>
        <p v-if="completed" class="alert alert-success">删除完成，列表已更新。</p>
        <p v-else class="field-hint">关闭窗口不会取消删除；重新打开词书页即可看到最新状态。</p>
      </div>

      <footer class="dialog-actions button-row">
        <button v-if="!completed" class="button-danger" type="button" :disabled="!canSubmit" @click="confirmDelete">
          {{ submitting ? '正在删除并轮询…' : '确认启动删除' }}
        </button>
        <button class="button-secondary" type="button" :disabled="submitting" @click="close">{{ completed ? '完成' : '取消' }}</button>
      </footer>
    </section>
  </div>
</template>
