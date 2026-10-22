<script setup lang="ts">
import { computed, onMounted, onUnmounted, reactive, ref } from 'vue'
import { isApiError } from '../api/errors'
import {
  confirmWordbookImport,
  getWordbookDetail,
  isPreviewExpired,
  previewWordbookImport,
  validateRequiredMapping,
  validateWordbookFile,
  WordbookTaskError,
  type DuplicateStrategy,
  type WordbookField,
  type WordbookImportPreview,
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
  { key: 'definition', label: 'definition｜释义', required: true },
  { key: 'phonetic', label: 'phonetic｜音标', required: false },
  { key: 'part_of_speech', label: 'part_of_speech｜词性', required: false },
  { key: 'example', label: 'example｜例句', required: false },
  { key: 'example_translation', label: 'example_translation｜例句翻译', required: false },
]

const form = reactive({
  visibility: 'private' as WordbookVisibility,
  name: '',
  description: '',
  duplicate_strategy: 'merge' as DuplicateStrategy,
})
const file = ref<File | null>(null)
const fileError = ref<string | null>(null)
const previewLoading = ref(false)
const previewError = ref<unknown>(null)
const preview = ref<WordbookImportPreview | null>(null)
const mapping = ref<Partial<Record<WordbookField, string | null>>>({})
const confirming = ref(false)
const importError = ref<unknown>(null)
const importProgress = ref<number | null>(null)
const importWordbookId = ref<string | null>(null)
const completed = ref(false)
const now = ref(Date.now())
const idempotencyKey = ref<string | null>(null)
const idempotencySignature = ref<string | null>(null)
let active = true
let clock: number | null = null
const dialogRef = ref<HTMLElement | null>(null)

const mappingError = computed(() => validateRequiredMapping(mapping.value))
const previewExpired = computed(() => preview.value ? isPreviewExpired(preview.value.expires_at, now.value) : false)
const ignoredColumns = computed(() => {
  if (!preview.value) {
    return []
  }
  const mapped = new Set(Object.values(mapping.value).filter((value): value is string => Boolean(value)))
  return preview.value.columns.filter((column) => !mapped.has(column))
})
const canPreview = computed(() => Boolean(file.value && form.name.trim()) && !fileError.value)
const canConfirm = computed(() => Boolean(
  preview.value
  && !previewExpired.value
  && !mappingError.value
  && !confirming.value
  && form.name.trim(),
))
const previewRestartSuggested = computed(() => {
  if (!isApiError(previewError.value)) {
    return false
  }
  return previewError.value.status === 410 || [
    'IMPORT_PREVIEW_EXPIRED',
    'WORDBOOK_PREVIEW_EXPIRED',
    'IMPORT_PREVIEW_MISMATCH',
    'IMPORT_PREVIEW_USED',
    'IMPORT_PREVIEW_NOT_FOUND',
  ].includes(previewError.value.code)
})

function chooseFile(event: Event): void {
  const input = event.target as HTMLInputElement
  const selected = input.files?.[0] ?? null
  file.value = selected
  preview.value = null
  previewError.value = null
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

async function loadPreview(): Promise<void> {
  if (!file.value || !canPreview.value) {
    return
  }
  previewLoading.value = true
  previewError.value = null
  importError.value = null
  preview.value = null
  idempotencyKey.value = null
  idempotencySignature.value = null

  try {
    const result = await previewWordbookImport(file.value, {
      visibility: form.visibility,
      name: form.name.trim(),
      description: form.description.trim(),
    })
    preview.value = result
    mapping.value = { ...result.suggested_mapping }
    now.value = Date.now()
  } catch (requestError) {
    previewError.value = requestError
  } finally {
    previewLoading.value = false
  }
}

function resetPreview(): void {
  preview.value = null
  previewError.value = null
  importError.value = null
  mapping.value = {}
  idempotencyKey.value = null
  idempotencySignature.value = null
}

function sleep(milliseconds: number): Promise<void> {
  return new Promise((resolve) => window.setTimeout(resolve, milliseconds))
}

async function confirmImport(): Promise<void> {
  if (!preview.value || !canConfirm.value) {
    return
  }
  confirming.value = true
  importError.value = null
  importProgress.value = null

  const request = {
    preview_token: preview.value.preview_token,
    visibility: form.visibility,
    name: form.name.trim(),
    description: form.description.trim(),
    mapping: mapping.value,
    ignored_columns: ignoredColumns.value,
    duplicate_strategy: form.duplicate_strategy,
  }
  const signature = JSON.stringify(request)
  if (idempotencySignature.value !== signature) {
    idempotencyKey.value = createKey()
    idempotencySignature.value = signature
  }
  const requestIdempotencyKey = idempotencyKey.value ?? createKey()
  idempotencyKey.value = requestIdempotencyKey

  try {
    const confirmation = await confirmWordbookImport(request, requestIdempotencyKey)
    importWordbookId.value = confirmation.wordbook_id
    emit('started')

    for (let attempt = 0; attempt < 120 && active; attempt += 1) {
      try {
        const detail = await getWordbookDetail(confirmation.wordbook_id, null, 1)
        if (!active) {
          return
        }
        importProgress.value = detail.wordbook.import_progress
        if (detail.wordbook.status === 'ready') {
          completed.value = true
          idempotencyKey.value = null
          idempotencySignature.value = null
          emit('completed', detail.wordbook.id)
          return
        }
        if (detail.wordbook.status === 'failed') {
          throw new WordbookTaskError(
            'WORD_BOOK_IMPORT_FAILED',
            detail.wordbook.import_error || '导入任务失败，请查看服务端任务状态后重新预览。',
          )
        }
        if (detail.wordbook.status === 'deleting') {
          throw new WordbookTaskError('WORD_BOOK_IMPORT_DELETED', '导入过程中词书进入了删除状态。')
        }
      } catch (requestError) {
        if (!(isApiError(requestError) && requestError.status === 404 && attempt < 3)) {
          throw requestError
        }
      }
      if (attempt < 119) {
        await sleep(1000)
      }
    }

    throw new WordbookTaskError(
      'WORD_BOOK_IMPORT_POLL_TIMEOUT',
      '在限定时间内没有确认导入完成。页面不会显示假成功，请刷新列表查看服务端状态。',
    )
  } catch (requestError) {
    importError.value = requestError
    if (
      isApiError(requestError)
      && (
        requestError.status === 410
        || ['IMPORT_PREVIEW_EXPIRED', 'WORDBOOK_PREVIEW_EXPIRED', 'IMPORT_PREVIEW_MISMATCH', 'IMPORT_PREVIEW_USED', 'IMPORT_PREVIEW_NOT_FOUND'].includes(requestError.code)
      )
    ) {
      previewError.value = requestError
      preview.value = null
    }
  } finally {
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
  }, 30000)
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
          <p class="eyebrow">内存中的预览令牌 · 24 小时有效</p>
          <h2 id="wordbook-import-title">导入词书</h2>
        </div>
        <button class="icon-button" type="button" aria-label="关闭导入窗口" :disabled="confirming" @click="close">×</button>
      </header>

      <div v-if="completed" class="alert alert-success" role="status">
        <strong>导入已完成</strong>
        <p>词书已由真实后台任务完成，并已刷新到列表。现在可以查看词条或激活它。</p>
        <p v-if="importWordbookId" class="field-hint">词书 ID：<code>{{ importWordbookId }}</code></p>
        <button type="button" @click="close">完成</button>
      </div>

      <template v-else-if="!preview">
        <p class="lead">先上传文件并由服务端解析。页面只保留本次预览令牌于内存中，不会写入 localStorage 或伪造预览结果。</p>

        <div class="wordbook-form-grid">
          <label class="field wordbook-form-full">
            <span>词书文件</span>
            <input type="file" accept=".csv,.json,.txt" :disabled="previewLoading" @change="chooseFile" />
            <span class="field-hint">支持 CSV、JSON、TXT；前端提示上限 10 MiB，最终限制以服务端 413 校验为准。</span>
          </label>

          <label class="field">
            <span>词书名称</span>
            <input v-model="form.name" type="text" maxlength="120" :disabled="previewLoading" />
          </label>

          <label class="field">
            <span>可见范围</span>
            <select v-model="form.visibility" :disabled="previewLoading || !props.isAdmin">
              <option v-if="props.isAdmin" value="organization">组织词书</option>
              <option value="private">我的私有词书</option>
            </select>
            <span class="field-hint">{{ props.isAdmin ? '管理员可创建组织或私有词书。' : '成员只能创建自己的私有词书，最终仍由服务端校验。' }}</span>
          </label>

          <label class="field wordbook-form-full">
            <span>描述（可选）</span>
            <textarea v-model="form.description" rows="3" maxlength="500" :disabled="previewLoading"></textarea>
          </label>
        </div>

        <p v-if="fileError" class="field-error" role="alert">{{ fileError }}</p>
        <ErrorNotice v-if="previewError" :error="previewError" :show-retry="false" />
        <p v-if="previewRestartSuggested" class="inline-note">预览已过期、已使用或与当前映射不一致。请选择文件并重新预览，不能复用旧令牌确认。</p>

        <footer class="dialog-actions button-row">
          <button type="button" :disabled="!canPreview || previewLoading" @click="loadPreview">
            {{ previewLoading ? '正在由服务端解析…' : '预览并检查映射' }}
          </button>
          <button class="button-secondary" type="button" :disabled="previewLoading" @click="close">取消</button>
        </footer>
      </template>

      <template v-else>
        <div class="wordbook-preview-summary" aria-live="polite">
          <div><strong>{{ preview.total_rows }}</strong><span>总行数</span></div>
          <div><strong>{{ preview.importable_rows }}</strong><span>可导入</span></div>
          <div><strong>{{ preview.warning_count }}</strong><span>警告</span></div>
          <div><strong>{{ preview.error_count }}</strong><span>错误</span></div>
        </div>

        <div class="wordbook-preview-meta">
          <span>格式 <strong>{{ preview.detected_format }}</strong></span>
          <span>编码 <strong>{{ preview.encoding || '自动检测' }}</strong></span>
          <span>分隔符 <strong>{{ preview.delimiter || '不适用' }}</strong></span>
          <span>预览有效期至 <strong>{{ new Date(preview.expires_at).toLocaleString('zh-CN') }}</strong></span>
        </div>

        <div v-if="previewExpired" class="alert alert-warning" role="alert">
          <strong>预览令牌已过期</strong>
          <p>必须重新上传并预览，不能继续使用旧令牌确认导入。</p>
          <button class="button-secondary" type="button" @click="resetPreview">重新预览</button>
        </div>

        <section class="wordbook-subpanel" aria-labelledby="wordbook-mapping-title">
          <div class="section-heading">
            <div>
              <h3 id="wordbook-mapping-title">字段映射</h3>
              <p class="field-hint">headword 与 definition 必填；同一源列不能映射到多个字段。</p>
            </div>
          </div>
          <div class="wordbook-form-grid wordbook-mapping-grid">
            <label v-for="field in fields" :key="field.key" class="field">
              <span>{{ field.label }}<b v-if="field.required" aria-label="必填"> *</b></span>
              <select v-model="mapping[field.key]" :disabled="confirming">
                <option :value="null">忽略此字段</option>
                <option v-for="column in preview.columns" :key="column" :value="column">{{ column }}</option>
              </select>
            </label>
          </div>
          <p v-if="mappingError" class="field-error" role="alert">{{ mappingError }}</p>
          <p v-if="ignoredColumns.length" class="field-hint">将被忽略的列：{{ ignoredColumns.join('、') }}</p>
          <label class="field">
            <span>重复行处理</span>
            <select v-model="form.duplicate_strategy" :disabled="confirming">
              <option value="merge">合并到同一词条（推荐）</option>
              <option value="reject">遇到重复时阻止导入</option>
            </select>
          </label>
        </section>

        <section v-if="preview.sample_rows.length" class="wordbook-subpanel" aria-labelledby="wordbook-sample-title">
          <h3 id="wordbook-sample-title">服务端样例</h3>
          <div class="table-wrap">
            <table class="data-table wordbook-sample-table">
              <thead>
                <tr><th v-for="column in preview.columns" :key="column">{{ column }}</th></tr>
              </thead>
              <tbody>
                <tr v-for="(row, index) in preview.sample_rows" :key="index">
                  <td v-for="column in preview.columns" :key="column">{{ row[column] || '—' }}</td>
                </tr>
              </tbody>
            </table>
          </div>
        </section>

        <section v-if="preview.errors.length" class="wordbook-subpanel" aria-labelledby="wordbook-errors-title">
          <div class="section-heading">
            <div>
              <h3 id="wordbook-errors-title">前 100 条预览错误</h3>
              <p class="field-hint">错误定位到服务端返回的行列；不会用通用失败覆盖。</p>
            </div>
            <span class="count-pill">{{ preview.error_count }} 条</span>
          </div>
          <ul class="wordbook-error-list">
            <li v-for="(item, index) in preview.errors" :key="`${item.row_number}-${item.column}-${index}`">
              <strong>{{ item.row_number ? `第 ${item.row_number} 行` : '文件级错误' }}</strong>
              <span v-if="item.column">· {{ item.column }}</span>
              <p>{{ item.message }}</p>
            </li>
          </ul>
        </section>

        <ErrorNotice v-if="importError" :error="importError" :show-retry="false" />

        <div v-if="confirming || importProgress !== null" class="wordbook-task-card" aria-live="polite">
          <div class="wordbook-task-heading">
            <strong>{{ importProgress !== null ? '后台导入中' : '已提交导入任务' }}</strong>
            <span>{{ importProgress !== null ? `${importProgress}%` : '等待状态' }}</span>
          </div>
          <div
            v-if="importProgress !== null"
            class="progress-track"
            role="progressbar"
            :aria-valuenow="importProgress"
            aria-valuemin="0"
            aria-valuemax="100"
          >
            <span :style="{ width: `${importProgress}%` }"></span>
          </div>
          <p v-if="importWordbookId" class="field-hint">词书 ID：<code>{{ importWordbookId }}</code></p>
        </div>

        <footer class="dialog-actions button-row">
          <button type="button" :disabled="!canConfirm" @click="confirmImport">
            {{ confirming ? '正在确认并轮询…' : '确认导入' }}
          </button>
          <button class="button-secondary" type="button" :disabled="confirming" @click="resetPreview">重新预览</button>
          <button class="button-secondary" type="button" :disabled="confirming" @click="close">取消</button>
        </footer>
      </template>
    </section>
  </div>
</template>