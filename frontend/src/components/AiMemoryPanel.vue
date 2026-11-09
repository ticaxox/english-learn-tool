<script setup lang="ts">
/**
 * Memories the coach keeps about the learner.
 *
 * Each row is a typed fact with its provenance, so the learner can see what the
 * coach remembers, add one, or forget it. Nothing accumulates silently.
 */
import { onMounted, ref } from 'vue'
import AppIcon from './AppIcon.vue'
import ErrorNotice from './ErrorNotice.vue'
import LoadingState from './LoadingState.vue'
import {
  COACH_MEMORY_KIND_LABELS,
  COACH_MEMORY_SOURCE_LABELS,
  createCoachMemory,
  deleteCoachMemory,
  listCoachMemories,
  type CoachMemory,
  type CoachMemoryKind,
} from '../api/coach-memories'

const KINDS: CoachMemoryKind[] = ['preference', 'goal', 'constraint', 'fact', 'note']

const memories = ref<CoachMemory[]>([])
const loading = ref(false)
const loadError = ref<unknown>(null)
const saveError = ref<unknown>(null)
const saving = ref(false)
const open = ref(false)

const draftKind = ref<CoachMemoryKind>('preference')
const draftContent = ref('')

async function load(): Promise<void> {
  loading.value = true
  loadError.value = null
  try {
    memories.value = await listCoachMemories()
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
  draftContent.value = ''
}

async function add(): Promise<void> {
  const content = draftContent.value.trim()
  if (!content || saving.value) return
  saving.value = true
  saveError.value = null
  try {
    await createCoachMemory({ kind: draftKind.value, content })
    draftContent.value = ''
    await load()
  } catch (error) {
    saveError.value = error
  } finally {
    saving.value = false
  }
}

async function forget(memory: CoachMemory): Promise<void> {
  if (!window.confirm(`让教练忘记“${memory.content}”？`)) return
  saveError.value = null
  try {
    await deleteCoachMemory(memory.id)
    memories.value = memories.value.filter((item) => item.id !== memory.id)
  } catch (error) {
    saveError.value = error
  }
}

function updatedLabel(memory: CoachMemory): string {
  const date = new Date(memory.updatedAt)
  if (Number.isNaN(date.getTime())) return ''
  return new Intl.DateTimeFormat('zh-CN', { month: 'numeric', day: 'numeric' }).format(date)
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
      </div>
      <span class="ai-memory-stamp">{{ memories.length }} 条</span>
      <DivButton class="button-secondary" type="button" @click="openDialog">管理</DivButton>
    </div>

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
            <h2 id="ai-memory-dialog-title">教练记住的事</h2>
            <p class="field-hint">教练回答前会按相关性读取这些内容；你可以随时让它忘记。</p>
          </div>
          <DivButton class="workspace-icon-button" type="button" aria-label="关闭" @click="closeDialog">
            <AppIcon name="close" />
          </DivButton>
        </header>

        <form class="ai-memory-add" @submit.prevent="add">
          <label class="visually-hidden" for="ai-memory-kind">类型</label>
          <select id="ai-memory-kind" v-model="draftKind">
            <option v-for="kind in KINDS" :key="kind" :value="kind">
              {{ COACH_MEMORY_KIND_LABELS[kind] }}
            </option>
          </select>
          <label class="visually-hidden" for="ai-memory-content">内容</label>
          <input
            id="ai-memory-content"
            v-model="draftContent"
            maxlength="500"
            placeholder="例如：我习惯早上背单词"
            :disabled="saving"
          />
          <DivButton type="submit" :disabled="saving || !draftContent.trim()">
            {{ saving ? '正在保存…' : '记住' }}
          </DivButton>
        </form>

        <ErrorNotice v-if="loadError" :error="loadError" retry-label="重新读取记忆" @retry="load" />
        <ErrorNotice v-if="saveError" :error="saveError" :show-retry="false" />
        <LoadingState v-if="loading && memories.length === 0" label="正在读取记忆…" />

        <ul v-else-if="memories.length" class="ai-memory-list" aria-label="教练记忆">
          <li v-for="memory in memories" :key="memory.id" class="ai-memory-item">
            <span class="ai-memory-item__kind">{{ COACH_MEMORY_KIND_LABELS[memory.kind] }}</span>
            <p class="ai-memory-item__content">{{ memory.content }}</p>
            <small class="ai-memory-item__meta">
              {{ COACH_MEMORY_SOURCE_LABELS[memory.source] }} · {{ updatedLabel(memory) }}
            </small>
            <DivButton class="button-secondary button-small" type="button" @click="forget(memory)">
              忘记
            </DivButton>
          </li>
        </ul>
        <p v-else-if="!loading" class="field-hint">
          教练还没有记住任何事。对话里说「记住…」，或在这里添加。
        </p>
      </section>
    </div>
  </section>
</template>
