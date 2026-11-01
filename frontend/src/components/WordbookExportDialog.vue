<script setup lang="ts">
import { computed, onUnmounted, reactive, ref } from 'vue'
import {
  createWordbookExport,
  downloadWordbookExport,
  getExportJob,
  WordbookTaskError,
  type ExportFormat,
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
  started: []
}>()

const form = reactive({
  format: 'csv' as ExportFormat,
  page_rows: 20,
  columns: 4,
})
const submitting = ref(false)
const downloading = ref(false)
const error = ref<unknown>(null)
const downloadError = ref<unknown>(null)
const job = ref<WordbookJob | null>(null)
const completed = ref(false)
const requestKey = ref<string | null>(null)
const requestSignature = ref<string | null>(null)
const dialogRef = ref<HTMLElement | null>(null)
let active = true

const validationError = computed(() => {
  if (form.format !== 'pdf') {
    return null
  }
  if (!Number.isInteger(form.page_rows) || form.page_rows < 1 || form.page_rows > 100) {
    return '每页行数必须是 1 到 100 之间的整数。'
  }
  if (!Number.isInteger(form.columns) || form.columns < 1 || form.columns > 4) {
    return '每行列数必须是 1 到 4 之间的整数。'
  }
  return null
})
const canSubmit = computed(() => !submitting.value && !validationError.value)
const statusLabel = computed(() => {
  if (!job.value) {
    return '尚未创建任务'
  }
  return {
    queued: '等待处理',
    running: '正在生成',
    succeeded: '导出完成',
    failed: '导出失败',
    cancelled: '导出已取消',
  }[job.value.status]
})
const downloadExpired = computed(() => {
  const value = job.value?.download_expires_at
  if (!value) {
    return false
  }
  const expiry = Date.parse(value)
  return Number.isNaN(expiry) || expiry <= Date.now()
})

function formatDate(value: string | null): string {
  if (!value) {
    return '暂无记录'
  }
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString('zh-CN', { year: 'numeric', month: 'long', day: 'numeric', hour: '2-digit', minute: '2-digit' })
}

function sleep(milliseconds: number): Promise<void> {
  return new Promise((resolve) => window.setTimeout(resolve, milliseconds))
}

function createKey(): string {
  return globalThis.crypto?.randomUUID?.() || `${Date.now()}-${Math.random()}`
}

function exportOptions(): { format: ExportFormat; page_rows?: number; columns?: number } {
  if (form.format !== 'pdf') {
    return { format: form.format }
  }
  return {
    format: form.format,
    page_rows: form.page_rows,
    columns: form.columns,
  }
}

async function submit(): Promise<void> {
  if (!canSubmit.value) {
    return
  }
  submitting.value = true
  error.value = null
  downloadError.value = null
  job.value = null
  completed.value = false

  const options = exportOptions()
  const signature = JSON.stringify(options)
  if (requestSignature.value !== signature) {
    requestKey.value = createKey()
    requestSignature.value = signature
  }
  const requestIdempotencyKey = requestKey.value ?? createKey()
  requestKey.value = requestIdempotencyKey

  try {
    const creation = await createWordbookExport(props.wordbook.id, options, requestIdempotencyKey)
    job.value = creation
    emit('started')

    for (let attempt = 0; attempt < 120 && active; attempt += 1) {
      const current = await getExportJob(creation.job_id)
      if (!active) {
        return
      }
      job.value = current

      if (current.status === 'succeeded') {
        completed.value = true
        requestKey.value = null
        requestSignature.value = null
        return
      }
      if (current.status === 'failed' || current.status === 'cancelled') {
        // The backend resolves a reused key to the same terminal job, so a retry needs a new key.
        requestKey.value = null
        requestSignature.value = null
        throw new WordbookTaskError(
          current.error_code || `EXPORT_${current.status.toUpperCase()}`,
          current.error_message || (current.status === 'cancelled' ? '导出任务已取消。' : '导出任务失败。'),
        )
      }
      if (attempt < 119) {
        await sleep(1000)
      }
    }

    throw new WordbookTaskError(
      'EXPORT_POLL_TIMEOUT',
      '在限定时间内没有收到导出完成状态。页面不会把超时当作成功，请稍后重新创建任务。',
    )
  } catch (requestError) {
    error.value = requestError
  } finally {
    submitting.value = false
  }
}

function safeDownloadName(): string {
  const stem = props.wordbook.name
    .trim()
    .replace(/[<>:"/\\|?*\u0000-\u001f]/g, '-')
    .replace(/\s+/g, ' ')
    .slice(0, 80) || 'wordbook'
  return `${stem}.${form.format}`
}

async function download(): Promise<void> {
  const current = job.value
  if (!current || current.status !== 'succeeded' || downloading.value || downloadExpired.value) {
    return
  }
  downloading.value = true
  downloadError.value = null

  try {
    const blob = await downloadWordbookExport(current.job_id)
    if (blob.size === 0) {
      throw new WordbookTaskError('EXPORT_DOWNLOAD_EMPTY', '导出文件为空，请重新导出。')
    }
    const objectUrl = window.URL.createObjectURL(blob)
    const anchor = document.createElement('a')
    anchor.href = objectUrl
    anchor.download = safeDownloadName()
    anchor.rel = 'noopener'
    document.body.append(anchor)
    anchor.click()
    anchor.remove()
    window.setTimeout(() => window.URL.revokeObjectURL(objectUrl), 0)
  } catch (requestError) {
    downloadError.value = requestError
  } finally {
    downloading.value = false
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
      aria-labelledby="wordbook-export-title"
    >
      <header class="dialog-heading">
        <div>
          <p class="eyebrow">异步导出 · 授权下载</p>
          <h2 id="wordbook-export-title">导出「{{ props.wordbook.name }}」</h2>
        </div>
        <button class="icon-button" type="button" aria-label="关闭导出窗口" :disabled="submitting" @click="close">×</button>
      </header>

      <div class="alert alert-info">
        <strong>导出会在后台生成，完成后即可下载。</strong>
        <p>下载链接只对当前账号有效；过期后重新导出即可。</p>
      </div>

      <fieldset class="wordbook-choice-group" :disabled="submitting">
        <legend>导出格式</legend>
        <label class="wordbook-choice">
          <input v-model="form.format" type="radio" value="csv" />
          <span><strong>CSV</strong><small>适合表格处理</small></span>
        </label>
        <label class="wordbook-choice">
          <input v-model="form.format" type="radio" value="txt" />
          <span><strong>TXT</strong><small>纯文本词书</small></span>
        </label>
        <label class="wordbook-choice">
          <input v-model="form.format" type="radio" value="pdf" />
          <span><strong>PDF</strong><small>可打印版本</small></span>
        </label>
      </fieldset>

      <div v-if="form.format === 'pdf'" class="wordbook-form-grid">
        <label class="field">
          <span>每页行数</span>
          <input v-model.number="form.page_rows" type="number" min="1" max="100" step="1" :disabled="submitting" />
        </label>
        <label class="field">
          <span>每行列数</span>
          <input v-model.number="form.columns" type="number" min="1" max="4" step="1" :disabled="submitting" />
        </label>
      </div>

      <p v-if="validationError" class="field-error" role="alert">{{ validationError }}</p>
      <ErrorNotice v-if="error" :error="error" :show-retry="false" />
      <ErrorNotice v-if="downloadError" :error="downloadError" :show-retry="false" />

      <div v-if="submitting || job" class="wordbook-task-card" aria-live="polite">
        <div class="wordbook-task-heading">
          <strong>{{ completed ? '导出已完成' : statusLabel }}</strong>
          <span>{{ job ? `${job.progress}%` : '等待任务' }}</span>
        </div>
        <div class="progress-track" role="progressbar" :aria-valuenow="job?.progress ?? 0" aria-valuemin="0" aria-valuemax="100">
          <span :style="{ width: `${job?.progress ?? 0}%` }"></span>
        </div>
        <p v-if="job" class="field-hint">导出文件已生成，可以下载。</p>
        <p v-if="job?.download_expires_at" class="field-hint">下载有效期至：{{ formatDate(job.download_expires_at) }}</p>

        <div v-if="completed" class="wordbook-download-actions">
          <button type="button" :disabled="downloading || downloadExpired" @click="download">
            {{ downloading ? '正在安全下载…' : downloadExpired ? '下载已过期' : `下载 ${form.format.toUpperCase()}` }}
          </button>
          <span class="field-hint">下载链接仅对当前账号有效。</span>
        </div>
      </div>

      <footer class="dialog-actions button-row">
        <button v-if="!completed" type="button" :disabled="!canSubmit" @click="submit">
          {{ submitting ? '导出任务处理中…' : job ? '重新创建导出任务' : '开始导出' }}
        </button>
        <button class="button-secondary" type="button" :disabled="submitting || downloading" @click="close">
          {{ completed ? '完成' : '取消' }}
        </button>
      </footer>
    </section>
  </div>
</template>
