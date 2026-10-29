<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import AiProviderForm from '../components/AiProviderForm.vue'
import AppIcon from '../components/AppIcon.vue'
import ErrorNotice from '../components/ErrorNotice.vue'
import LoadingState from '../components/LoadingState.vue'
import {
  createPersonalProvider,
  deletePersonalProvider,
  fetchPersonalProviderModels,
  listPersonalProviders,
  testPersonalProvider,
  updatePersonalProvider,
  type AiProvider,
  type ProviderCreateInput,
  type ProviderModelsResult,
  type ProviderPatchInput,
  type ProviderTestResult,
} from '../api/personal-ai'
import '../ai-admin.css'

interface OperationState<T> {
  loading: boolean
  result: T | null
  error: unknown
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
const deleteTarget = ref<AiProvider | null>(null)
const testStates = reactive<Record<string, OperationState<ProviderTestResult>>>({})
const modelStates = reactive<Record<string, OperationState<ProviderModelsResult>>>({})

const sortedProviders = computed(() => [...providers.value].sort((left, right) => {
  if (left.isDefault !== right.isDefault) return left.isDefault ? -1 : 1
  if (left.priority !== right.priority) return left.priority - right.priority
  return left.name.localeCompare(right.name, 'zh-CN')
}))

const defaultProvider = computed(() => providers.value.find((provider) => provider.isDefault) ?? null)

function operation<T>(store: Record<string, OperationState<T>>, id: string): OperationState<T> {
  return store[id] ?? { loading: false, result: null, error: null }
}

function setTestState(id: string, patch: Partial<OperationState<ProviderTestResult>>): void {
  testStates[id] = { ...operation(testStates, id), ...patch }
}

function setModelState(id: string, patch: Partial<OperationState<ProviderModelsResult>>): void {
  modelStates[id] = { ...operation(modelStates, id), ...patch }
}

function orderLabel(provider: AiProvider): string {
  if (provider.isDefault) return '默认'
  const index = sortedProviders.value.findIndex((item) => item.id === provider.id)
  return index >= 0 ? `备用 ${index + (defaultProvider.value ? 0 : 1)}` : '备用'
}

function lastTestLabel(provider: AiProvider): string {
  if (provider.lastTestStatus === 'succeeded') return '最近连接正常'
  if (provider.lastTestStatus === 'failed') return '最近连接失败'
  return '尚未检查连接'
}

async function load(): Promise<void> {
  loading.value = true
  loadError.value = null
  try {
    providers.value = await listPersonalProviders()
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
    await createPersonalProvider(input)
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
    await updatePersonalProvider(providerId, input)
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
    await updatePersonalProvider(providerId, input)
    await load()
  } catch (error) {
    operationError.value = error
  } finally {
    actionKey.value = null
  }
}

function makeDefault(provider: AiProvider): void {
  void patchProvider(provider.id, { isDefault: true, enabled: true }, `default:${provider.id}`)
}

function toggleEnabled(provider: AiProvider): void {
  if (provider.isDefault && provider.enabled) return
  void patchProvider(provider.id, { enabled: !provider.enabled }, `enabled:${provider.id}`)
}

async function runTest(provider: AiProvider): Promise<void> {
  setTestState(provider.id, { loading: true, result: null, error: null })
  try {
    setTestState(provider.id, { result: await testPersonalProvider(provider.id) })
    await load()
  } catch (error) {
    setTestState(provider.id, { error })
  } finally {
    setTestState(provider.id, { loading: false })
  }
}

async function loadModels(provider: AiProvider): Promise<void> {
  setModelState(provider.id, { loading: true, result: null, error: null })
  try {
    setModelState(provider.id, { result: await fetchPersonalProviderModels(provider.id) })
  } catch (error) {
    setModelState(provider.id, { error })
  } finally {
    setModelState(provider.id, { loading: false })
  }
}

function selectModel(provider: AiProvider, modelId: string): void {
  void patchProvider(provider.id, { modelId }, `model:${provider.id}`)
}

async function confirmDelete(): Promise<void> {
  const provider = deleteTarget.value
  if (!provider) return
  actionKey.value = `delete:${provider.id}`
  operationError.value = null
  try {
    await deletePersonalProvider(provider.id)
    deleteTarget.value = null
    await load()
  } catch (error) {
    operationError.value = error
  } finally {
    actionKey.value = null
  }
}

onMounted(() => {
  void load()
})
</script>

<template>
  <section class="personal-ai-page" :class="{ 'personal-ai-page--editing': formOpen }" aria-labelledby="personal-ai-title">
    <div class="personal-ai-main">
      <div class="personal-ai-toolbar">
        <div>
          <h2 id="personal-ai-title">你的 AI 提供商</h2>
          <p class="field-hint">只显示当前账号自己的配置。默认提供商优先，其他提供商按备用顺序接管。</p>
        </div>
        <button class="button" type="button" @click="openCreate">添加 AI 提供商</button>
      </div>

      <LoadingState v-if="loading && providers.length === 0" label="正在读取 AI 配置…" />
      <ErrorNotice v-else-if="loadError" :error="loadError" retry-label="重新读取 AI 配置" @retry="load" />

      <div v-else-if="providers.length === 0" class="personal-ai-empty">
        <span class="personal-ai-empty__mark" aria-hidden="true"><AppIcon name="spark" /></span>
        <div>
          <h3>还没有 AI 提供商</h3>
          <p>添加一个 OpenAI 兼容服务，AI 教练、练习生成和评分才能开始工作。</p>
        </div>
        <button v-if="!formOpen" class="button" type="button" @click="openCreate">添加第一个提供商</button>
      </div>

      <div v-else class="personal-ai-list">
        <article v-for="provider in sortedProviders" :key="provider.id" class="personal-ai-provider">
          <div>
            <div class="personal-ai-provider__meta">
              <span class="status-badge" :class="provider.enabled ? 'status-badge--success' : 'status-badge--muted'">
                {{ provider.enabled ? '已启用' : '已停用' }}
              </span>
              <span class="count-pill">{{ orderLabel(provider) }}</span>
              <span class="field-hint">{{ lastTestLabel(provider) }}</span>
            </div>
            <h3>{{ provider.name }}</h3>
            <p class="field-hint">{{ provider.modelId }} · {{ provider.baseUrl }}</p>
            <p class="masked-value">API Key：<code>{{ provider.apiKeyMasked }}</code></p>
          </div>
          <div class="personal-ai-provider__actions">
            <button class="button-secondary" type="button" @click="openEdit(provider)">编辑</button>
            <button class="button-secondary" type="button" :disabled="testStates[provider.id]?.loading" @click="runTest(provider)">
              {{ testStates[provider.id]?.loading ? '检查中…' : '测试连接' }}
            </button>
            <button class="button-secondary" type="button" :disabled="modelStates[provider.id]?.loading" @click="loadModels(provider)">
              {{ modelStates[provider.id]?.loading ? '读取中…' : '获取模型' }}
            </button>
            <button v-if="!provider.isDefault" class="button-secondary" type="button" :disabled="Boolean(actionKey)" @click="makeDefault(provider)">设为默认</button>
            <button class="button-secondary" type="button" :disabled="Boolean(actionKey) || provider.isDefault" @click="toggleEnabled(provider)">
              {{ provider.enabled ? '停用' : '启用' }}
            </button>
            <button class="button-danger" type="button" :disabled="Boolean(actionKey)" @click="deleteTarget = provider">删除</button>
          </div>

          <div v-if="testStates[provider.id]?.result" class="operation-result" aria-live="polite">
            <strong>{{ testStates[provider.id].result!.success ? '连接成功' : '连接未通过' }}</strong>
            <p v-if="testStates[provider.id].result!.success && testStates[provider.id].result!.latencyMs !== null">
              响应耗时 {{ testStates[provider.id].result!.latencyMs }} ms。
            </p>
            <p v-else>请检查接口地址、模型 ID 和 API Key 后重试。</p>
          </div>
          <ErrorNotice v-if="testStates[provider.id]?.error" :error="testStates[provider.id].error" :show-retry="false" />

          <div v-if="modelStates[provider.id]?.result?.success" class="operation-result">
            <strong>可用模型</strong>
            <div class="model-chip-list">
              <button
                v-for="model in modelStates[provider.id].result!.models"
                :key="model"
                class="model-chip"
                type="button"
                :class="{ 'model-chip--selected': model === provider.modelId }"
                :disabled="Boolean(actionKey)"
                @click="selectModel(provider, model)"
              >{{ model }}</button>
            </div>
          </div>
          <div v-else-if="modelStates[provider.id]?.result" class="operation-result">
            <strong>模型列表暂时不可用</strong>
            <p>可以继续在编辑表单中手动填写模型 ID。</p>
          </div>
          <ErrorNotice v-if="modelStates[provider.id]?.error" :error="modelStates[provider.id].error" :show-retry="false" />
        </article>
      </div>

      <ErrorNotice v-if="operationError" :error="operationError" :show-retry="false" />

      <section v-if="deleteTarget" class="alert alert-warning" role="alertdialog" aria-labelledby="delete-provider-title">
        <strong id="delete-provider-title">删除 {{ deleteTarget.name }}？</strong>
        <p>删除后该提供商配置和密钥会从当前账号移除，其他备用提供商不受影响。</p>
        <div class="button-row">
          <button class="button-danger" type="button" :disabled="Boolean(actionKey)" @click="confirmDelete">
            {{ actionKey?.startsWith('delete:') ? '正在删除…' : '确认删除' }}
          </button>
          <button class="button-secondary" type="button" :disabled="Boolean(actionKey)" @click="deleteTarget = null">取消</button>
        </div>
      </section>

    </div>

    <aside class="personal-ai-aside" aria-label="AI 提供商配置详情">
      <div v-if="formOpen" class="provider-form-shell">
        <AiProviderForm
          :provider="editingProvider"
          :saving="saving"
          :error="saveError"
          @create="handleCreate"
          @update="handleUpdate"
          @cancel="closeForm"
        />
      </div>

      <div v-else class="personal-ai-guide">
        <p class="eyebrow">配置说明</p>
        <h3>配置后就能用</h3>
        <ul class="personal-ai-guide__list">
          <li>AI 教练对话与学习计划调整</li>
          <li>AI 练习生成、评分与错题解析</li>
          <li>每日闯关的题目生成</li>
        </ul>
        <h3>密钥怎么保存</h3>
        <p class="field-hint">
          密钥加密保存，页面只显示掩码；每个账号只能看到自己的提供商，其他账号互不影响。
        </p>
        <h3>建议顺序</h3>
        <p class="field-hint">先保存配置，再用“测试连接”确认可达，最后获取模型列表选择模型 ID。</p>
      </div>
    </aside>
  </section>
</template>
