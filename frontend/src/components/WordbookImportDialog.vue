<script setup lang="ts">
import { computed, onMounted, onUnmounted, reactive, ref } from 'vue'
import { isApiError } from '../api/errors'
import {
  confirmWordbookImport,
  getWordbookJob,
  isPreviewExpired,
  previewWordbookImport,
  remapWordbookPreview,
  validateRequiredMapping,
  validateWordbookFile,
  WordbookTaskError,
  type WordbookField,
  type WordbookImportPreview,
  type WordbookJob,
  type WordbookVisibility,
} from '../api/wordbooks'
import { useDialogA11y } from '../composables/useDialogA11y'
import ErrorNotice from './ErrorNotice.vue'

const props = defineProps<{
  isAdmin: boolean
}>()

const emit = defineEmits<{
  close: []
  started: []
  completed: [wordbookId: string]
}>()

const fields: Array<{ key: WordbookField; label: string; required: boolean }> = [
  { key: 'headword', label: 'headword｜单词', required: true },
  { key: 'definition_en', label: 'definition_en｜英文释义', required: true },
  { key: 'definition_zh', label: 'definition_zh｜中文释义', required: true },
  { key: 'phonetic', label: 'phonetic｜音标', required: false },
  { key: 'part_of_speech', label: 'part_of_speech｜词性', required: false },
  { key: 'example', label: 'example｜英文例句', required: false },
  { key: 'example_translation', label: 'example_translation｜例句翻译', required: false },
]

const form = reactive({
  visibility: 'private' as WordbookVisibility,
  name: '',
  description: '',
})
const file = ref<File | null>(null)
const fileError = ref<string | null>(null)
const previewLoading = ref(false)
const previewError = ref<unknown>(null)
const preview = ref<WordbookImportPreview | null>(null)
const mapping = ref<Partial<Record<WordbookField, string | null>>>({})
const remapping = ref(false)
const confirming = ref(false)
const importError = ref<unknown>(null)
const job = ref<WordbookJob | null>(null)
const completed = ref(false)
const now = ref(Date.now())
const idempotencyKey = ref<string | null>(null)
const idempotencySignature = ref<string | null>(null)
const dialogRef = ref<HTMLElement | null>(null)
let active = true
let clock: number | null = null

const mappingError = computed(() => validateRequiredMapping(mapping.value))
const previewExpired = computed(() => preview.value ? isPreviewExpired(preview.value.expires_at, now.value) : false)
const previewHasErrors = computed(() => Boolean(preview.value && (preview.value.error_count > 0 || preview.value.errors.length > 0)))
const importTerminalFailure = computed(() => (
  job.value?.status === 'failed' || job.value?.status === 'cancelled'
))
const importTaskLabel = computed(() => {
  if (completed.value || job.value?.status === 'succeeded') {
    return '导入已完成'
  }
  if (remapping.value) {
    return '正在更新字段映射'
  }
  if (job.value?.status === 'queued') {
    return '导入任务排队中'
  }
  if (job.value?.status === 'running') {
    return '后台导入中'
  }
  if (job.value?.status === 'failed') {
    return '导入任务失败'
  }
  if (job.value?.status === 'cancelled') {
    return '导入任务已取消'
  }
  return confirming.value ? '正在确认导入' : '等待任务'
})
const ignoredColumns = computed(() => {
  if (!preview.value) {
    return []
  }
  const mapped = new Set(Object.values(mapping.value).filter((value): value is string => Boolean(value)))
  return preview.value.columns.filter((column) => !mapped.has(column))
})
const canPreview = computed(() => Boolean(file.value && form.name.trim()) && !fileError.value && !previewLoading.value)
const taskRunning = computed(() => Boolean(
  remapping.value
  || confirming.value
  || job.value?.status === 'queued'
  || job.value?.status === 'running',
))
const canConfirm = computed(() => Boolean(
  preview.value
  && !previewExpired.value
  && !previewHasErrors.value
  && !mappingError.value
  && !taskRunning.value
  && !importTerminalFailure.value
  && form.name.trim(),
))
const previewRestartSuggested = computed(() => {
  const candidate = importError.value ?? previewError.value
  if (!isApiError(candidate)) {
    return false
  }
  return candidate.status === 410 || [
    'IMPORT_PREVIEW_EXPIRED',
    'WORDBOOK_PREVIEW_EXPIRED',
    'IMPORT_PREVIEW_MISMATCH',
    'IMPORT_PREVIEW_USED',
    'WORDBOOK_PREVIEW_ALREADY_USED',
    'IMPORT_PREVIEW_NOT_FOUND',
  ].includes(candidate.code)
})

function formatDate(value: string): string {
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString('zh-CN')
}

function chooseFile(event: Event): void {
  const input = event.target as HTMLInputElement
  const selected = input.files?.[0] ?? null
  file.value = selected
  preview.value = null
  previewError.value = null
  importError.value = null
  job.value = null
  completed.value = false
  idempotencyKey.value = null
  idempotencySignature.value = null
  fileError.value = selected ? validateWordbookFile(selected) : null

  if (selected && !form.name.trim()) {
    form.name = selected.name.replace(/\.(csv|json|txt)$/i, '')
  }
}

function createKey(): string {
  return globalThis.crypto?.randomUUID?.() || `${Date.now()}-${Math.random()}`
}

function resetPreview(): void {
  preview.value = null
  previewError.value = null
  importError.value = null
  job.value = null
  completed.value = false
  mapping.value = {}
  idempotencyKey.value = null
  idempotencySignature.value = null
}

async function loadPreview(): Promise<void> {
  if (!file.value || !canPreview.value) {
    return
  }
  previewLoading.value = true
  previewError.value = null
  importError.value = null
  preview.value = null
  job.value = null
  completed.value = false
  idempotencyKey.value = null
  idempotencySignature.value = null

  try {
    const result = await previewWordbookImport(file.value, {
      visibility: form.visibility,
      name: form.name.trim(),
      description: form.description.trim(),
    })
    preview.value = result
    const serverMapping = Object.values(result.mapping).some(Boolean)
    mapping.value = { ...(serverMapping ? result.mapping : result.suggested_mapping) }
    now.value = Date.now()
  } catch (requestError) {
    previewError.value = requestError
  } finally {
    previewLoading.value = false
  }
}

function sleep(milliseconds: number): Promise<void> {
  return new Promise((resolve) => window.setTimeout(resolve, milliseconds))
}

function isPreviewInvalidError(error: unknown): boolean {
  return isApiError(error) && (
    error.status === 410
    || [
      'IMPORT_PREVIEW_EXPIRED',
      'WORDBOOK_PREVIEW_EXPIRED',
      'IMPORT_PREVIEW_MISMATCH',
      'IMPORT_PREVIEW_USED',
      'WORDBOOK_PREVIEW_ALREADY_USED',
      'IMPORT_PREVIEW_NOT_FOUND',
    ].includes(error.code)
  )
}

async function confirmImport(): Promise<void> {
  const currentPreview = preview.value
  if (!currentPreview || !canConfirm.value) {
    return
  }

  confirming.value = true
  importError.value = null
  completed.value = false
  job.value = null

  try {
    remapping.value = true
    const remapped = await remapWordbookPreview(currentPreview.preview_id, {
      preview_token: currentPreview.preview_token,
      mapping: mapping.value,
      ignored_columns: ignoredColumns.value,
    })
    remapping.value = false
    preview.value = remapped
    mapping.value = { ...mapping.value }
    now.value = Date.now()

    if (remapped.error_count > 0 || remapped.errors.length > 0) {
      throw new WordbookTaskError(
        'IMPORT_PREVIEW_HAS_ERRORS',
        '当前字段映射下仍有预览错误。请修正映射或文件后重新预览，错误未清零前不能确认导入。',
      )
    }

    const confirmationInput = {
      preview_id: remapped.preview_id,
      preview_token: remapped.preview_token || currentPreview.preview_token,
      preview_hash: remapped.preview_hash,
      visibility: form.visibility,
      name: form.name.trim(),
      description: form.description.trim() || null,
    }
    const signature = JSON.stringify(confirmationInput)
    if (idempotencySignature.value !== signature) {
      idempotencyKey.value = createKey()
      idempotencySignature.value = signature
    }
    const requestKey = idempotencyKey.value ?? createKey()
    idempotencyKey.value = requestKey

    const creation = await confirmWordbookImport(confirmationInput, requestKey)
    job.value = creation
    emit('started')

    for (let attempt = 0; attempt < 120 && active; attempt += 1) {
      const current = await getWordbookJob(creation.job_id)
      if (!active) {
        return
      }
      job.value = current

      if (current.status === 'succeeded') {
        completed.value = true
        idempotencyKey.value = null
        idempotencySignature.value = null
        emit('completed', current.wordbook_id ?? creation.wordbook_id ?? '')
        return
      }
      if (current.status === 'failed' || current.status === 'cancelled') {
        throw new WordbookTaskError(
          current.error_code || `IMPORT_${current.status.toUpperCase()}`,
          current.error_message || (current.status === 'cancelled' ? '导入任务已取消。' : '导入任务失败。'),
        )
      }
      if (attempt < 119) {
        await sleep(1000)
      }
    }

    throw new WordbookTaskError(
      'IMPORT_POLL_TIMEOUT',
      '在限定时间内没有确认导入完成。页面不会显示假成功，请稍后刷新词书列表查看真实任务状态。',
    )
  } catch (requestError) {
    importError.value = requestError
    if (isPreviewInvalidError(requestError)) {
      previewError.value = requestError
      preview.value = null
      job.value = null
    }
  } finally {
    remapping.value = false
    confirming.value = false
  }
}

function close(): void {
  active = false
  emit('close')
}

useDialogA11y(dialogRef, { onClose: close })

onMounted(() => {
  clock = window.setInterval(() => {
    now.value = Date.now()
  }, 1000)
})

onUnmounted(() => {
  active = false
  if (clock !== null) {
    window.clearInterval(clock)
  }
})
</script>

<template>
  <div class="dialog-backdrop" @click.self="close">
    <section
      ref="dialogRef"
      class="dialog-card wordbook-dialog wordbook-import-dialog"
      tabindex="-1"
      role="dialog"
      aria-modal="true"
      aria-labelledby="wordbook-import-title"
    >
      <header class="dialog-heading">
        <div>
          <p class="eyebrow">预览 · 映射 · 异步导入</p>
          <h2 id="wordbook-import-title">导入词书</h2>
        </div>
        <button class="icon-button" type="button" aria-label="关闭导入窗口" :disabled="taskRunning" @click="close">×</button>
      </header>

      <template v-if="!preview">
        <div class="alert alert-info">
          <strong>先检查文件和字段映射，确认后才会保存。</strong>
          <p>支持 CSV、JSON、TXT；至少需要识别单词、英文释义和中文释义。检查通过后才可确认导入。</p>
        </div>

        <form class="wordbook-form-grid" @submit.prevent="loadPreview">
          <label class="field">
            <span>可见范围</span>
            <select v-model="form.visibility" :disabled="previewLoading">
              <option v-if="props.isAdmin" value="organization">组织词书</option>
              <option value="private">我的私有词书</option>
            </select>
          </label>

          <label class="field">
            <span>词书名 <b aria-hidden="true">*</b></span>
            <input v-model="form.name" type="text" maxlength="200" autocomplete="off" :disabled="previewLoading" />
          </label>

          <label class="field wordbook-form-full">
            <span>描述</span>
            <textarea v-model="form.description" rows="3" maxlength="4000" :disabled="previewLoading"></textarea>
          </label>

          <label class="field wordbook-form-full">
            <span>词书文件</span>
            <input type="file" accept=".csv,.json,.txt,text/csv,application/json,text/plain" :disabled="previewLoading" @change="chooseFile" />
            <span class="field-hint">单文件不超过 10 MiB；导入结果会在确认前再次检查。</span>
          </label>
        </form>

        <p v-if="fileError" class="field-error" role="alert">{{ fileError }}</p>
        <ErrorNotice v-if="previewError" :error="previewError" :show-retry="false" />

        <footer class="dialog-actions button-row">
          <button type="button" :disabled="!canPreview" @click="loadPreview">
            {{ previewLoading ? '正在检查文件…' : '预览并检查映射' }}
          </button>
          <button class="button-secondary" type="button" :disabled="previewLoading" @click="close">取消</button>
        </footer>
      </template>

      <template v-else>
        <div class="wordbook-preview-meta">
          <span class="wordbook-pill" :class="`wordbook-pill--${preview.requested_visibility}`">
            {{ preview.requested_visibility === 'organization' ? '组织词书' : '我的私有词书' }}
          </span>
          <span><strong>{{ preview.filename }}</strong></span>
          <span>格式 <strong>{{ preview.detected_format.toUpperCase() }}</strong></span>
          <span>编码 <strong>{{ preview.encoding }}</strong></span>
          <span v-if="preview.delimiter">分隔符 <strong>{{ preview.delimiter }}</strong></span>
          <span>有效期至 <strong>{{ formatDate(preview.expires_at) }}</strong></span>
        </div>

        <div v-if="previewExpired" class="alert alert-warning" role="alert">
          <strong>预览令牌已过期</strong>
          <p>必须重新上传并预览，不能继续使用旧令牌确认导入。</p>
          <button class="button-secondary" type="button" @click="resetPreview">返回文件</button>
        </div>

        <div class="wordbook-preview-summary">
          <div><strong>{{ preview.total_rows }}</strong><span>总行数</span></div>
          <div><strong>{{ preview.valid_rows }}</strong><span>有效行</span></div>
          <div><strong>{{ preview.warning_count }}</strong><span>警告</span></div>
          <div :class="{ 'wordbook-summary-error': previewHasErrors }"><strong>{{ preview.error_count }}</strong><span>错误</span></div>
        </div>

        <section v-if="preview.errors.length" class="wordbook-subpanel" aria-labelledby="wordbook-errors-title">
          <div class="section-heading">
            <div>
              <h3 id="wordbook-errors-title">服务端预览错误</h3>
              <p class="field-hint">错误未清零前禁止确认导入。</p>
            </div>
            <span class="count-pill">{{ preview.error_count }} 条</span>
          </div>
          <ul class="wordbook-error-list">
            <li v-for="(item, index) in preview.errors" :key="`${item.line_number}-${item.code}-${index}`">
              <strong>{{ item.line_number ? `第 ${item.line_number} 行` : '文件级错误' }}</strong>
              <span v-if="item.code">· {{ item.code }}</span>
              <p>{{ item.message }}</p>
            </li>
          </ul>
        </section>

        <section v-if="preview.warnings.length" class="wordbook-subpanel" aria-labelledby="wordbook-warnings-title">
          <div class="section-heading">
            <div>
              <h3 id="wordbook-warnings-title">服务端预览警告</h3>
              <p class="field-hint">警告不会阻止导入，但请在确认前检查映射。</p>
            </div>
            <span class="count-pill">{{ preview.warning_count }} 条</span>
          </div>
          <ul class="wordbook-warning-list">
            <li v-for="(item, index) in preview.warnings" :key="`${item.line_number}-${item.code}-warning-${index}`">
              <strong>{{ item.line_number ? `第 ${item.line_number} 行` : '文件级警告' }}</strong>
              <span v-if="item.code">· {{ item.code }}</span>
              <p>{{ item.message }}</p>
            </li>
          </ul>
        </section>

        <section class="wordbook-subpanel" aria-labelledby="wordbook-mapping-title">
          <div class="section-heading">
            <div>
              <h3 id="wordbook-mapping-title">字段映射</h3>
              <p class="field-hint">确认前会先 PATCH remap，再使用响应中的新 preview_hash 创建导入任务。</p>
            </div>
          </div>
          <div class="wordbook-form-grid wordbook-mapping-grid">
            <label v-for="field in fields" :key="field.key" class="field">
              <span>{{ field.label }}<b v-if="field.required" aria-label="必填"> *</b></span>
              <select v-model="mapping[field.key]" :disabled="taskRunning">
                <option :value="null">忽略此字段</option>
                <option v-for="column in preview.columns" :key="column" :value="column">{{ column }}</option>
              </select>
            </label>
          </div>
          <p v-if="mappingError" class="field-error" role="alert">{{ mappingError }}</p>
          <p v-if="ignoredColumns.length" class="field-hint">忽略列：{{ ignoredColumns.join('、') }}</p>
        </section>

        <section v-if="preview.sample_rows.length" class="wordbook-subpanel" aria-labelledby="wordbook-sample-title">
          <div class="section-heading">
            <div>
              <h3 id="wordbook-sample-title">服务端结构化样例</h3>
              <p class="field-hint">样例行已经按映射归一化，不是原始列对象。</p>
            </div>
          </div>
          <div class="wordbook-sample-list">
            <article v-for="(row, index) in preview.sample_rows" :key="`${row.line_number}-${row.headword}-${index}`" class="wordbook-sample-row">
              <header>
                <strong>{{ row.headword }}</strong>
                <span v-if="row.phonetic">{{ row.phonetic }}</span>
                <span v-if="row.line_number">第 {{ row.line_number }} 行</span>
              </header>
              <p v-if="row.normalized_headword" class="field-hint">归一化：{{ row.normalized_headword }}</p>
              <div v-if="row.definitions.length" class="wordbook-sample-definitions">
                <div v-for="(definition, definitionIndex) in row.definitions" :key="`${row.headword}-sample-${definitionIndex}`">
                  <span v-if="definition.part_of_speech" class="part-of-speech">{{ definition.part_of_speech }}</span>
                  <p v-if="definition.definition_en"><b>EN</b> {{ definition.definition_en }}</p>
                  <p v-if="definition.definition_zh"><b>ZH</b> {{ definition.definition_zh }}</p>
                  <p v-if="definition.example_en" class="muted">例：{{ definition.example_en }}</p>
                  <p v-if="definition.example_translation" class="muted">{{ definition.example_translation }}</p>
                </div>
              </div>
              <p v-else class="muted">映射后暂无释义。</p>
            </article>
          </div>
        </section>

        <ErrorNotice v-if="importError" :error="importError" :show-retry="false" />

        <div v-if="taskRunning || job" class="wordbook-task-card" aria-live="polite">
          <div class="wordbook-task-heading">
            <strong>{{ importTaskLabel }}</strong>
            <span>{{ job ? `${job.progress}%` : '等待任务' }}</span>
          </div>
          <div class="progress-track" role="progressbar" :aria-valuenow="job?.progress ?? 0" aria-valuemin="0" aria-valuemax="100">
            <span :style="{ width: `${job?.progress ?? 0}%` }"></span>
          </div>
          <p v-if="job" class="field-hint">任务 ID：<code>{{ job.job_id }}</code> · 状态：{{ job.status }} · 清理：{{ job.cleanup_status }}</p>
          <p v-if="completed" class="alert alert-success" role="status">服务端任务已成功，词书列表将刷新。</p>
          <p v-else-if="importTerminalFailure" class="field-hint" role="status">服务端任务未成功；预览已失效，请返回文件重新预览。</p>
        </div>

        <footer class="dialog-actions button-row">
          <button type="button" :disabled="!canConfirm || completed || importTerminalFailure" @click="confirmImport">
            {{ importTerminalFailure ? '请返回文件重新预览' : confirming ? (remapping ? '正在 remap…' : '正在确认并轮询…') : '确认导入' }}
          </button>
          <button class="button-secondary" type="button" :disabled="taskRunning || completed" @click="resetPreview">返回文件</button>
          <button class="button-secondary" type="button" :disabled="taskRunning" @click="close">{{ completed ? '完成' : '取消' }}</button>
        </footer>

        <p v-if="previewRestartSuggested" class="field-hint">预览凭证已失效或不匹配，请返回文件重新上传预览。</p>
      </template>
    </section>
  </div>
</template>
