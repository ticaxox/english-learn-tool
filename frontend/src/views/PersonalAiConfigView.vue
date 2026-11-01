<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
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
  type ProviderPatchInput,
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
const globalTimeout = ref(120)
const globalSaving = ref(false)

const sortedProviders = computed(() => [...providers.value].sort((left, right) => {
  if (left.priority !== right.priority) return left.priority - right.priority
  return left.name.localeCompare(right.name, 'zh-CN')
}))

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

function openCreate(): void {
  editingProvider.value = null
  saveError.value = null
  resetFormSideState()
  formOpen.value = true
}

function openEdit(provider: AiProvider): void {
  editingProvider.value = provider
  saveError.value = null
  resetFormSideState()
  formOpen.value = true
}

async function loadFormModels(): Promise<void> {
  const provider = editingProvider.value
  if (!provider || formModelsLoading.value) return
  formModelsLoading.value = true
  formModelError.value = null
  try {
    const result = await fetchPersonalProviderModels(provider.id)
    formModels.value = result.success ? result.models : []
  } catch (error) {
    formModels.value = []
    formModelError.value = error
  } finally {
    formModelsLoading.value = false
  }
}

async function testFormProvider(): Promise<void> {
  const provider = editingProvider.value
  if (!provider || formTestLoading.value) return
  formTestLoading.value = true
  formTestResult.value = null
  try {
    const result = await testPersonalProvider(provider.id)
    formTestResult.value = result
    if (result.success) {
      toast.success('连接成功', result.latencyMs === null ? undefined : `响应耗时 ${result.latencyMs} ms。`)
    } else {
      toast.error('连接未通过', '检查接口地址、模型 ID 和 API Key 后重试。')
    }
    await load()
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

watch(providers, (list) => {
  if (list.length > 0) globalTimeout.value = list[0].timeoutSeconds
}, { immediate: true })

async function saveGlobalTimeout(): Promise<void> {
  if (globalSaving.value || providers.value.length === 0) return
  const value = Number(globalTimeout.value)
  if (!Number.isInteger(value) || value < 1 || value > 120) {
    toast.error('超时必须是 1–120 秒')
    return
  }
  globalSaving.value = true
  try {
    for (const provider of providers.value) {
      await updatePersonalProvider(provider.id, { timeoutSeconds: value })
    }
    await load()
    toast.success('已应用到所有提供商', `生成超时 ${value} 秒`)
  } catch (error) {
    operationError.value = error
  } finally {
    globalSaving.value = false
  }
}

function updatePriority(provider: AiProvider, event: Event): void {
  const value = Number((event.target as HTMLInputElement).value)
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
    <div class="personal-ai-main">
      <div class="personal-ai-toolbar">
        <div>
          <h2 id="personal-ai-title">你的 AI 提供商</h2>
          <p class="field-hint">只显示当前账号自己的配置。数字越小越先用，失败时按顺序换下一个。</p>
        </div>
        <button v-if="providers.length > 0" class="button" type="button" @click="openCreate">添加 AI 提供商</button>
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
          <div class="personal-ai-provider__main">
            <span
              class="ai-status-dot"
              :class="{ 'is-on': provider.enabled }"
              :title="provider.enabled ? '已启用' : '已停用'"
              aria-hidden="true"
            ></span>
            <h3>{{ provider.name }}</h3>
            <span class="personal-ai-provider__model">{{ provider.modelId }}</span>
            <span class="personal-ai-provider__url">{{ provider.baseUrl }}</span>
          </div>
          <label class="personal-ai-provider__priority">
            <span>优先级</span>
            <input
              type="number"
              min="0"
              max="10000"
              step="1"
              :value="provider.priority"
              :disabled="Boolean(actionKey)"
              @change="updatePriority(provider, $event)"
            />
          </label>
          <div class="personal-ai-provider__actions">
            <button class="button-secondary" type="button" @click="openEdit(provider)">编辑</button>
            <button class="button-secondary" type="button" :disabled="Boolean(actionKey)" @click="toggleEnabled(provider)">
              {{ provider.enabled ? '停用' : '启用' }}
            </button>
            <button class="button-danger" type="button" :disabled="Boolean(actionKey)" @click="deleteTarget = provider">删除</button>
          </div>
        </article>
      </div>

      <section class="panel ai-global-config" aria-labelledby="ai-global-config-title">
        <div>
          <h3 id="ai-global-config-title">其他 API 配置</h3>
          <p class="field-hint">对所有提供商生效，不绑定某一个。</p>
        </div>
        <div class="ai-global-config__row">
          <div class="field">
            <label for="global-timeout">生成超时（秒，1–120）</label>
            <input id="global-timeout" v-model.number="globalTimeout" type="number" min="1" max="120" step="1" />
          </div>
          <button class="button" type="button" :disabled="globalSaving || providers.length === 0" @click="saveGlobalTimeout">
            {{ globalSaving ? '正在应用…' : '应用到所有提供商' }}
          </button>
        </div>
      </section>

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

    <aside class="personal-ai-aside" aria-label="AI 提供商配置说明">
      <div class="personal-ai-guide">
        <div>
          <p class="eyebrow">配置说明</p>
          <h3>配置后就能用</h3>
          <ul class="personal-ai-guide__list">
            <li>AI 教练对话与学习计划调整</li>
            <li>AI 练习生成、评分与错题解析</li>
            <li>每日闯关的题目生成</li>
          </ul>
        </div>
        <div>
          <h3>密钥怎么保存</h3>
          <p class="field-hint">
            密钥加密保存，列表只显示掩码；已保存的 Key 不会回显，需要更换时在编辑弹窗里输入新 Key。
          </p>
        </div>
        <div>
          <h3>建议顺序</h3>
          <p class="field-hint">先保存配置，再在弹窗里测试连接，最后获取模型列表选择模型 ID。</p>
        </div>
      </div>
    </aside>

    <div v-if="formOpen" class="dialog-backdrop" @click.self="closeForm">
      <section class="dialog-card ai-provider-dialog" role="dialog" aria-modal="true" aria-label="AI 提供商配置">
        <AiProviderForm
          compact
          :provider="editingProvider"
          :saving="saving"
          :error="saveError"
          :can-fetch-models="Boolean(editingProvider)"
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
