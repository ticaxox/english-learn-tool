<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import AiProviderForm from '../components/AiProviderForm.vue'
import ErrorNotice from '../components/ErrorNotice.vue'
import LoadingState from '../components/LoadingState.vue'
import { apiClient } from '../api/client'
import {
  createProvider,
  deleteProvider,
  fetchProviderModels,
  listProviders,
  testProvider,
  updateProvider,
  type AiProvider,
  type ProviderCreateInput,
  type ProviderModelsResult,
  type ProviderPatchInput,
  type ProviderTestResult,
} from '../api/ai-admin'
import '../ai-admin.css'

interface OperationState<T> {
  loading: boolean
  result: T | null
  error: unknown
  requestId: string | null
}

const providers = ref<AiProvider[]>([])
const loading = ref(false)
const loadError = ref<unknown>(null)
const formOpen = ref(false)
const editingProvider = ref<AiProvider | null>(null)
const saving = ref(false)
const saveError = ref<unknown>(null)
const operationError = ref<unknown>(null)
const actionKey = ref<string | null>(null)
const testStates = reactive<Record<string, OperationState<ProviderTestResult>>>({})
const modelStates = reactive<Record<string, OperationState<ProviderModelsResult>>>({})

const sortedProviders = computed(() =>
  [...providers.value].sort((a, b) => {
    if (a.isDefault !== b.isDefault) return a.isDefault ? -1 : 1
    if (a.priority !== b.priority) return a.priority - b.priority
    return a.name.localeCompare(b.name, 'zh-CN')
  }),
)

const defaultCount = computed(() => providers.value.filter((item) => item.isDefault).length)
const enabledCount = computed(() => providers.value.filter((item) => item.enabled).length)

function providerState<T>(store: Record<string, OperationState<T>>, id: string): OperationState<T> {
  return store[id] ?? { loading: false, result: null, error: null, requestId: null }
}

function setTestState(id: string, patch: Partial<OperationState<ProviderTestResult>>): void {
  testStates[id] = { ...providerState(testStates, id), ...patch }
}

function setModelState(id: string, patch: Partial<OperationState<ProviderModelsResult>>): void {
  modelStates[id] = { ...providerState(modelStates, id), ...patch }
}

async function load(): Promise<void> {
  loading.value = true
  loadError.value = null
  try {
    providers.value = await listProviders()
  } catch (error) {
    providers.value = []
    loadError.value = error
  } finally {
    loading.value = false
  }
}

function openCreate(): void {
  editingProvider.value = null
  saveError.value = null
  formOpen.value = true
}

function openEdit(provider: AiProvider): void {
  editingProvider.value = provider
  saveError.value = null
  formOpen.value = true
}

function closeForm(): void {
  formOpen.value = false
  editingProvider.value = null
  saveError.value = null
}

async function handleCreate(input: ProviderCreateInput): Promise<void> {
  saving.value = true
  saveError.value = null
  try {
    await createProvider(input)
    closeForm()
    await load()
  } catch (error) {
    saveError.value = error
  } finally {
    saving.value = false
  }
}

async function handleUpdate(providerId: string, input: ProviderPatchInput): Promise<void> {
  saving.value = true
  saveError.value = null
  try {
    await updateProvider(providerId, input)
    closeForm()
    await load()
  } catch (error) {
    saveError.value = error
  } finally {
    saving.value = false
  }
}

async function patchProvider(providerId: string, input: ProviderPatchInput, key: string): Promise<void> {
  if (actionKey.value) return
  actionKey.value = key
  operationError.value = null
  try {
    await updateProvider(providerId, input)
    await load()
  } catch (error) {
    operationError.value = error
  } finally {
    actionKey.value = null
  }
}

function toggleEnabled(provider: AiProvider): void {
  const input: ProviderPatchInput = { enabled: !provider.enabled }
  if (provider.isDefault && !input.enabled) return
  void patchProvider(provider.id, input, `enabled:${provider.id}`)
}

function makeDefault(provider: AiProvider): void {
  void patchProvider(provider.id, { isDefault: true }, `default:${provider.id}`)
}

async function removeProvider(provider: AiProvider): Promise<void> {
  const confirmed = window.confirm(`确认删除提供商“${provider.name}”？后端会按真实配置提升下一启用备用项。`)
  if (!confirmed) return
  actionKey.value = `delete:${provider.id}`
  operationError.value = null
  try {
    await deleteProvider(provider.id)
    await load()
  } catch (error) {
    operationError.value = error
  } finally {
    actionKey.value = null
  }
}

async function runTest(provider: AiProvider): Promise<void> {
  setTestState(provider.id, { loading: true, result: null, error: null, requestId: null })
  try {
    const result = await testProvider(provider.id)
    setTestState(provider.id, {
      loading: false,
      result,
      error: null,
      requestId: apiClient.getLastRequestId(),
    })
    await load()
  } catch (error) {
    setTestState(provider.id, {
      loading: false,
      result: null,
      error,
      requestId: apiClient.getLastRequestId(),
    })
  }
}

async function loadModels(provider: AiProvider): Promise<void> {
  setModelState(provider.id, { loading: true, result: null, error: null, requestId: null })
  try {
    const result = await fetchProviderModels(provider.id)
    setModelState(provider.id, {
      loading: false,
      result,
      error: null,
      requestId: apiClient.getLastRequestId(),
    })
  } catch (error) {
    setModelState(provider.id, {
      loading: false,
      result: null,
      error,
      requestId: apiClient.getLastRequestId(),
    })
  }
}

async function selectModel(provider: AiProvider, modelId: string): Promise<void> {
  await patchProvider(provider.id, { modelId }, `model:${provider.id}:${modelId}`)
}

function providerRole(provider: AiProvider): string {
  if (provider.isDefault) return '默认提供商'
  return provider.enabled ? '备用提供商' : '已禁用'
}

function testStatusLabel(provider: AiProvider): string {
  if (provider.lastTestStatus === 'succeeded') return '最近检查成功'
  if (provider.lastTestStatus === 'failed') return '最近检查失败'
  return '尚未检查'
}

onMounted(() => {
  void load()
})
</script>

<template>
  <article class="ai-admin-page providers-page">
    <header class="ai-admin-hero">
      <div>
        <p class="eyebrow">管理员 · AI 配置</p>
        <h1>AI 提供商</h1>
        <p class="lead">配置 OpenAI 兼容提供商，查看服务端掩码、真实连接检查、模型列表与默认/备用顺序。</p>
      </div>
      <DivButton class="button" type="button" @click="openCreate">新增提供商</DivButton>
    </header>

    <section class="ai-summary-strip" aria-label="提供商摘要">
      <div><strong>{{ providers.length }}</strong><span>全部提供商</span></div>
      <div><strong>{{ enabledCount }}</strong><span>已启用</span></div>
      <div><strong>{{ defaultCount }}</strong><span>默认项</span></div>
    </section>

    <AiProviderForm
      v-if="formOpen"
      :provider="editingProvider"
      :saving="saving"
      :error="saveError"
      @create="handleCreate"
      @update="handleUpdate"
      @cancel="closeForm"
    />

    <ErrorNotice v-if="operationError" :error="operationError" :show-retry="false" retry-label="重试" @retry="() => {}" />

    <LoadingState v-if="loading" label="正在读取真实提供商配置…" />

    <section v-else-if="loadError" class="panel">
      <ErrorNotice :error="loadError" retry-label="重新读取提供商" @retry="load" />
    </section>

    <section v-else-if="providers.length === 0" class="panel empty-state">
      <h2>尚未配置 AI 提供商</h2>
      <p>新增后由服务端加密保存 Key，前端只显示掩码。连接测试和模型列表会发起真实网络请求。</p>
      <DivButton class="button" type="button" @click="openCreate">新增第一个提供商</DivButton>
    </section>

    <section v-else class="provider-list" aria-label="AI 提供商列表">
      <article v-for="(provider, index) in sortedProviders" :key="provider.id" class="provider-card">
        <header class="provider-card__header">
          <div>
            <p class="eyebrow">{{ providerRole(provider) }}</p>
            <h2>{{ provider.name }}</h2>
            <p class="inline-note">顺序 {{ index + 1 }} · 优先级 {{ provider.priority }}</p>
          </div>
          <span class="status-badge" :class="`status-badge--${provider.enabled ? 'success' : 'muted'}`">
            {{ provider.enabled ? '已启用' : '已禁用' }}
          </span>
        </header>

        <dl class="provider-facts">
          <div><dt>模型</dt><dd><code>{{ provider.modelId }}</code></dd></div>
          <div><dt>Base URL</dt><dd><code>{{ provider.baseUrl }}</code></dd></div>
          <div><dt>API Key</dt><dd><code>{{ provider.apiKeyMasked }}</code></dd></div>
          <div><dt>超时</dt><dd>{{ provider.timeoutSeconds }} 秒</dd></div>
          <div><dt>自定义头</dt><dd>{{ Object.keys(provider.customHeaders).length }} 个</dd></div>
          <div><dt>最近检查</dt><dd>{{ testStatusLabel(provider) }}<span v-if="provider.lastTestLatencyMs !== null"> · {{ provider.lastTestLatencyMs }} ms</span></dd></div>
        </dl>

        <p v-if="provider.lastTestErrorCode" class="alert alert-warning">
          最近失败：<code>{{ provider.lastTestErrorCode }}</code>
        </p>

        <div class="button-row provider-actions">
          <DivButton class="button-secondary button-small" type="button" @click="openEdit(provider)">编辑</DivButton>
          <DivButton class="button-secondary button-small" type="button" :disabled="testStates[provider.id]?.loading" @click="runTest(provider)">
            {{ testStates[provider.id]?.loading ? '检查中…' : '连接检查' }}
          </DivButton>
          <DivButton class="button-secondary button-small" type="button" :disabled="modelStates[provider.id]?.loading" @click="loadModels(provider)">
            {{ modelStates[provider.id]?.loading ? '读取中…' : '获取模型' }}
          </DivButton>
          <DivButton
            v-if="!provider.isDefault"
            class="button-secondary button-small"
            type="button"
            :disabled="Boolean(actionKey)"
            @click="makeDefault(provider)"
          >设为默认</DivButton>
          <DivButton class="button-secondary button-small" type="button" :disabled="Boolean(actionKey) || provider.isDefault" @click="toggleEnabled(provider)">
            {{ provider.enabled ? '停用' : '启用' }}
          </DivButton>
          <DivButton class="button-danger button-small" type="button" :disabled="Boolean(actionKey)" @click="removeProvider(provider)">删除</DivButton>
        </div>

        <section v-if="testStates[provider.id]?.result || testStates[provider.id]?.error" class="operation-result" aria-live="polite">
          <template v-if="testStates[provider.id]?.result">
            <strong :class="testStates[provider.id].result!.success ? 'text-success' : 'text-danger'">
              {{ testStates[provider.id].result!.success ? '真实连接检查成功' : '真实连接检查失败' }}
            </strong>
            <p v-if="testStates[provider.id].result!.latencyMs !== null">耗时：{{ testStates[provider.id].result!.latencyMs }} ms</p>
            <p v-if="testStates[provider.id].result!.errorCode">错误码：<code>{{ testStates[provider.id].result!.errorCode }}</code></p>
            <p v-if="testStates[provider.id].result!.errorMessage">{{ testStates[provider.id].result!.errorMessage }}</p>
            <p v-if="testStates[provider.id].result!.models.length > 0">服务端同时返回 {{ testStates[provider.id].result!.models.length }} 个模型。</p>
          </template>
          <ErrorNotice v-else :error="testStates[provider.id].error" :show-retry="false" retry-label="重试" @retry="() => runTest(provider)" />
          <p v-if="testStates[provider.id]?.requestId" class="inline-note">Request ID：<code>{{ testStates[provider.id].requestId }}</code></p>
        </section>

        <section v-if="modelStates[provider.id]?.result || modelStates[provider.id]?.error" class="operation-result" aria-live="polite">
          <template v-if="modelStates[provider.id]?.result?.success">
            <strong>服务端返回 {{ modelStates[provider.id].result!.models.length }} 个模型</strong>
            <div class="model-chip-list">
              <DivButton
                v-for="model in modelStates[provider.id].result!.models"
                :key="model"
                class="model-chip"
                type="button"
                :class="{ 'model-chip--selected': model === provider.modelId }"
                :disabled="Boolean(actionKey)"
                @click="selectModel(provider, model)"
              >{{ model }}</DivButton>
            </div>
          </template>
          <template v-else-if="modelStates[provider.id]?.result">
            <strong class="text-danger">模型列表读取失败</strong>
            <p v-if="modelStates[provider.id].result!.errorCode">错误码：<code>{{ modelStates[provider.id].result!.errorCode }}</code></p>
            <p v-if="modelStates[provider.id].result!.errorMessage">{{ modelStates[provider.id].result!.errorMessage }}</p>
            <p class="inline-note">可打开编辑表单手填模型 ID，不会伪造模型列表。</p>
          </template>
          <ErrorNotice v-else :error="modelStates[provider.id].error" :show-retry="false" retry-label="重试" @retry="() => loadModels(provider)" />
          <p v-if="modelStates[provider.id]?.requestId" class="inline-note">Request ID：<code>{{ modelStates[provider.id].requestId }}</code></p>
        </section>
      </article>
    </section>
  </article>
</template>