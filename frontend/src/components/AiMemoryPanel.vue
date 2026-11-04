<script setup lang="ts">
/**
 * AI memory management.
 *
 * The coach reads these notes before every answer, so the learner can inspect
 * what is remembered, add something explicitly, edit or forget a note, and
 * clear everything the product recorded on its own.
 */
import { computed, onMounted, ref } from 'vue'
import ErrorNotice from './ErrorNotice.vue'
import LoadingState from './LoadingState.vue'
import {
  clearAutoAiMemories,
  createAiMemory,
  deleteAiMemory,
  listAiMemories,
  updateAiMemory,
  type AiMemory,
  type AiMemoryKind,
  type AiMemoryList,
} from '../api/ai-memory'
import { useToast } from '../composables/useToast'

const KINDS: Array<{ key: AiMemoryKind; label: string }> = [
  { key: 'profile', label: '用户信息' },
  { key: 'practice', label: '做题情况' },
  { key: 'chat', label: '聊天要点' },
  { key: 'preference', label: '习惯偏好' },
  { key: 'custom', label: '指定记忆' },
]

const memoryList = ref<AiMemoryList>({ items: [], counts: {} })
const loading = ref(false)
const loadError = ref<unknown>(null)
const operationError = ref<unknown>(null)
const filter = ref<AiMemoryKind | 'all'>('all')
const draft = ref('')
const draftKind = ref<AiMemoryKind>('custom')
const saving = ref(false)
const editingId = ref<string | null>(null)
const editDraft = ref('')
const busyId = ref<string | null>(null)
const toast = useToast()

const visibleItems = computed(() => {
  if (filter.value === 'all') return memoryList.value.items
  return memoryList.value.items.filter((item) => item.kind === filter.value)
})

const autoCount = computed(() => memoryList.value.items.filter((item) => item.source === 'auto').length)

function kindLabel(kind: AiMemoryKind): string {
  return KINDS.find((option) => option.key === kind)?.label ?? kind
}

function countFor(kind: AiMemoryKind | 'all'): number {
  if (kind === 'all') {
    return Object.values(memoryList.value.counts).reduce((total, value) => total + value, 0)
  }
  return memoryList.value.counts[kind] ?? 0
}

function formatDate(value: string): string {
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return ''
  return new Intl.DateTimeFormat('zh-CN', { month: 'numeric', day: 'numeric' }).format(date)
}

async function load(): Promise<void> {
  loading.value = true
  loadError.value = null
  try {
    memoryList.value = await listAiMemories()
  } catch (error) {
    loadError.value = error
  } finally {
    loading.value = false
  }
}

async function addMemory(): Promise<void> {
  const content = draft.value.trim()
  if (!content || saving.value) return
  saving.value = true
  operationError.value = null
  try {
    await createAiMemory({ kind: draftKind.value, content })
    draft.value = ''
    await load()
    toast.success('已记住', 'AI 教练会在之后的回答里带上这条记忆。')
  } catch (error) {
    operationError.value = error
  } finally {
    saving.value = false
  }
}

function startEdit(memory: AiMemory): void {
  editingId.value = memory.id
  editDraft.value = memory.content
}

function cancelEdit(): void {
  editingId.value = null
  editDraft.value = ''
}

async function saveEdit(memory: AiMemory): Promise<void> {
  const content = editDraft.value.trim()
  if (!content || busyId.value) return
  busyId.value = memory.id
  operationError.value = null
  try {
    await updateAiMemory(memory.id, { content })
    cancelEdit()
    await load()
  } catch (error) {
    operationError.value = error
  } finally {
    busyId.value = null
  }
}

async function removeMemory(memory: AiMemory): Promise<void> {
  if (busyId.value) return
  busyId.value = memory.id
  operationError.value = null
  try {
    await deleteAiMemory(memory.id)
    await load()
    toast.push({ title: '这条记忆已删除', tone: 'info' })
  } catch (error) {
    operationError.value = error
  } finally {
    busyId.value = null
  }
}

async function clearAuto(): Promise<void> {
  if (autoCount.value === 0 || busyId.value) return
  const confirmed = window.confirm('清空所有自动记录的记忆？你自己要求记住的内容会保留。')
  if (!confirmed) return
  busyId.value = 'clear'
  operationError.value = null
  try {
    const deleted = await clearAutoAiMemories()
    await load()
    toast.success('已清空自动记忆', `共删除 ${deleted} 条。`)
  } catch (error) {
    operationError.value = error
  } finally {
    busyId.value = null
  }
}

onMounted(() => {
  void load()
})
</script>

<template>
  <section class="panel ai-memory-panel" aria-labelledby="ai-memory-title">
    <header class="ai-memory-panel__head">
      <div>
        <h3 id="ai-memory-title">AI 记忆</h3>
        <p class="field-hint">教练回答前会读取这些记忆：你的学习目标、做题结果、聊天要点和偏好。</p>
      </div>
      <DivButton class="button-secondary button-small" type="button" :disabled="autoCount === 0 || busyId !== null" @click="clearAuto">
        清空自动记忆
      </DivButton>
    </header>

    <div class="ai-memory-filters" role="list" aria-label="记忆分类">
      <DivButton
        role="listitem"
        class="ai-memory-chip"
        :class="{ 'is-active': filter === 'all' }"
        :aria-pressed="filter === 'all'"
        type="button"
        @click="filter = 'all'"
      >
        全部 <span>{{ countFor('all') }}</span>
      </DivButton>
      <DivButton
        v-for="kind in KINDS"
        :key="kind.key"
        role="listitem"
        class="ai-memory-chip"
        :class="{ 'is-active': filter === kind.key }"
        :aria-pressed="filter === kind.key"
        type="button"
        @click="filter = kind.key"
      >
        {{ kind.label }} <span>{{ countFor(kind.key) }}</span>
      </DivButton>
    </div>

    <form class="ai-memory-form" @submit.prevent="addMemory">
      <label class="visually-hidden" for="ai-memory-draft">要记住的内容</label>
      <textarea
        id="ai-memory-draft"
        v-model="draft"
        rows="2"
        maxlength="500"
        placeholder="例如：我容易混淆 affect 和 effect，请多给我这类题。"
      ></textarea>
      <div class="ai-memory-form__actions">
        <label class="ai-memory-form__kind">
          <span>分类</span>
          <select v-model="draftKind">
            <option v-for="kind in KINDS" :key="kind.key" :value="kind.key">{{ kind.label }}</option>
          </select>
        </label>
        <DivButton class="button" type="submit" :disabled="saving || !draft.trim()">
          {{ saving ? '正在保存…' : '记住这条' }}
        </DivButton>
      </div>
    </form>

    <ErrorNotice v-if="operationError" :error="operationError" :show-retry="false" />

    <LoadingState v-if="loading && memoryList.items.length === 0" label="正在读取 AI 记忆…" />
    <ErrorNotice v-else-if="loadError" :error="loadError" retry-label="重新读取记忆" @retry="load" />

    <div v-else-if="visibleItems.length === 0" class="ai-memory-empty">
      <p>这里还没有记忆。完成一轮练习或让教练记住你的习惯后，会自动出现在这里。</p>
    </div>

    <div v-else role="list" class="ai-memory-list">
      <div v-for="memory in visibleItems" :key="memory.id" role="listitem" class="ai-memory-item">
        <div class="ai-memory-item__meta">
          <span class="ai-memory-kind" :class="`ai-memory-kind--${memory.kind}`">{{ kindLabel(memory.kind) }}</span>
          <span class="ai-memory-source">{{ memory.source === 'auto' ? '自动记录' : '我要求记住' }}</span>
          <span class="ai-memory-date">{{ formatDate(memory.updatedAt) }}</span>
        </div>

        <template v-if="editingId === memory.id">
          <textarea v-model="editDraft" rows="2" maxlength="500" aria-label="编辑记忆内容"></textarea>
          <div class="ai-memory-item__actions">
            <DivButton class="button-secondary button-small" type="button" :disabled="busyId !== null" @click="saveEdit(memory)">保存</DivButton>
            <DivButton class="button-secondary button-small" type="button" :disabled="busyId !== null" @click="cancelEdit">取消</DivButton>
          </div>
        </template>
        <template v-else>
          <p class="ai-memory-item__content">{{ memory.content }}</p>
          <div class="ai-memory-item__actions">
            <DivButton class="button-secondary button-small" type="button" :disabled="busyId !== null" @click="startEdit(memory)">编辑</DivButton>
            <DivButton class="button-secondary button-small" type="button" :disabled="busyId !== null" @click="removeMemory(memory)">删除</DivButton>
          </div>
        </template>
      </div>
    </div>
  </section>
</template>
