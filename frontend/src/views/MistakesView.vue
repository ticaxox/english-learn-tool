<script setup lang="ts">
/**
 * /memory/mistakes — real word-level mistakes from the memory domain.
 *
 * Deliberately separate from any future AI practice mistakes: the source module
 * is displayed so the two can never be conflated. Restore calls the server and
 * uses the server's recomputed next appearance.
 */
import { computed, onMounted, ref } from 'vue'
import ErrorNotice from '../components/ErrorNotice.vue'
import LoadingState from '../components/LoadingState.vue'
import ContractGate from '../components/ContractGate.vue'
import { fetchMistakes, restoreWord, setMistakePriority } from '../api/learning'
import { isContractFrozen } from '../api/contract-adapter'
import {
  MEMORY_MODULE_LABELS,
  type LearnedWordState,
  type MistakeEntry,
  type PagedMistakes,
} from '../types/learning'
import '../learning.css'

const PAGE_SIZE = 20

const frozen = computed(() => isContractFrozen())
const data = ref<PagedMistakes | null>(null)
const loading = ref(false)
const error = ref<unknown>(null)
const restoring = ref<string | null>(null)
const restored = ref<LearnedWordState | null>(null)
const restoreError = ref<unknown>(null)
const offset = ref(0)
const prioritising = ref<string | null>(null)
const priorityError = ref<unknown>(null)

const page = computed(() => Math.floor(offset.value / PAGE_SIZE) + 1)
const totalPages = computed(() => (data.value ? Math.max(1, Math.ceil(data.value.total / PAGE_SIZE)) : 1))
const canPrev = computed(() => offset.value > 0)
const canNext = computed(() => (data.value ? offset.value + PAGE_SIZE < data.value.total : false))

/**
 * A refetch (after a priority toggle, or a page change) keeps the current rows
 * on screen and only disables the controls; dropping to the loading state would
 * blank the table and lose the learner's place for a one-row change.
 */
async function load(nextOffset = offset.value): Promise<void> {
  if (!frozen.value) {
    return
  }
  const isFirstLoad = data.value === null
  offset.value = nextOffset
  loading.value = true
  if (isFirstLoad) {
    error.value = null
  }
  try {
    data.value = await fetchMistakes({ offset: nextOffset, limit: PAGE_SIZE })
    error.value = null
  } catch (requestError) {
    if (isFirstLoad) {
      data.value = null
    }
    error.value = requestError
  } finally {
    loading.value = false
  }
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

/**
 * Toggle priority review. The request goes to the server, and the row keeps its
 * previous flag until a reload confirms the change: ordering and the flag are
 * server state, so the UI must not re-sort or re-label a row on its own.
 */
async function togglePriority(entry: MistakeEntry): Promise<void> {
  if (prioritising.value) {
    return
  }
  prioritising.value = entry.stateId
  priorityError.value = null
  try {
    await setMistakePriority(entry.stateId, { priorityReview: !entry.priorityReview })
    await load(offset.value)
  } catch (requestError) {
    priorityError.value = requestError
  } finally {
    prioritising.value = null
  }
}

onMounted(() => {
  void load(0)
})
</script>

<template>
  <article class="mistakes-page">
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

    <section v-else-if="error" class="panel">
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
                <th scope="col">来源模块</th>
                <th scope="col">最近错误</th>
                <th scope="col">次数</th>
                <th scope="col">重点复习</th>
                <th scope="col">操作</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="entry in data.items" :key="entry.stateId">
                <th scope="row">{{ entry.headword }}</th>
                <td>{{ entry.definition }}</td>
                <td>{{ MEMORY_MODULE_LABELS[entry.module] }}</td>
                <td>{{ entry.lastMistakeAt ?? '—' }}</td>
                <td>{{ entry.mistakeCount }}</td>
                <td>
                  <button
                    class="link-button"
                    type="button"
                    :disabled="prioritising === entry.stateId"
                    :aria-pressed="entry.priorityReview"
                    @click="togglePriority(entry)"
                  >
                    {{ entry.priorityReview ? '已标记重点' : '标为重点' }}
                  </button>
                  <span v-if="prioritising === entry.stateId" class="field-hint">更新中…</span>
                </td>
                <td>
                  <button
                    class="button-secondary button-small"
                    typetype="button"
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
          <button class="button-secondary button-small" typetype="button" :disabled="!canPrev || loading" @click="load(offset - PAGE_SIZE)">
            上一页
          </button>
          <span>第 {{ page }} / {{ totalPages }} 页 · 共 {{ data.total }} 条</span>
          <button class="button-secondary button-small" typetype="button" :disabled="!canNext || loading" @click="load(offset + PAGE_SIZE)">
            下一页
          </button>
        </nav>
      </template>

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
