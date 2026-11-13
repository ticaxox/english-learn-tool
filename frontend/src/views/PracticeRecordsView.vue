<script setup lang="ts">
/**
 * /practice/records and /practice/mistakes — one list, two scopes.
 *
 * A submitted practice is a record; a record that still holds a wrong answer is
 * a mistake. Both are lists here and nothing more: a record opens on its own
 * page, where the questions and the answers are. The switch at the top swaps
 * the filter, not the layout, and the mistake book lays the same rows out by
 * exercise type — the type a learner is weak in is the thing worth naming —
 * newest first inside each type. Scope and type live in the URL, so a filtered
 * view is something you can link to.
 */
import { computed, ref, watch } from 'vue'
import { RouterLink, useRoute, useRouter } from 'vue-router'
import ErrorNotice from '../components/ErrorNotice.vue'
import LoadingState from '../components/LoadingState.vue'
import TypeMark from '../components/TypeMark.vue'
import AppIcon from '../components/AppIcon.vue'
import DivButton from '../components/DivButton.vue'
import {
  deletePracticeRecords,
  listPracticeMistakes,
  listPracticeRecords,
  PRACTICE_SOURCE_LABELS,
  PRACTICE_TYPE_LABELS,
  type PracticeRecordSummary,
  type PracticeSource,
  type PracticeType,
} from '../api/practice'
import '../practice.css'

const props = withDefaults(defineProps<{ onlyMistakes?: boolean }>(), { onlyMistakes: false })

const route = useRoute()
const router = useRouter()

const practiceTypes: PracticeType[] = ['fill_blank', 'reading', 'translation', 'writing', 'conversation', 'mixed']
const practiceSources: PracticeSource[] = ['today_new', 'today_review', 'memory_mistakes', 'whole_book', 'difficulty']
/** The mistake book groups in one pass, so it loads a bigger slice at a time. */
const MISTAKE_BATCH = 100
const PAGE_SIZE = 12

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
const loading = ref(false)
const loadingMore = ref(false)
const error = ref<unknown>(null)

const selected = ref<string[]>([])
const deleting = ref(false)
const deleteError = ref<unknown>(null)
let pendingDeleteKey: string | null = null
let pendingDeleteSignature = ''

const page = computed(() => Math.floor(offset.value / PAGE_SIZE) + 1)
const pages = computed(() => Math.max(1, Math.ceil(total.value / PAGE_SIZE)))
const canPrev = computed(() => offset.value > 0)
const canNext = computed(() => offset.value + PAGE_SIZE < total.value)
const canLoadMore = computed(() => records.value.length < total.value)
const allSelected = computed(
  () => records.value.length > 0 && records.value.every((record) => selected.value.includes(record.id)),
)

/**
 * The mistake book is read type by type, newest first in each type. The server
 * already answers newest-first; sorting again keeps the promise if a page ever
 * arrives out of order.
 */
const groups = computed(() =>
  practiceTypes
    .map((type) => ({
      type,
      label: PRACTICE_TYPE_LABELS[type],
      items: records.value
        .filter((record) => record.practiceType === type)
        .slice()
        .sort((left, right) => (right.submittedAt ?? '').localeCompare(left.submittedAt ?? '')),
    }))
    .filter((group) => group.items.length > 0),
)

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

/** Where a record opens, and where its page should send the learner back to. */
function recordTarget(record: PracticeRecordSummary) {
  const query: Record<string, string> = { ...viewQuery(practiceType.value) }
  if (isMistakes.value) query.from = 'mistakes'
  return { name: 'practice-record', params: { recordId: record.id }, query }
}

function openRecord(record: PracticeRecordSummary): void {
  void router.push(recordTarget(record))
}

function newKey(): string {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') return crypto.randomUUID()
  return `practice-delete-${Date.now()}-${Math.random().toString(16).slice(2)}`
}

async function load(): Promise<void> {
  loading.value = true
  error.value = null
  try {
    if (isMistakes.value) {
      const pageData = await listPracticeMistakes({
        practiceType: practiceType.value || undefined,
        offset: 0,
        limit: MISTAKE_BATCH,
      })
      records.value = pageData.items
      total.value = pageData.total
    } else {
      const pageData = await listPracticeRecords({
        practiceType: practiceType.value || undefined,
        source: source.value || undefined,
        onlyMistakes: false,
        offset: offset.value,
        limit: PAGE_SIZE,
      })
      records.value = pageData.items
      total.value = pageData.total
    }
    selected.value = selected.value.filter((id) => records.value.some((item) => item.id === id))
  } catch (requestError) {
    records.value = []
    total.value = 0
    error.value = requestError
  } finally {
    loading.value = false
  }
}

async function loadMore(): Promise<void> {
  if (loadingMore.value || !canLoadMore.value) return
  loadingMore.value = true
  deleteError.value = null
  try {
    const pageData = await listPracticeMistakes({
      practiceType: practiceType.value || undefined,
      offset: records.value.length,
      limit: MISTAKE_BATCH,
    })
    const known = new Set(records.value.map((record) => record.id))
    records.value = [...records.value, ...pageData.items.filter((record) => !known.has(record.id))]
    total.value = pageData.total
  } catch (requestError) {
    error.value = requestError
  } finally {
    loadingMore.value = false
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
    // The page may now be past the end of the list; step back before reloading.
    if (!isMistakes.value && records.value.length <= removed.deletedIds.length && offset.value >= PAGE_SIZE) {
      offset.value = Math.max(0, offset.value - PAGE_SIZE)
    }
    await load()
  } catch (requestError) {
    deleteError.value = requestError
  } finally {
    deleting.value = false
  }
}

function changePage(nextOffset: number): void {
  offset.value = Math.max(0, nextOffset)
  selected.value = []
  void load()
}

watch(
  () => [route.name, route.query.type],
  () => {
    offset.value = 0
    selected.value = []
    // The source filter belongs to the records list only.
    if (isMistakes.value) source.value = ''
    void load()
  },
)

watch(source, () => {
  offset.value = 0
  void load()
})

void load()
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
            ? '答错过的练习按题型归在一起，每种题型里最近的在最前面。点一条看当时那道题。'
            : '每一次提交都在这里。点开一条，才看它的题目、你的作答和解析。' }}
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

    <LoadingState v-if="loading && records.length === 0" label="正在读取记录…" />
    <section v-else-if="error" class="panel">
      <ErrorNotice :error="error" retry-label="重新读取记录" @retry="load" />
    </section>

    <template v-else>
      <div class="records-toolbar">
        <label class="records-check-all">
          <input type="checkbox" :checked="allSelected" :disabled="records.length === 0" @change="toggleAll" />
          <span>{{ selected.length ? `已选 ${selected.length}` : '全选' }}</span>
        </label>
        <ErrorNotice v-if="deleteError" :error="deleteError" :show-retry="false" retry-label="重试" @retry="removeSelected" />
        <DivButton
          class="button-danger button-small"
          type="button"
          :disabled="selected.length === 0 || deleting"
          @click="removeSelected"
        >
          {{ deleting ? '删除中…' : '删除选中' }}
        </DivButton>
      </div>

      <p v-if="records.length === 0" class="records-empty panel">
        {{ isMistakes
          ? '还没有带着错题的练习。答错过的题目会自动归到这里。'
          : '还没有符合条件的记录。完成一次练习并提交后，记录会出现在这里。' }}
      </p>

      <!-- 题目集: one flat list, newest first. -->
      <section v-else-if="!isMistakes" class="records-list" aria-label="记录列表">
        <ul class="records-rows" role="list">
          <li
            v-for="record in records"
            :key="record.id"
            class="records-row"
            :class="{ 'is-selected': selected.includes(record.id) }"
          >
            <input
              class="records-row__check"
              type="checkbox"
              :checked="selected.includes(record.id)"
              :aria-label="`选择${PRACTICE_TYPE_LABELS[record.practiceType]}记录`"
              @change="toggleSelected(record.id)"
            />
            <button class="records-row__open" type="button" @click="openRecord(record)">
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
              <AppIcon class="records-row__go" name="arrow" />
            </button>
          </li>
        </ul>

        <nav v-if="total > PAGE_SIZE" class="records-pager" aria-label="记录分页">
          <DivButton class="button-secondary button-small" type="button" :disabled="!canPrev || loading" @click="changePage(offset - PAGE_SIZE)">上一页</DivButton>
          <span>{{ page }} / {{ pages }}</span>
          <DivButton class="button-secondary button-small" type="button" :disabled="!canNext || loading" @click="changePage(offset + PAGE_SIZE)">下一页</DivButton>
        </nav>
      </section>

      <!-- 错题本: the same rows, one shelf per type. -->
      <div v-else class="records-groups">
        <section v-for="group in groups" :key="group.type" class="records-group" :aria-label="`${group.label}错题`">
          <header class="records-group__head">
            <TypeMark :type="group.type" :size="22" />
            <h2>{{ group.label }}</h2>
            <span class="records-group__count">{{ group.items.length }} 条</span>
          </header>
          <ul class="records-rows" role="list">
            <li
              v-for="record in group.items"
              :key="record.id"
              class="records-row"
              :class="{ 'is-selected': selected.includes(record.id) }"
            >
              <input
                class="records-row__check"
                type="checkbox"
                :checked="selected.includes(record.id)"
                :aria-label="`选择${formatSubmittedAt(record.submittedAt)}的${group.label}记录`"
                @change="toggleSelected(record.id)"
              />
              <button class="records-row__open" type="button" @click="openRecord(record)">
                <span class="records-row__body">
                  <span class="records-row__title">{{ formatSubmittedAt(record.submittedAt) }}</span>
                  <span class="records-row__meta">
                    {{ PRACTICE_SOURCE_LABELS[record.source] }} · {{ record.totalQuestions }} 题 · 错 {{ record.wrongCount }}
                  </span>
                </span>
                <span class="records-row__marks">
                  <span class="records-row__score">{{ scoreText(record) }}<small>分</small></span>
                </span>
                <AppIcon class="records-row__go" name="arrow" />
              </button>
            </li>
          </ul>
        </section>

        <div v-if="canLoadMore" class="records-loadmore">
          <DivButton class="button-secondary button-small" type="button" :disabled="loadingMore" @click="loadMore">
            {{ loadingMore ? '读取中…' : '加载更多' }}
          </DivButton>
        </div>
      </div>
    </template>
  </article>
</template>
