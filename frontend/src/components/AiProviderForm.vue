<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import ErrorNotice from './ErrorNotice.vue'
import type {
  AiProvider,
  ProviderCreateInput,
  ProviderPatchInput,
  ProviderTestResult,
} from '../api/ai-admin'

interface ValidatedProviderFields {
  name: string
  baseUrl: string
  modelId: string
  priority: number
  timeoutSeconds: number
  enabled: boolean
  customHeaders: Record<string, string>
}

const props = defineProps<{
  provider?: AiProvider | null
  saving?: boolean
  error?: unknown
  /** The personal settings dialog: no title, actions in the header row. */
  compact?: boolean
  /** Lets the parent fetch the model list for a saved provider. */
  canFetchModels?: boolean
  modelOptions?: string[]
  modelLoading?: boolean
  modelError?: unknown
  testLoading?: boolean
  testResult?: ProviderTestResult | null
}>()

const emit = defineEmits<{
  (event: 'create', input: ProviderCreateInput): void
  (event: 'update', providerId: string, input: ProviderPatchInput): void
  (event: 'cancel'): void
  (event: 'fetch-models'): void
  (event: 'test'): void
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
const modelsOpen = ref(false)
const modelsFetched = ref(false)
const errors = reactive<Record<string, string>>({})

const editing = computed(() => Boolean(props.provider))
const title = computed(() => (editing.value ? `编辑 ${props.provider?.name}` : '新增 AI 提供商'))
const maskedKey = computed(() => (editing.value ? props.provider?.apiKeyMasked ?? '' : ''))
const keyChanged = computed(() => editing.value && apiKey.value !== '')

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
  apiKey.value = ''
  modelsOpen.value = false
  modelsFetched.value = false
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
  if (!editing.value || keyChanged.value) {
    if (apiKey.value.trim().length < 8) errors.apiKey = 'API Key 至少需要 8 个字符。'
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
    customHeaders: headers,
  }
}

function submit(): void {
  const fields = validate()
  if (!fields) return
  if (!props.provider) {
    emit('create', { ...fields, isDefault: false, apiKey: apiKey.value })
    return
  }
  const patch: ProviderPatchInput = { ...fields }
  if (!props.compact) patch.isDefault = isDefault.value
  // The stored key is never sent to the browser; only a newly typed key is saved.
  if (keyChanged.value) patch.apiKey = apiKey.value.trim()
  emit('update', props.provider.id, patch)
}

function toggleModels(): void {
  modelsOpen.value = !modelsOpen.value
}

function chooseModel(model: string): void {
  modelId.value = model
  modelsOpen.value = false
}

function cancel(): void {
  apiKey.value = ''
  emit('cancel')
}
</script>

<template>
  <section class="panel ai-form-panel" :class="{ 'ai-form-panel--compact': compact }" :aria-label="compact ? 'AI 提供商配置' : undefined" :aria-labelledby="compact ? undefined : 'provider-form-title'">
    <div v-if="!compact" class="section-heading">
      <div>
        <p class="eyebrow">AI 提供商</p>
        <h2 id="provider-form-title">{{ title }}</h2>
      </div>
      <DivButton class="button-secondary button-small" type="button" @click="cancel">关闭</DivButton>
    </div>

    <form class="ai-form" novalidate @submit.prevent="submit">
      <div class="ai-form-top">
        <div class="field">
          <label for="provider-name">名称</label>
          <input id="provider-name" v-model="name" type="text" maxlength="100" :aria-invalid="Boolean(errors.name)" />
          <p v-if="errors.name" class="field-error" role="alert">{{ errors.name }}</p>
        </div>
        <div class="ai-form-actions">
          <DivButton
            class="button-secondary ai-toggle"
            type="button"
            :aria-pressed="enabled"
            @click="enabled = !enabled"
          >
            <span class="ai-toggle__dot" :class="{ 'is-on': enabled }" aria-hidden="true"></span>
            {{ enabled ? '停用' : '启用' }}
          </DivButton>
          <DivButton class="button" type="submit" :disabled="saving">{{ saving ? '正在保存…' : '保存' }}</DivButton>
          <DivButton class="button-secondary" type="button" :disabled="saving" @click="cancel">取消</DivButton>
        </div>
      </div>

      <div class="field ai-model-field">
        <label for="provider-model">模型 ID</label>
        <div class="ai-model-row">
          <div class="ai-model-input">
            <input id="provider-model" v-model="modelId" type="text" maxlength="200" :aria-invalid="Boolean(errors.modelId)" />
            <DivButton
              v-if="modelOptions && modelOptions.length"
              class="ai-model-caret"
              type="button"
              aria-label="从已获取的模型中选择"
              :aria-expanded="modelsOpen"
              @click="toggleModels"
            >
              <span class="ai-model-fetch__arrow" :class="{ 'is-open': modelsOpen }" aria-hidden="true">▾</span>
            </DivButton>
          </div>
          <DivButton
            v-if="canFetchModels"
            class="button-secondary ai-model-fetch"
            type="button"
            :disabled="modelLoading"
            @click="modelsFetched = true; emit('fetch-models')"
          >
            {{ modelLoading ? '读取中…' : '获取模型' }}
          </DivButton>
          <DivButton
            v-if="editing"
            class="button-secondary"
            type="button"
            :disabled="testLoading"
            @click="emit('test')"
          >
            {{ testLoading ? '连接中…' : '测试连接' }}
          </DivButton>
        </div>
        <p v-if="editing && testResult" class="field-hint">
          {{ testResult.success ? `连接正常 · ${testResult.latencyMs ?? '—'} ms` : '连接失败，请检查地址、模型和 Key。' }}
        </p>
        <p v-if="errors.modelId" class="field-error" role="alert">{{ errors.modelId }}</p>
        <p v-else-if="modelsFetched && !modelLoading && modelOptions && modelOptions.length === 0" class="field-hint">这个接口没有返回模型列表，直接手填模型 ID 即可。</p>
        <ErrorNotice v-if="modelError" :error="modelError" :show-retry="false" />

        <div v-if="canFetchModels && modelsOpen" class="ai-model-menu" role="listbox" aria-label="可用模型">
          <p v-if="modelLoading" class="field-hint">正在读取模型列表…</p>
          <template v-else-if="modelOptions && modelOptions.length">
            <DivButton
              v-for="model in modelOptions"
              :key="model"
              class="ai-model-option"
              :class="{ 'is-selected': model === modelId }"
              type="button"
              role="option"
              :aria-selected="model === modelId"
              @click="chooseModel(model)"
            >{{ model }}</DivButton>
          </template>
          <p v-else class="field-hint">这个接口没有返回模型列表，直接手填模型 ID 即可。</p>
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
          type="password"
          autocomplete="new-password"
          spellcheck="false"
          maxlength="4096"
          :placeholder="editing ? (maskedKey || '留空保持当前 Key') : '至少 8 个字符'"
          :aria-invalid="Boolean(errors.apiKey)"
        />
        <p v-if="editing && !errors.apiKey" class="field-hint">已保存的 Key 不会回显；需要更换时直接输入新 Key。</p>
        <p v-if="errors.apiKey" class="field-error" role="alert">{{ errors.apiKey }}</p>
      </div>

      <div class="field">
        <label for="provider-headers">自定义请求头（JSON）</label>
        <textarea id="provider-headers" v-model="customHeadersText" rows="3" spellcheck="false"></textarea>
        <p v-if="errors.customHeaders" class="field-error" role="alert">{{ errors.customHeaders }}</p>
        <p class="field-hint">最多 10 个；Authorization、Cookie、Host 等安全头不可覆盖。</p>
      </div>

      <label v-if="!compact" class="checkbox">
        <input v-model="isDefault" type="checkbox" />
        设为默认提供商
      </label>

      <ErrorNotice v-if="error" :error="error" :show-retry="false" retry-label="重试" @retry="() => {}" />

      <div v-if="!compact" class="button-row">
        <DivButton class="button" type="submit" :disabled="saving">{{ saving ? '正在保存…' : '保存提供商' }}</DivButton>
        <DivButton class="button-secondary" type="button" :disabled="saving" @click="cancel">取消</DivButton>
      </div>
    </form>
  </section>
</template>
