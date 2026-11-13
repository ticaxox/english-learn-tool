<script setup lang="ts">
/**
 * /practice/records and /practice/mistakes — one page, two scopes.
 *
 * A submitted practice is a record; a record that still holds a wrong answer is
 * a mistake. Both are read the same way: the list on the left, the whole record
 * on the right. The switch at the top only changes the filter the list is drawn
 * with, so nothing on the page has to be learned twice. The scope and the type
 * filter live in the URL, which makes a filtered view something you can link to.
 */
import { computed, nextTick, ref, watch } from 'vue'
import { RouterLink, useRoute } from 'vue-router'
import ErrorNotice from '../components/ErrorNotice.vue'
import LoadingState from '../components/LoadingState.vue'
import PracticeResultView from '../components/PracticeResultView.vue'
import TypeMark from '../components/TypeMark.vue'
import AppIcon from '../components/AppIcon.vue'
import DivButton from '../components/DivButton.vue'
import {
  deletePracticeRecords,
  getPracticeRecord,
  listPracticeMistakes,
  listPracticeRecords,
  PRACTICE_SOURCE_LABELS,
  PRACTICE_TYPE_LABELS,
  type PracticeRecordDetail,
  type PracticeRecordSummary,
  type PracticeSource,
  type PracticeType,
} from '../api/practice'
import '../practice.css'

const props = withDefaults(defineProps<{ onlyMistakes?: boolean }>(), { onlyMistakes: false })

const route = useRoute()

const practiceTypes: PracticeType[] = ['fill_blank', 'reading', 'translation', 'writing', 'conversation', 'mixed']
const practiceSources: PracticeSource[] = ['today_new', 'today_review', 'memory_mistakes', 'whole_book', 'difficulty']

/** The URL decides which half of the pair the page is showing. */
const scope = computed<'all' | 'mistakes'>(() =>
  route.name === 'practice-mistakes' || props.onlyMistakes ? 'mistakes' : 'all',
)
const isMistakes = computed(() => scope.value === 'mistakes')

const practiceType = computed<PracticeType | ''>(() => {
  const value = typeof route.query.type === 'string' ? route.query.type : ''
  return (practiceTypes as string[]).includes(value) ? (value as PracticeType) : ''
})
const source = ref<PracticeSource | ''>('')

const records = ref<PracticeRecordSummary[]>([])
const total = ref(0)
const offset = ref(0)
const limit = 12
const loading = ref(false)
const error = ref<unknown>(null)
const reloading = ref(false)

const activeId = ref<string | null>(null)
const detail = ref<PracticeRecordDetail | null>(null)
const detailLoading = ref(false)
const detailError = ref<unknown>(null)

const selected = ref<string[]>([])
const deleting = ref(false)
const deleteError = ref<unknown>(null)
let pendingDeleteKey: string | null = null
let pendingDeleteSignature = ''

const page = computed(() => Math.floor(offset.value / limit) + 1)
const pages = computed(() => Math.max(1, Math.ceil(total.value / limit)))
const canPrev = computed(() => offset.value > 0)
const canNext = computed(() => offset.value + limit < total.value)
const allSelected = computed(() => records.value.length > 0 && records.value.every((record) => selected.value.includes(record.id)))

function formatSubmittedAt(value: string | null): string {
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

function scoreText(record: PracticeRecordSummary): string {
  return record.score === null ? '—' : String(Math.round(record.score))
}

/** The same query, with the type replaced or removed. */
function viewQuery(type: PracticeType | ''): Record<string, string> {
  const query: Record<string, string> = {}
  if (type) query.type = type
  return query
}

function newKey(): string {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') return crypto.randomUUID()
  return `practice-delete-${Date.now()}-${Math.random().toString(16).slice(2)}`
}

async function load(): Promise<void> {
  loading.value = true
  error.value = null
  try {
    const pageData = isMistakes.value
      ? await listPracticeMistakes({ practiceType: practiceType.value || undefined, offset: offset.value, limit })
      : await listPracticeRecords({
          practiceType: practiceType.value || undefined,
          source: source.value || undefined,
          onlyMistakes: false,
          offset: offset.value,
          limit,
        })
    records.value = pageData.items
    total.value = pageData.total
    selected.value = selected.value.filter((id) => pageData.items.some((item) => item.id === id))
  } catch (requestError) {
    records.value = []
    total.value = 0
    error.value = requestError
  } finally {
    loading.value = false
  }
}

/** Load a page of records, then open the first one so the right pane is never blank. */
async function loadAndSelectFirst(): Promise<void> {
  await load()
  if (records.value.length === 0) {
    activeId.value = null
    detail.value = null
    return
  }
  const keep = records.value.find((record) => record.id === activeId.value)
  await openRecord(keep ?? records.value[0])
}

async function openRecord(record: PracticeRecordSummary, reveal = false): Promise<void> {
  activeId.value = record.id
  detailLoading.value = true
  detailError.value = null
  try {
    detail.value = await getPracticeRecord(record.id)
  } catch (requestError) {
    detail.value = null
    detailError.value = requestError
  } finally {
    detailLoading.value = false
  }
  // Only a click asks to be shown the result. Auto-opening the first record on
  // load must leave the page where it is, or the header scrolls away by itself.
  if (reveal) {
    await nextTick()
    document.querySelector<HTMLElement>('.records-detail')?.scrollIntoView({ block: 'nearest', behavior: 'smooth' })
  }
}

function toggleSelected(id: string): void {
  selected.value = selected.value.includes(id)
    ? selected.value.filter((item) => item !== id)
    : [...selected.value, id]
}

function toggleAll(): void {
  selected.value = allSelected.value ? [] : records.value.map((record) => record.id)
}

async function removeSelected(): Promise<void> {
  if (selected.value.length === 0 || deleting.value) return
  const confirmed = window.confirm(`确认删除选中的 ${selected.value.length} 条练习记录？删除后无法恢复。`)
  if (!confirmed) return
  const signature = selected.value.slice().sort().join(',')
  if (!pendingDeleteKey || pendingDeleteSignature !== signature) {
    pendingDeleteKey = newKey()
    pendingDeleteSignature = signature
  }
  deleting.value = true
  deleteError.value = null
  try {
    const removed = await deletePracticeRecords(selected.value, pendingDeleteKey)
    pendingDeleteKey = null
    pendingDeleteSignature = ''
    selected.value = []
    if (detail.value && removed.deletedIds.includes(detail.value.id)) {
      detail.value = null
      activeId.value = null
    }
    // The page may now be past the end of the list; step back before reloading.
    if (records.value.length <= removed.deletedIds.length && offset.value >= limit) {
      offset.value = Math.max(0, offset.value - limit)
    }
    await loadAndSelectFirst()
  } catch (requestError) {
    deleteError.value = requestError
  } finally {
    deleting.value = false
  }
}

function changePage(nextOffset: number): void {
  offset.value = Math.max(0, nextOffset)
  selected.value = []
  void loadAndSelectFirst()
}

async function refresh(): Promise<void> {
  if (reloading.value) return
  reloading.value = true
  try {
    await loadAndSelectFirst()
  } finally {
    reloading.value = false
  }
}

watch(
  () => [route.name, route.query.type],
  () => {
    offset.value = 0
    selected.value = []
    detail.value = null
    activeId.value = null
    // The source filter belongs to the records list only.
    if (isMistakes.value) source.value = ''
    void loadAndSelectFirst()
  },
)

watch(source, () => {
  offset.value = 0
  void loadAndSelectFirst()
})

void loadAndSelectFirst()
</script>

<template>
  <article class="practice-page practice-records-page workspace-page">
    <header class="workspace-page-header records-header">
      <div class="records-header__copy">
        <RouterLink class="records-back" to="/practice">
          <AppIcon name="arrow-left" /> AI 练习
        </RouterLink>
        <p class="workspace-kicker">复习巩固</p>
        <h1>{{ isMistakes ? '错题本' : '题目集' }}</h1>
        <p class="workspace-page-lead">
          {{ isMistakes
            ? '只列出还有错题的练习。左边挑一条，右边看当时那道题和解析。'
            : '左边挑一条记录，右边看题目、你的答案、正确答案和解析。' }}
        </p>
      </div>

      <nav class="records-scope" aria-label="在题目集和错题本之间切换">
        <RouterLink
          class="records-scope__link"
          :class="{ 'is-active': !isMistakes }"
          :aria-current="!isMistakes ? 'page' : undefined"
          :to="{ name: 'practice-records', query: viewQuery(practiceType) }"
        >题目集</RouterLink>
        <RouterLink
          class="records-scope__link"
          :class="{ 'is-active': isMistakes }"
          :aria-current="isMistakes ? 'page' : undefined"
          :to="{ name: 'practice-mistakes', query: viewQuery(practiceType) }"
        >错题本</RouterLink>
      </nav>
    </header>

    <section class="records-filters" aria-label="筛选记录">
      <nav class="records-type-tabs" aria-label="题型">
        <RouterLink
          class="records-type-tab"
          :class="{ 'is-active': practiceType === '' }"
          :to="{ name: route.name as string, query: viewQuery('') }"
        >全部</RouterLink>
        <RouterLink
          v-for="type in practiceTypes"
          :key="type"
          class="records-type-tab"
          :class="{ 'is-active': practiceType === type }"
          :to="{ name: route.name as string, query: viewQuery(type) }"
        >
          <TypeMark :type="type" :size="18" />
          <span>{{ PRACTICE_TYPE_LABELS[type] }}</span>
        </RouterLink>
      </nav>

      <div class="records-filters__tail">
        <label v-if="!isMistakes" class="records-source">
          <span>来源</span>
          <select v-model="source" aria-label="按来源筛选">
            <option value="">全部来源</option>
            <option v-for="item in practiceSources" :key="item" :value="item">{{ PRACTICE_SOURCE_LABELS[item] }}</option>
          </select>
        </label>
        <span class="records-tally">{{ total }} 条记录</span>
      </div>
    </section>

    <div class="records-shell">
      <section class="records-list" aria-label="记录列表">
        <header class="records-list__bar">
          <label class="records-check-all">
            <input type="checkbox" :checked="allSelected" :disabled="records.length === 0" @change="toggleAll" />
            <span>{{ selected.length ? `已选 ${selected.length}` : '全选' }}</span>
          </label>
          <DivButton
            class="button-danger button-small"
            type="button"
            :disabled="selected.length === 0 || deleting"
            @click="removeSelected"
          >
            {{ deleting ? '删除中…' : '删除' }}
          </DivButton>
        </header>

        <ErrorNotice v-if="deleteError" :error="deleteError" :show-retry="false" retry-label="重试" @retry="removeSelected" />

        <LoadingState v-if="loading && records.length === 0" label="正在读取记录…" />
        <ErrorNotice v-else-if="error" :error="error" retry-label="重新读取记录" @retry="refresh" />
        <p v-else-if="records.length === 0" class="records-empty">
          {{ isMistakes
            ? '还没有带着错题的练习记录。答错过的题目会自动出现在这里。'
            : '还没有符合条件的记录。完成一次练习并提交后，记录会出现在这里。' }}
        </p>

        <ul v-else class="records-rows" role="list">
          <li
            v-for="record in records"
            :key="record.id"
            class="records-row"
            :class="{ 'is-active': record.id === activeId, 'is-selected': selected.includes(record.id) }"
          >
            <input
              class="records-row__check"
              type="checkbox"
              :checked="selected.includes(record.id)"
              :aria-label="`选择第 ${record.totalQuestions} 题的${PRACTICE_TYPE_LABELS[record.practiceType]}记录`"
              @change="toggleSelected(record.id)"
            />
            <button
              class="records-row__open"
              type="button"
              :aria-current="record.id === activeId ? 'true' : undefined"
              @click="openRecord(record, true)"
            >
              <TypeMark :type="record.practiceType" :size="24" />
              <span class="records-row__body">
                <span class="records-row__title">{{ PRACTICE_TYPE_LABELS[record.practiceType] }}</span>
                <span class="records-row__meta">
                  {{ PRACTICE_SOURCE_LABELS[record.source] }} · {{ record.totalQuestions }} 题 · {{ formatSubmittedAt(record.submittedAt) }}
                </span>
              </span>
              <span class="records-row__marks">
                <span class="records-row__score">{{ scoreText(record) }}<small>分</small></span>
                <span v-if="record.wrongCount" class="records-row__wrong">{{ record.wrongCount }} 错</span>
                <span v-else class="records-row__clean">全对</span>
              </span>
            </button>
          </li>
        </ul>

        <nav v-if="total > limit" class="records-pager" aria-label="记录分页">
          <DivButton class="button-secondary button-small" type="button" :disabled="!canPrev || loading" @click="changePage(offset - limit)">上一页</DivButton>
          <span>{{ page }} / {{ pages }}</span>
          <DivButton class="button-secondary button-small" type="button" :disabled="!canNext || loading" @click="changePage(offset + limit)">下一页</DivButton>
        </nav>
      </section>

      <section class="records-detail" aria-label="记录详情" aria-live="polite">
        <LoadingState v-if="detailLoading" label="正在读取这次记录…" />
        <ErrorNotice v-else-if="detailError" :error="detailError" retry-label="重新读取" @retry="detail && openRecord(detail)" />
        <template v-else-if="detail">
          <header class="records-detail__head">
            <div class="records-detail__title">
              <TypeMark :type="detail.practiceType" :size="30" />
              <div>
                <h2>{{ PRACTICE_TYPE_LABELS[detail.practiceType] }}练习</h2>
                <p>{{ PRACTICE_SOURCE_LABELS[detail.source] }} · {{ detail.totalQuestions }} 题 · {{ formatSubmittedAt(detail.submittedAt) }}</p>
              </div>
            </div>
            <p class="records-detail__score">
              <strong>{{ scoreText(detail) }}</strong><span>分</span>
            </p>
          </header>

          <PracticeResultView v-if="detail.result" :result="detail.result" :questions="detail.questions" />
          <p v-else class="records-empty">这次练习暂无可用结果，可能仍在评分或评分失败。</p>
        </template>
        <div v-else class="records-detail__blank">
          <TypeMark type="reading" :size="46" />
          <p>从左边挑一条记录，这里会显示题目、你的答案和解析。</p>
        </div>
      </section>
    </div>
  </article>
</template>
