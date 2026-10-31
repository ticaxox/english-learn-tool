<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import ErrorNotice from './ErrorNotice.vue'
import type {
  AiProvider,
  ProviderCreateInput,
  ProviderPatchInput,
} from '../api/ai-admin'

interface ValidatedProviderFields {
  name: string
  baseUrl: string
  modelId: string
  priority: number
  timeoutSeconds: number
  enabled: boolean
  isDefault: boolean
  customHeaders: Record<string, string>
}

const props = defineProps<{
  provider?: AiProvider | null
  saving?: boolean
  error?: unknown
}>()

const emit = defineEmits<{
  (event: 'create', input: ProviderCreateInput): void
  (event: 'update', providerId: string, input: ProviderPatchInput): void
  (event: 'cancel'): void
}>()

const name = ref('')
const baseUrl = ref('')
const modelId = ref('')
const priority = ref(100)
const timeoutSeconds = ref(120)
const enabled = ref(true)
const isDefault = ref(false)
const customHeadersText = ref('{}')
const apiKey = ref('')
const errors = reactive<Record<string, string>>({})

const editing = computed(() => Boolean(props.provider))
const maskedKey = computed(() => (editing.value ? props.provider?.apiKeyMasked ?? '' : ''))
const keyChanged = computed(() => editing.value && apiKey.value !== '' && apiKey.value !== maskedKey.value)
const title = computed(() => (editing.value ? `编辑 ${props.provider?.name}` : '新增 AI 提供商'))

const forbiddenHeaders = new Set([
  'authorization',
  'host',
  'content-length',
  'transfer-encoding',
  'connection',
  'cookie',
  'proxy-authorization',
  'x-forwarded-for',
  'x-forwarded-host',
  'x-real-ip',
])

function reset(): void {
  const provider = props.provider
  name.value = provider?.name ?? ''
  baseUrl.value = provider?.baseUrl ?? ''
  modelId.value = provider?.modelId ?? ''
  priority.value = provider?.priority ?? 100
  timeoutSeconds.value = provider?.timeoutSeconds ?? 120
  enabled.value = provider?.enabled ?? true
  isDefault.value = provider?.isDefault ?? false
  customHeadersText.value = provider ? JSON.stringify(provider.customHeaders, null, 2) : '{}'
  apiKey.value = provider?.apiKeyMasked ?? ''
  Object.keys(errors).forEach((key) => delete errors[key])
}

watch(() => props.provider, reset, { immediate: true })

watch(isDefault, (value) => {
  if (value) enabled.value = true
})

function clearErrors(): void {
  Object.keys(errors).forEach((key) => delete errors[key])
}

function parseHeaders(): Record<string, string> | null {
  const text = customHeadersText.value.trim()
  if (!text) return {}
  let parsed: unknown
  try {
    parsed = JSON.parse(text)
  } catch {
    errors.customHeaders = '自定义请求头必须是合法 JSON 对象。'
    return null
  }
  if (typeof parsed !== 'object' || parsed === null || Array.isArray(parsed)) {
    errors.customHeaders = '自定义请求头必须是 JSON 对象。'
    return null
  }
  const entries = Object.entries(parsed as Record<string, unknown>)
  if (entries.length > 10) {
    errors.customHeaders = '自定义请求头最多 10 个。'
    return null
  }
  const headers: Record<string, string> = {}
  for (const [rawName, rawValue] of entries) {
    const headerName = rawName.trim()
    if (!headerName || !/^[A-Za-z0-9-]+$/.test(headerName)) {
      errors.customHeaders = `请求头名称“${rawName}”不是安全的 HTTP 名称。`
      return null
    }
    if (forbiddenHeaders.has(headerName.toLowerCase())) {
      errors.customHeaders = `不允许覆盖请求头 ${headerName}。`
      return null
    }
    if (typeof rawValue !== 'string' || rawValue.length > 512 || /[\r\n]/.test(rawValue)) {
      errors.customHeaders = `请求头 ${headerName} 的值必须是不含换行的字符串。`
      return null
    }
    headers[headerName] = rawValue
  }
  return headers
}

function validate(): ValidatedProviderFields | null {
  clearErrors()
  const normalizedName = name.value.trim()
  const normalizedUrl = baseUrl.value.trim().replace(/\/+$/, '')
  const normalizedModel = modelId.value.trim()

  if (!normalizedName) errors.name = '请输入提供商名称。'
  if (!normalizedUrl) {
    errors.baseUrl = '请输入 Base URL。'
  } else {
    try {
      const url = new URL(normalizedUrl)
      if (!['http:', 'https:'].includes(url.protocol)) errors.baseUrl = 'Base URL 必须使用 http 或 https。'
    } catch {
      errors.baseUrl = 'Base URL 不是有效地址。'
    }
  }
  if (!normalizedModel) errors.modelId = '请输入模型 ID。'
  if (!Number.isInteger(priority.value) || priority.value < 0 || priority.value > 10000) {
    errors.priority = '优先级必须是 0–10000 的整数。'
  }
  if (!Number.isInteger(timeoutSeconds.value) || timeoutSeconds.value < 1 || timeoutSeconds.value > 120) {
    errors.timeoutSeconds = '超时必须是 1–120 秒的整数。'
  }
  if (isDefault.value && !enabled.value) errors.enabled = '默认提供商必须保持启用。'
  if (!editing.value || keyChanged.value) {
    if (apiKey.value.length < 8) errors.apiKey = 'API Key 至少需要 8 个字符。'
  }

  const headers = parseHeaders()
  if (Object.keys(errors).length > 0 || headers === null) return null
  return {
    name: normalizedName,
    baseUrl: normalizedUrl,
    modelId: normalizedModel,
    priority: priority.value,
    timeoutSeconds: timeoutSeconds.value,
    enabled: enabled.value,
    isDefault: isDefault.value,
    customHeaders: headers,
  }
}

function submit(): void {
  const fields = validate()
  if (!fields) return
  if (!props.provider) {
    emit('create', { ...fields, apiKey: apiKey.value })
    return
  }
  const patch: ProviderPatchInput = { ...fields }
  // An untouched field still shows the masked key; only send the key when it changed.
  if (keyChanged.value) patch.apiKey = apiKey.value
  emit('update', props.provider.id, patch)
}

function selectMaskedKey(event: FocusEvent): void {
  const input = event.target as HTMLInputElement
  if (input.value === maskedKey.value) input.select()
}

function cancel(): void {
  apiKey.value = ''
  emit('cancel')
}
</script>

<template>
  <section class="panel ai-form-panel" aria-labelledby="provider-form-title">
    <div class="section-heading">
      <div>
        <p class="eyebrow">AI 提供商</p>
        <h2 id="provider-form-title">{{ title }}</h2>
      </div>
      <button class="button-secondary button-small" type="button" @click="cancel">关闭</button>
    </div>

    <form class="ai-form" novalidate @submit.prevent="submit">
      <div class="ai-form-grid">
        <div class="field">
          <label for="provider-name">名称</label>
          <input id="provider-name" v-model="name" type="text" maxlength="100" :aria-invalid="Boolean(errors.name)" />
          <p v-if="errors.name" class="field-error" role="alert">{{ errors.name }}</p>
        </div>

        <div class="field">
          <label for="provider-model">模型 ID</label>
          <input id="provider-model" v-model="modelId" type="text" maxlength="200" :aria-invalid="Boolean(errors.modelId)" />
          <p v-if="errors.modelId" class="field-error" role="alert">{{ errors.modelId }}</p>
        </div>
      </div>

      <div class="field">
        <label for="provider-base-url">Base URL</label>
        <input id="provider-base-url" v-model="baseUrl" type="url" maxlength="500" :aria-invalid="Boolean(errors.baseUrl)" />
        <p v-if="errors.baseUrl" class="field-error" role="alert">{{ errors.baseUrl }}</p>
      </div>

      <div class="field">
        <label for="provider-api-key">API Key</label>
        <input
          id="provider-api-key"
          v-model="apiKey"
          type="text"
          autocomplete="off"
          spellcheck="false"
          maxlength="4096"
          :aria-invalid="Boolean(errors.apiKey)"
          @focus="selectMaskedKey"
        />
        <p v-if="errors.apiKey" class="field-error" role="alert">{{ errors.apiKey }}</p>
      </div>

      <div class="ai-form-grid">
        <div class="field">
          <label for="provider-timeout">生成超时（秒）</label>
          <input id="provider-timeout" v-model.number="timeoutSeconds" type="number" min="1" max="120" step="1" />
          <p v-if="errors.timeoutSeconds" class="field-error" role="alert">{{ errors.timeoutSeconds }}</p>
          <p class="field-hint">1–120 秒。单次题目、地图或教练回复的最长等待时间。</p>
        </div>

        <div class="field">
          <label for="provider-priority">备用顺序</label>
          <input id="provider-priority" v-model.number="priority" type="number" min="0" max="10000" step="1" />
          <p v-if="errors.priority" class="field-error" role="alert">{{ errors.priority }}</p>
          <p class="field-hint">数字越小越靠前，默认提供商始终最先使用。</p>
        </div>
      </div>

      <div class="field">
        <label for="provider-headers">自定义请求头（JSON）</label>
        <textarea id="provider-headers" v-model="customHeadersText" rows="3" spellcheck="false"></textarea>
        <p v-if="errors.customHeaders" class="field-error" role="alert">{{ errors.customHeaders }}</p>
        <p class="field-hint">最多 10 个；Authorization、Cookie、Host 等安全头不可覆盖。</p>
      </div>

      <div class="checkbox-row">
        <label class="checkbox"><input v-model="enabled" type="checkbox" :disabled="isDefault" /> 启用</label>
        <label class="checkbox"><input v-model="isDefault" type="checkbox" /> 设为默认提供商</label>
      </div>
      <p v-if="errors.enabled" class="field-error" role="alert">{{ errors.enabled }}</p>

      <ErrorNotice v-if="error" :error="error" :show-retry="false" retry-label="重试" @retry="() => {}" />

      <div class="button-row">
        <button class="button" type="submit" :disabled="saving">{{ saving ? '正在保存…' : '保存提供商' }}</button>
        <button class="button-secondary" type="button" :disabled="saving" @click="cancel">取消</button>
      </div>
    </form>
  </section>
</template>
