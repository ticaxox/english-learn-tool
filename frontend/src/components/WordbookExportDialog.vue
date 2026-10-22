<script setup lang="ts">
import { computed, onUnmounted, reactive, ref } from 'vue'
import {
  createWordbookExport,
  getExportJob,
  normalizeDownloadUrl,
  WordbookTaskError,
  type ExportFormat,
  type ExportJob,
  type Wordbook,
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
  pdf_rows_per_page: 20,
  pdf_words_per_line: 5,
})
const submitting = ref(false)
const error = ref<unknown>(null)
const job = ref<ExportJob | null>(null)
const completed = ref(false)
const requestKey = ref<string | null>(null)
const requestSignature = ref<string | null>(null)
let active = true
const dialogRef = ref<HTMLElement | null>(null)

const downloadUrl = computed(() => normalizeDownloadUrl(job.value?.download_url ?? null))
const statusLabel = computed(() => {
  if (!job.value) {
    return '尚未创建任务'
  }
  return {
    queued: '等待处理',
    running: '正在生成',
    succeeded: '导出完成',
    failed: '导出失败',
    expired: '下载已过期',
  }[job.value.status]
})
const validationError = computed(() => {
  if (form.format !== 'pdf') {
    return null
  }
  if (!Number.isInteger(form.pdf_rows_per_page) || form.pdf_rows_per_page < 1 || form.pdf_rows_per_page > 200) {
    return '每页行数必须是 1 到 200 之间的整数。'
  }
  if (!Number.isInteger(form.pdf_words_per_line) || form.pdf_words_per_line < 1 || form.pdf_words_per_line > 50) {
    return '每行单词数必须是 1 到 50 之间的整数。'
  }
  return null
})

function sleep(milliseconds: number): Promise<void> {
  return new Promise((resolve) => window.setTimeout(resolve, milliseconds))
}

function createKey(): string {
  return globalThis.crypto?.randomUUID?.() || `${Date.now()}-${Math.random()}`
}

async function submit(): Promise<void> {
  if (submitting.value || validationError.value) {
    return
  }
  submitting.value = true
  error.value = null
  job.value = null
  completed.value = false
  const signature = JSON.stringify({
    format: form.format,
    page_rows: form.format === 'pdf' ? form.pdf_rows_per_page : null,
    columns: form.format === 'pdf' ? form.pdf_words_per_line : null,
  })
  if (requestSignature.value !== signature) {
    requestKey.value = createKey()
    requestSignature.value = signature
  }
  const requestIdempotencyKey = requestKey.value ?? createKey()
  requestKey.value = requestIdempotencyKey

  try {
    const creation = await createWordbookExport(
      props.wordbook.id,
      {
        format: form.format,
        ...(form.format === 'pdf'
          ? {
              pdf_rows_per_page: form.pdf_rows_per_page,
              pdf_words_per_line: form.pdf_words_per_line,
            }
          : {}),
      },
      requestIdempotencyKey,
    )
    emit('started')

    for (let attempt = 0; attempt < 120 && active; attempt += 1) {
      const current = await getExportJob(creation.job_id)
      if (!active) {
        return
      }
      job.value = current
      if (current.status === 'succeeded') {
        if (!normalizeDownloadUrl(current.download_url)) {
          throw new WordbookTaskError(
            'EXPORT_DOWNLOAD_MISSING',
            '导出任务已成功，但没有返回安全的短期下载地址。请检查 OpenAPI。',
          )
        }
        completed.value = true
        requestKey.value = null
        requestSignature.value = null
        return
      }
      if (current.status === 'failed' || current.status === 'expired') {
        throw new WordbookTaskError(
          current.error_code || `EXPORT_${current.status.toUpperCase()}`,
          current.error_message || (current.status === 'expired' ? '下载链接已过期。' : '导出任务失败。'),
        )
      }
      if (attempt < 119) {
        await sleep(1000)
      }
    }

    throw new WordbookTaskError(
      'EXPORT_POLL_TIMEOUT',
      '在限定时间内没有收到导出完成状态。页面不会把超时当作成功，请稍后查询真实任务状态。',
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
      aria-labelledby="wordbook-export-title"
    >
      <header class="dialog-heading">
        <div>
          <p class="eyebrow">异步导出</p>
          <h2 id="wordbook-export-title">导出「{{ props.wordbook.name }}」</h2>
        </div>
        <button class="icon-button" type="button" aria-label="关闭导出窗口" :disabled="submitting" @click="close">×</button>
      </header>

      <p class="lead">CSV 和 TXT 适合继续处理或备份；PDF 由服务端生成，并支持分页与每行词数设置。</p>

      <fieldset class="wordbook-choice-group" :disabled="submitting">
        <legend>导出格式</legend>
        <label v-for="item in [
          { value: 'csv', label: 'CSV', hint: '通用表格格式' },
          { value: 'txt', label: 'TXT', hint: '纯文本词书' },
          { value: 'pdf', label: 'PDF', hint: '适合打印或阅读' },
        ]" :key="item.value" class="wordbook-choice">
          <input v-model="form.format" type="radio" :value="item.value" />
          <span><strong>{{ item.label }}</strong><small>{{ item.hint }}</small></span>
        </label>
      </fieldset>

      <div v-if="form.format === 'pdf'" class="wordbook-form-grid">
        <label class="field">
          <span>每页行数</span>
          <input v-model.number="form.pdf_rows_per_page" type="number" min="1" max="200" inputmode="numeric" />
        </label>
        <label class="field">
          <span>每行单词数</span>
          <input v-model.number="form.pdf_words_per_line" type="number" min="1" max="50" inputmode="numeric" />
        </label>
      </div>

      <p v-if="validationError" class="field-error" role="alert">{{ validationError }}</p>
      <ErrorNotice v-if="error" :error="error" :show-retry="false" />

      <div v-if="job" class="wordbook-task-card" aria-live="polite">
        <div class="wordbook-task-heading">
          <strong>{{ statusLabel }}</strong>
          <span>{{ job.progress }}%</span>
        </div>
        <div class="progress-track" role="progressbar" :aria-valuenow="job.progress" aria-valuemin="0" aria-valuemax="100">
          <span :style="{ width: `${job.progress}%` }"></span>
        </div>
        <p class="field-hint">任务 ID：<code>{{ job.job_id }}</code></p>
      </div>

      <div v-if="completed" class="alert alert-success">
        <strong>导出已完成</strong>
        <p>下载地址由服务端签发，可能短期失效。</p>
        <a v-if="downloadUrl" class="button" :href="downloadUrl" target="_blank" rel="noopener noreferrer">
          下载导出文件
        </a>
        <p v-if="job?.expires_at" class="field-hint">有效期至 {{ new Date(job.expires_at).toLocaleString('zh-CN') }}</p>
      </div>

      <footer class="dialog-actions button-row">
        <button type="button" :disabled="submitting || Boolean(validationError)" @click="submit">
          {{ submitting ? '正在处理…' : job || error ? '重新创建导出任务' : '开始导出' }}
        </button>
        <button class="button-secondary" type="button" :disabled="submitting" @click="close">关闭</button>
      </footer>
    </section>
  </div>
</template>