<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import AiMemoryPanel from '../components/AiMemoryPanel.vue'
import CrumbNumber from '../components/ui/CrumbNumber.vue'
import AiQuotaPanel from '../components/AiQuotaPanel.vue'
import AiProviderForm from '../components/AiProviderForm.vue'
import AppIcon from '../components/AppIcon.vue'
import ErrorNotice from '../components/ErrorNotice.vue'
import LoadingState from '../components/LoadingState.vue'
import {
  createPersonalProvider,
  deletePersonalProvider,
  listPersonalProviders,
  probePersonalProvider,
  probePersonalProviderModels,
  updatePersonalProvider,
  type AiProvider,
  type AiProviderKind,
  type ProviderCreateInput,
  type ProviderPatchInput,
  type ProviderProbeInput,
  type ProviderTestResult,
} from '../api/personal-ai'
import '../ai-admin.css'
import { useToast } from '../composables/useToast'

const providers = ref<AiProvider[]>([])
const toast = useToast()
const loading = ref(false)
const loadError = ref<unknown>(null)
const formOpen = ref(false)
const editingProvider = ref<AiProvider | null>(null)
const saving = ref(false)
const saveError = ref<unknown>(null)
const operationError = ref<unknown>(null)
const actionKey = ref<string | null>(null)
const deleteTarget = ref<AiProvider | null>(null)
const formModels = ref<string[]>([])
const formModelsLoading = ref(false)
const formModelError = ref<unknown>(null)
const formTestLoading = ref(false)
const formTestResult = ref<ProviderTestResult | null>(null)

function byPriority(list: AiProvider[]): AiProvider[] {
  return [...list].sort((left, right) => {
    if (left.priority !== right.priority) return left.priority - right.priority
    return left.name.localeCompare(right.name, 'zh-CN')
  })
}

/** Writing text and making vectors are separate services, listed apart. */
const chatProviders = computed(() => byPriority(providers.value.filter((p) => p.kind !== 'embedding')))
const embeddingProviders = computed(() => byPriority(providers.value.filter((p) => p.kind === 'embedding')))

/** One shelf: chat first, then embedding, each by priority. */
const sortedProviders = computed(() => [...chatProviders.value, ...embeddingProviders.value])

/** Which list the open form belongs to. */
const formKind = ref<AiProviderKind>('chat')

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

function resetFormSideState(): void {
  formModels.value = []
  formModelsLoading.value = false
  formModelError.value = null
  formTestLoading.value = false
  formTestResult.value = null
}

function openCreate(kind: AiProviderKind = 'chat'): void {
  editingProvider.value = null
  formKind.value = kind
  saveError.value = null
  resetFormSideState()
  formOpen.value = true
}

function openEdit(provider: AiProvider): void {
  editingProvider.value = provider
  formKind.value = provider.kind
  saveError.value = null
  resetFormSideState()
  formOpen.value = true
}

async function loadFormModels(input: ProviderProbeInput): Promise<void> {
  if (formModelsLoading.value) return
  formModelsLoading.value = true
  formModelError.value = null
  try {
    const result = await probePersonalProviderModels(input)
    formModels.value = result.success ? result.models : []
    if (!result.success) {
      toast.error('获取模型失败', '检查 Base URL 和 API Key 后重试。')
    }
  } catch (error) {
    formModels.value = []
    formModelError.value = error
  } finally {
    formModelsLoading.value = false
  }
}

async function testFormProvider(input: ProviderProbeInput): Promise<void> {
  if (formTestLoading.value) return
  formTestLoading.value = true
  formTestResult.value = null
  try {
    const result = await probePersonalProvider(input)
    formTestResult.value = result
    if (result.success) {
      toast.success('连接成功', result.latencyMs === null ? undefined : `响应耗时 ${result.latencyMs} ms。`)
      if (result.models.length) formModels.value = result.models
    } else {
      toast.error('连接未通过', '检查接口地址、模型 ID 和 API Key 后重试。')
    }
  } catch (error) {
    saveError.value = error
  } finally {
    formTestLoading.value = false
  }
}

function closeForm(): void {
  formOpen.value = false
  editingProvider.value = null
  saveError.value = null
  resetFormSideState()
}

async function handleCreate(input: ProviderCreateInput): Promise<void> {
  saving.value = true
  saveError.value = null
  try {
    await createPersonalProvider(input)
    closeForm()
    await load()
    toast.success('AI 提供商已添加', '可以再打开编辑，测试连接或获取模型列表。')
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
    toast.success('AI 提供商已更新')
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
    toast.push({ title: 'AI 配置已更新', tone: 'success' })
  } catch (error) {
    operationError.value = error
  } finally {
    actionKey.value = null
  }
}

function toggleEnabled(provider: AiProvider): void {
  void patchProvider(provider.id, { enabled: !provider.enabled }, `enabled:${provider.id}`)
}

function updatePriority(provider: AiProvider, value: number): void {
  if (!Number.isInteger(value) || value < 0 || value > 10000 || value === provider.priority) return
  void patchProvider(provider.id, { priority: value }, `priority:${provider.id}`)
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
    <div class="personal-ai-main panel personal-ai-stack">
      <div class="personal-ai-toolbar">
        <div>
          <h2 id="personal-ai-title">你的 AI 提供商</h2>
        </div>
        <DivButton v-if="!formOpen" class="button" type="button" @click="openCreate('chat')">添加</DivButton>
      </div>

      <LoadingState v-if="loading && providers.length === 0" label="正在读取 AI 配置…" />
      <ErrorNotice v-else-if="loadError" :error="loadError" retry-label="重新读取 AI 配置" @retry="load" />

      <template v-else>
        <section class="personal-ai-group" aria-labelledby="personal-ai-title">

          <div v-if="providers.length === 0" class="personal-ai-empty personal-ai-empty--inline">
            <span class="personal-ai-empty__mark" aria-hidden="true"><AppIcon name="spark" /></span>
            <div>
              <h4>还没有配置模型</h4>
              <p>添加一个 OpenAI 兼容服务。对话模型让教练、出题和评分工作；向量模型让知识库能按语义检索。</p>
            </div>
          </div>

          <div v-else class="personal-ai-list">
            <article v-for="provider in sortedProviders" :key="provider.id" class="personal-ai-provider">
              <div class="personal-ai-provider__main">
                <span
                  class="ai-status-dot"
                  :class="{ 'is-on': provider.enabled }"
                  :title="provider.enabled ? '已启用' : '已停用'"
                  aria-hidden="true"
                ></span>
                <div class="personal-ai-provider__name">
                  <h3>{{ provider.name }}</h3>
                  <span v-if="provider.kind === 'embedding'" class="personal-ai-provider__tag">嵌入</span>
                </div>
                <span class="personal-ai-provider__model">{{ provider.modelId }}</span>
              </div>
              <label class="personal-ai-provider__priority">
                <span>优先级</span>
                <CrumbNumber
                  :model-value="provider.priority"
                  :min="0"
                  :max="10000"
                  :step="1"
                  :disabled="Boolean(actionKey)"
                  label="优先级"
                  @update:model-value="updatePriority(provider, $event)"
                />
              </label>
              <div class="personal-ai-provider__actions">
                <DivButton class="button-secondary ai-provider-action" type="button" aria-label="编辑" title="编辑" @click="openEdit(provider)">
                  <AppIcon name="edit" />
                </DivButton>
                <DivButton
                  class="button-secondary ai-provider-action"
                  type="button"
                  :aria-label="provider.enabled ? '停用' : '启用'"
                  :title="provider.enabled ? '停用' : '启用'"
                  :disabled="Boolean(actionKey)"
                  @click="toggleEnabled(provider)"
                >
                  <AppIcon name="power" />
                </DivButton>
                <DivButton class="button-danger ai-provider-action" type="button" aria-label="删除" title="删除" :disabled="Boolean(actionKey)" @click="deleteTarget = provider">
                  <AppIcon name="trash" />
                </DivButton>
              </div>
            </article>
          </div>
        </section>

      </template>

      <AiMemoryPanel />


      <AiQuotaPanel :providers="providers" @saved="load" />

      <ErrorNotice v-if="operationError" :error="operationError" :show-retry="false" />

      <section v-if="deleteTarget" class="alert alert-warning" role="alertdialog" aria-labelledby="delete-provider-title">
        <strong id="delete-provider-title">删除 {{ deleteTarget.name }}？</strong>
        <p>删除后该提供商配置和密钥会从当前账号移除，其他备用提供商不受影响。</p>
        <div class="button-row">
          <DivButton class="button-danger" type="button" :disabled="Boolean(actionKey)" @click="confirmDelete">
            {{ actionKey?.startsWith('delete:') ? '正在删除…' : '确认删除' }}
          </DivButton>
          <DivButton class="button-secondary" type="button" :disabled="Boolean(actionKey)" @click="deleteTarget = null">取消</DivButton>
        </div>
      </section>
    </div>


    <div v-if="formOpen" class="dialog-backdrop" @click.self="closeForm">
      <section class="dialog-card ai-provider-dialog" role="dialog" aria-modal="true" aria-label="AI 提供商配置">
        <AiProviderForm
          compact
          :provider="editingProvider"
          :default-kind="formKind"
          :saving="saving"
          :error="saveError"
          :can-fetch-models="true"
          :model-options="formModels"
          :model-loading="formModelsLoading"
          :model-error="formModelError"
          :test-loading="formTestLoading"
          :test-result="formTestResult"
          @create="handleCreate"
          @update="handleUpdate"
          @cancel="closeForm"
          @fetch-models="loadFormModels"
          @test="testFormProvider"
        />
      </section>
    </div>
  </section>
</template>
