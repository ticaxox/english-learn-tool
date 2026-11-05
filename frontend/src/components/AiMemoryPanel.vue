<script setup lang="ts">
/**
 * AI memory is one document, not a list of records.
 *
 * The settings page only shows a compact row; the document itself opens in a
 * floating dialog for reading and editing. The coach reads it before answering.
 */
import { computed, onMounted, ref } from 'vue'
import ErrorNotice from './ErrorNotice.vue'
import LoadingState from './LoadingState.vue'
import {
  getAiMemoryDocument,
  saveAiMemoryDocument,
  type AiMemoryDocument,
} from '../api/ai-memory'
import { useToast } from '../composables/useToast'

const LIMIT = 6000

const document = ref<AiMemoryDocument>({ content: '', updatedAt: null })
const draft = ref('')
const open = ref(false)
const loading = ref(false)
const loadError = ref<unknown>(null)
const saveError = ref<unknown>(null)
const saving = ref(false)
const toast = useToast()

const dirty = computed(() => draft.value !== document.value.content)
const updatedLabel = computed(() => {
  if (!document.value.updatedAt) return '还没有自动记录'
  const date = new Date(document.value.updatedAt)
  if (Number.isNaN(date.getTime())) return '最近已更新'
  return `最近更新 ${new Intl.DateTimeFormat('zh-CN', {
    month: 'numeric',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  }).format(date)}`
})

async function load(): Promise<void> {
  loading.value = true
  loadError.value = null
  try {
    document.value = await getAiMemoryDocument()
    draft.value = document.value.content
  } catch (error) {
    loadError.value = error
  } finally {
    loading.value = false
  }
}

function openDialog(): void {
  open.value = true
  void load()
}

function closeDialog(): void {
  open.value = false
  saveError.value = null
}

async function save(): Promise<void> {
  if (saving.value || !dirty.value) return
  saving.value = true
  saveError.value = null
  try {
    document.value = await saveAiMemoryDocument(draft.value)
    draft.value = document.value.content
    toast.success('记忆已保存', '教练会按这份文档回答。')
  } catch (error) {
    saveError.value = error
  } finally {
    saving.value = false
  }
}

onMounted(() => {
  void load()
})
</script>

<template>
  <section class="panel ai-memory-panel" aria-labelledby="ai-memory-title">
    <div class="ai-memory-row">
      <div class="ai-memory-row__copy">
        <h3 id="ai-memory-title">AI 记忆</h3>
        <p class="field-hint">教练回答前会读这份文档；点击右侧可以查看和修改。</p>
      </div>
      <span class="ai-memory-stamp">{{ updatedLabel }}</span>
      <DivButton class="button-secondary" type="button" @click="openDialog">查看 / 修改</DivButton>
    </div>
  </section>

  <div v-if="open" class="dialog-backdrop" @click.self="closeDialog">
    <section
      class="dialog-card ai-memory-dialog"
      role="dialog"
      aria-modal="true"
      aria-labelledby="ai-memory-dialog-title"
    >
      <header class="ai-memory-dialog__head">
        <div>
          <p class="eyebrow">AI 配置</p>
          <h2 id="ai-memory-dialog-title">AI 记忆</h2>
          <p class="ai-memory-stamp">{{ updatedLabel }}</p>
        </div>
        <DivButton class="button-secondary button-small" type="button" @click="closeDialog">关闭</DivButton>
      </header>

      <LoadingState v-if="loading && !draft" label="正在读取 AI 记忆…" />
      <ErrorNotice v-else-if="loadError" :error="loadError" retry-label="重新读取记忆" @retry="load" />

      <template v-else>
        <p class="field-hint">
          学习档案、做题结果和对话要点会自动写进来，也可以直接改写。用「保存记忆」提交整份文档。
        </p>
        <label class="visually-hidden" for="ai-memory-document">AI 记忆文档</label>
        <textarea
          id="ai-memory-document"
          v-model="draft"
          class="ai-memory-document"
          rows="12"
          :maxlength="LIMIT"
          placeholder="这里还是一张白纸。完成一轮练习、保存学习设置或和教练聊天后，这里会自动出现记录；也可以直接写下希望教练一直记住的内容。"
        ></textarea>

        <div class="ai-memory-actions">
          <span class="ai-memory-count">{{ draft.length }} / {{ LIMIT }}</span>
          <span v-if="dirty" class="ai-memory-dirty">有未保存的修改</span>
          <DivButton class="button" type="button" :disabled="saving || !dirty" @click="save">
            {{ saving ? '正在保存…' : '保存记忆' }}
          </DivButton>
        </div>

        <ErrorNotice v-if="saveError" :error="saveError" :show-retry="false" retry-label="重试" @retry="save" />
      </template>
    </section>
  </div>
</template>
