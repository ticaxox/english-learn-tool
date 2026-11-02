<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import ErrorNotice from '../components/ErrorNotice.vue'
import LoadingState from '../components/LoadingState.vue'
import { apiClient } from '../api/client'
import {
  getPrompt,
  listPrompts,
  updatePrompt,
  PROMPT_LABELS,
  type PromptDetail,
  type PromptKey,
  type PromptSummary,
} from '../api/ai-admin'
import '../ai-admin.css'

const prompts = ref<PromptSummary[]>([])
const selectedKey = ref<PromptKey | null>(null)
const detail = ref<PromptDetail | null>(null)
const loadingList = ref(false)
const loadingDetail = ref(false)
const saving = ref(false)
const listError = ref<unknown>(null)
const detailError = ref<unknown>(null)
const saveError = ref<unknown>(null)
const saved = ref(false)
const lastRequestId = ref<string | null>(null)
const fieldErrors = reactive<Record<string, string>>({})

const draft = reactive({ name: '', summary: '', template: '' })

const selectedLabel = computed(() => (selectedKey.value ? PROMPT_LABELS[selectedKey.value] : ''))

function clearFieldErrors(): void {
  Object.keys(fieldErrors).forEach((key) => delete fieldErrors[key])
}

function applyDetail(value: PromptDetail): void {
  detail.value = value
  draft.name = value.name
  draft.summary = value.summary
  draft.template = value.template
  clearFieldErrors()
}

async function loadList(): Promise<void> {
  loadingList.value = true
  listError.value = null
  try {
    prompts.value = await listPrompts()
    if (!selectedKey.value && prompts.value.length > 0) {
      await selectPrompt(prompts.value[0].key)
    }
  } catch (error) {
    prompts.value = []
    listError.value = error
  } finally {
    loadingList.value = false
  }
}

async function selectPrompt(key: PromptKey): Promise<void> {
  selectedKey.value = key
  loadingDetail.value = true
  detailError.value = null
  saveError.value = null
  saved.value = false
  try {
    applyDetail(await getPrompt(key))
  } catch (error) {
    detail.value = null
    detailError.value = error
  } finally {
    loadingDetail.value = false
  }
}

function validate(): boolean {
  clearFieldErrors()
  if (!draft.name.trim()) fieldErrors.name = '名称不能为空。'
  if (draft.name.trim().length > 100) fieldErrors.name = '名称最多 100 个字符。'
  if (!draft.summary.trim()) fieldErrors.summary = '用途摘要不能为空。'
  if (draft.summary.trim().length > 500) fieldErrors.summary = '用途摘要最多 500 个字符。'
  if (!draft.template.trim()) fieldErrors.template = '提示词模板不能为空。'
  if (draft.template.length > 100000) fieldErrors.template = '提示词模板最多 100000 个字符。'
  return Object.keys(fieldErrors).length === 0
}

async function save(): Promise<void> {
  if (!selectedKey.value || !validate()) return
  saving.value = true
  saveError.value = null
  saved.value = false
  try {
    const updated = await updatePrompt(selectedKey.value, {
      name: draft.name.trim(),
      summary: draft.summary.trim(),
      template: draft.template,
    })
    applyDetail(updated)
    const index = prompts.value.findIndex((item) => item.key === updated.key)
    if (index >= 0) {
      prompts.value[index] = {
        key: updated.key,
        name: updated.name,
        summary: updated.summary,
        updatedAt: updated.updatedAt,
      }
    }
    lastRequestId.value = apiClient.getLastRequestId()
    saved.value = true
  } catch (error) {
    saveError.value = error
    lastRequestId.value = apiClient.getLastRequestId()
  } finally {
    saving.value = false
  }
}

onMounted(() => {
  void loadList()
})
</script>

<template>
  <article class="ai-admin-page prompts-page">
    <header class="ai-admin-hero">
      <div>
        <p class="eyebrow">管理员 · AI 配置</p>
        <h1>AI 提示词</h1>
        <p class="lead">按功能键读取并覆盖提示词。保存只影响后续 AI 任务，不会展示用户答案、密钥或教练正文。</p>
      </div>
      <DivButton class="button-secondary" type="button" :disabled="loadingList" @click="loadList">刷新列表</DivButton>
    </header>

    <LoadingState v-if="loadingList" label="正在读取提示词列表…" />

    <section v-else-if="listError" class="panel">
      <ErrorNotice :error="listError" retry-label="重新读取提示词" @retry="loadList" />
    </section>

    <section v-else-if="prompts.length === 0" class="panel empty-state">
      <h2>没有可编辑的提示词</h2>
      <p>服务端尚未返回提示词清单。本页不会生成静态模板。</p>
    </section>

    <div v-else class="prompt-layout">
      <aside class="panel prompt-list" aria-label="提示词清单">
        <h2>功能键</h2>
        <DivButton
          v-for="item in prompts"
          :key="item.key"
          class="prompt-list__item"
          :class="{ 'prompt-list__item--active': selectedKey === item.key }"
          type="button"
          @click="selectPrompt(item.key)"
        >
          <strong>{{ item.name }}</strong>
          <span>{{ PROMPT_LABELS[item.key] }} · <code>{{ item.key }}</code></span>
          <small>更新于 {{ item.updatedAt }}</small>
        </DivButton>
      </aside>

      <section class="panel prompt-editor">
        <LoadingState v-if="loadingDetail" label="正在读取提示词详情…" />

        <section v-else-if="detailError" class="prompt-editor__error">
          <ErrorNotice :error="detailError" retry-label="重新读取提示词" @retry="() => selectedKey && selectPrompt(selectedKey)" />
        </section>

        <template v-else-if="detail && selectedKey">
          <div class="section-heading">
            <div>
              <p class="eyebrow">{{ selectedLabel }} · <code>{{ selectedKey }}</code></p>
              <h2>编辑提示词</h2>
              <p class="inline-note">最近保存：{{ detail.updatedAt }}</p>
            </div>
          </div>

          <form class="ai-form" novalidate @submit.prevent="save">
            <div class="field">
              <label for="prompt-name">名称</label>
              <input id="prompt-name" v-model="draft.name" type="text" maxlength="100" :aria-invalid="Boolean(fieldErrors.name)" />
              <p v-if="fieldErrors.name" class="field-error" role="alert">{{ fieldErrors.name }}</p>
            </div>

            <div class="field">
              <label for="prompt-summary">用途摘要</label>
              <input id="prompt-summary" v-model="draft.summary" type="text" maxlength="500" :aria-invalid="Boolean(fieldErrors.summary)" />
              <p v-if="fieldErrors.summary" class="field-error" role="alert">{{ fieldErrors.summary }}</p>
            </div>

            <div class="field">
              <label for="prompt-template">提示词模板</label>
              <textarea id="prompt-template" v-model="draft.template" class="prompt-template" spellcheck="false" :aria-invalid="Boolean(fieldErrors.template)"></textarea>
              <p v-if="fieldErrors.template" class="field-error" role="alert">{{ fieldErrors.template }}</p>
              <p class="field-hint">直接覆盖保存；模板变量与 JSON 结构由后端任务负责解释。</p>
            </div>

            <ErrorNotice v-if="saveError" :error="saveError" :show-retry="false" retry-label="重新保存" @retry="save" />
            <div v-if="lastRequestId" class="inline-note">Request ID：<code>{{ lastRequestId }}</code></div>

            <div class="button-row">
              <DivButton class="button" type="submit" :disabled="saving">{{ saving ? '正在保存…' : '覆盖保存' }}</DivButton>
              <span v-if="saved" class="status-badge status-badge--success" role="status">已保存</span>
            </div>
          </form>
        </template>
      </section>
    </div>
  </article>
</template>