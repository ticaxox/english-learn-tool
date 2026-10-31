<script setup lang="ts">
/**
 * /memory/mistakes — real word-level mistakes from the memory domain.
 *
 * The endpoint uses cursor pagination and does not expose the originating
 * module, so the page labels these rows explicitly as memory-training mistakes
 * instead of inventing a module name. Restore calls the server and uses the
 * server's recomputed next appearance.
 */
import { computed, onMounted, ref } from 'vue'
import ErrorNotice from '../components/ErrorNotice.vue'
import LoadingState from '../components/LoadingState.vue'
import ContractGate from '../components/ContractGate.vue'
import { fetchMistakes, restoreWord, setMistakePriority } from '../api/learning'
import { isContractFrozen } from '../api/contract-adapter'
import {
  type LearnedWordState,
  type MistakeEntry,
  type PagedMistakes,
  type WordStateStatus,
} from '../types/learning'
import '../learning.css'

const PAGE_SIZE = 50
const STATUS_LABELS: Record<WordStateStatus, string> = {
  new: '新词',
  learning: '学习中',
  review: '复习中',
  relearning: '重新学习',
  mastered: '已掌握',
  suspended: '已暂停',
}

const frozen = computed(() => isContractFrozen())
const data = ref<PagedMistakes | null>(null)
const loading = ref(false)
const error = ref<unknown>(null)
const restoring = ref<string | null>(null)
const restored = ref<LearnedWordState | null>(null)
const restoreError = ref<unknown>(null)
const currentCursor = ref<string | null>(null)
const cursorHistory = ref<Array<string | null>>([])
const prioritising = ref<string | null>(null)
const priorityError = ref<unknown>(null)

const page = computed(() => cursorHistory.value.length + 1)
const canPrev = computed(() => cursorHistory.value.length > 0)

function formatMistakeTime(value: string | null): string {
  if (!value) return '—'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return '—'
  return new Intl.DateTimeFormat('zh-CN', {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  }).format(date)
}

async function load(cursor: string | null = currentCursor.value): Promise<void> {
  if (!frozen.value) return
  const isFirstLoad = data.value === null
  currentCursor.value = cursor
  loading.value = true
  if (isFirstLoad) error.value = null
  try {
    data.value = await fetchMistakes({ cursor, limit: PAGE_SIZE })
    error.value = null
  } catch (requestError) {
    if (isFirstLoad) data.value = null
    error.value = requestError
  } finally {
    loading.value = false
  }
}

async function nextPage(): Promise<void> {
  if (!data.value?.nextCursor) return
  cursorHistory.value.push(currentCursor.value)
  await load(data.value.nextCursor)
}

async function previousPage(): Promise<void> {
  const previous = cursorHistory.value.pop()
  await load(previous ?? null)
}

async function restore(entry: MistakeEntry): Promise<void> {
  restoring.value = entry.stateId
  restoreError.value = null
  restored.value = null
  try {
    restored.value = await restoreWord(entry.stateId)
  } catch (requestError) {
    restoreError.value = requestError
  } finally {
    restoring.value = null
  }
}

async function togglePriority(entry: MistakeEntry): Promise<void> {
  if (prioritising.value) return
  prioritising.value = entry.entryId
  priorityError.value = null
  try {
    await setMistakePriority(entry.entryId, { priorityReview: !entry.priorityReview })
    await load()
  } catch (requestError) {
    priorityError.value = requestError
  } finally {
    prioritising.value = null
  }
}

onMounted(() => {
  void load(null)
})
</script>

<template>
  <article class="mistakes-page">
    <RouterLink class="immersive-back" to="/challenges">← 学习中心</RouterLink>

    <header class="page-header">
      <div>
        <p class="eyebrow">错词本</p>
        <h1>需要再练的词</h1>
        <p class="lead">
          只列出背词训练中真实答错（Again）的词。未来 AI 练习的错题属于另一个数据源，不会混入这里。
        </p>
      </div>
    </header>

    <ContractGate v-if="!frozen" :endpoints="['GET /memory/mistakes', 'PATCH /memory/words/{state_id}/restore']" />

    <LoadingState v-else-if="loading && !data" label="正在读取错词…" />

    <section v-else-if="error && !data" class="panel">
      <ErrorNotice :error="error" retry-label="重新读取错词" @retry="load()" />
    </section>

    <template v-else-if="data">
      <section v-if="data.items.length === 0" class="panel">
        <h2>暂时没有错词</h2>
        <p>继续练习后，答错的词会自动出现在这里。</p>
      </section>

      <template v-else>
        <section class="panel">
          <table class="mistake-table">
            <caption class="visually-hidden">背词错词列表</caption>
            <thead>
              <tr>
                <th scope="col">单词</th>
                <th scope="col">释义</th>
                <th scope="col">来源 / 状态</th>
                <th scope="col">最近错误</th>
                <th scope="col">次数</th>
                <th scope="col">重点复习</th>
                <th scope="col">操作</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="entry in data.items" :key="entry.stateId">
                <th scope="row" data-label="单词">{{ entry.headword }}</th>
                <td data-label="释义">{{ entry.definition ?? '—' }}</td>
                <td data-label="来源 / 状态">背词训练 · {{ STATUS_LABELS[entry.status] }}</td>
                <td data-label="最近错误">{{ formatMistakeTime(entry.lastMistakeAt) }}</td>
                <td data-label="次数">{{ entry.mistakeCount }}</td>
                <td data-label="重点复习">
                  <button
                    class="link-button"
                    type="button"
                    :disabled="prioritising === entry.entryId"
                    :aria-pressed="entry.priorityReview"
                    @click="togglePriority(entry)"
                  >
                    {{ entry.priorityReview ? '已标记重点' : '标为重点' }}
                  </button>
                  <span v-if="prioritising === entry.entryId" class="field-hint">更新中…</span>
                </td>
                <td data-label="操作">
                  <button
                    class="button-secondary button-small"
                    type="button"
                    :disabled="restoring === entry.stateId"
                    @click="restore(entry)"
                  >
                    {{ restoring === entry.stateId ? '恢复中…' : '恢复复习' }}
                  </button>
                </td>
              </tr>
            </tbody>
          </table>
        </section>

        <nav class="pager" aria-label="错词分页">
          <button class="button-secondary button-small" type="button" :disabled="!canPrev || loading" @click="previousPage">
            上一页
          </button>
          <span>第 {{ page }} 页 · 本页 {{ data.items.length }} 条</span>
          <button class="button-secondary button-small" type="button" :disabled="!data.hasMore || loading" @click="nextPage">
            下一页
          </button>
        </nav>
      </template>

      <ErrorNotice v-if="error" :error="error" retry-label="重新读取错词" @retry="load()" />
      <div v-if="restored" class="alert alert-success" role="status">
        <strong>{{ restored.headword }} 已恢复复习</strong>
        <p v-if="restored.nextDueAt">服务端计算的下一复习时间：{{ restored.nextDueAt }}</p>
        <p v-else class="inline-note">服务端尚未给出下一次复习时间，请刷新查看。</p>
      </div>
      <ErrorNotice v-if="restoreError" :error="restoreError" :show-retry="false" retry-label="重试" @retry="() => {}" />
      <ErrorNotice v-if="priorityError" :error="priorityError" retry-label="重新读取错词" @retry="load()" />
    </template>
  </article>
</template>
