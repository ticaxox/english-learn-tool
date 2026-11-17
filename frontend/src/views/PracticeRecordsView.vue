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
import PracticeRecordRow from '../components/PracticeRecordRow.vue'
import DivButton from '../components/DivButton.vue'
import {
  deletePracticeRecords,
  listPracticeMistakes,
  listPracticeRecords,
  PRACTICE_SOURCE_LABELS,
  PRACTICE_TYPE_LABELS,
  type PracticeRecordSummary,
  type PracticeType,
} from '../api/practice'
import '../practice.css'

const props = withDefaults(defineProps<{ onlyMistakes?: boolean }>(), { onlyMistakes: false })

const route = useRoute()
const router = useRouter()

const practiceTypes: PracticeType[] = ['fill_blank', 'reading', 'translation', 'writing', 'conversation', 'mixed']
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

/** A local calendar day, not a timestamp: the mistake book is read by date. */
function dayKeyOf(value: string | null): string {
  const date = value ? new Date(value) : null
  if (!date || Number.isNaN(date.getTime())) return ''
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`
}

function dayLabelOf(key: string, value: string | null): string {
  const date = value ? new Date(value) : null
  if (!date || Number.isNaN(date.getTime())) return '日期未知'
  const today = new Date()
  const yesterday = new Date()
  yesterday.setDate(today.getDate() - 1)
  if (key === dayKeyOf(today.toISOString())) return '今天'
  if (key === dayKeyOf(yesterday.toISOString())) return '昨天'
  return new Intl.DateTimeFormat('zh-CN', {
    year: 'numeric',
    month: 'long',
    day: 'numeric',
    weekday: 'short',
  }).format(date)
}

/**
 * The mistake book opens on dates: one group per day, newest day first. Inside
 * a day the rows are split by exercise type — the type a learner is weak in is
 * worth naming — and within a type the newest practice leads. With one type
 * picked, the day already says everything the type would, so the rows sit
 * straight under the date.
 */
const dayGroups = computed(() => {
  // The server filters by type already; doing it again keeps a loose response
  // from mixing types into a view that promised one.
  const visible = practiceType.value
    ? records.value.filter((record) => record.practiceType === practiceType.value)
    : records.value
  const buckets = new Map<string, PracticeRecordSummary[]>()
  for (const record of visible) {
    const key = dayKeyOf(record.submittedAt)
    const bucket = buckets.get(key) ?? []
    bucket.push(record)
    buckets.set(key, bucket)
  }
  return [...buckets.entries()]
    .sort((left, right) => right[0].localeCompare(left[0]))
    .map(([key, items]) => {
      const sorted = items
        .slice()
        .sort((left, right) => (right.submittedAt ?? '').localeCompare(left.submittedAt ?? ''))
      return {
        key,
        label: dayLabelOf(key, sorted[0]?.submittedAt ?? null),
        count: sorted.length,
        items: sorted,
        types: practiceTypes
          .map((type) => ({
            type,
            label: PRACTICE_TYPE_LABELS[type],
            items: sorted.filter((record) => record.practiceType === type),
          }))
          .filter((group) => group.items.length > 0),
      }
    })
})

/** What the list actually has to show, after the client-side type guard. */
const hasRows = computed(() => (isMistakes.value ? dayGroups.value.length > 0 : records.value.length > 0))

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

/** A row inside a dated group needs the clock time, not the whole date. */
function timeOfDay(value: string | null): string {
  if (!value) return '—'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return '—'
  return new Intl.DateTimeFormat('zh-CN', { hour: '2-digit', minute: '2-digit' }).format(date)
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
    void load()
  },
)


void load()
</script>

<template>
  <article class="practice-page practice-records-page workspace-page">
    <header class="workspace-page-header records-header">
      <div class="records-header__copy">
        <p class="workspace-kicker">复习巩固</p>
        <h1>{{ isMistakes ? '错题本' : '题目集' }}</h1>
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
          v-for="type in practiceTypes.filter((item) => item !== 'mixed')"
          :key="type"
          class="records-type-tab"
          :class="{ 'is-active': practiceType === type }"
          :to="{ name: route.name as string, query: viewQuery(type) }"
        >
          <span>{{ PRACTICE_TYPE_LABELS[type] }}</span>
        </RouterLink>
      </nav>

      <div class="records-filters__tail">
        <span class="records-tally">{{ total }} 条记录</span>
      </div>
    </section>

    <LoadingState v-if="loading && records.length === 0" label="正在读取记录…" />
    <section v-else-if="error" class="panel">
      <ErrorNotice :error="error" retry-label="重新读取记录" @retry="load" />
    </section>

    <template v-else>
      <p v-if="!hasRows" class="records-empty panel">
        {{ isMistakes
          ? '还没有带着错题的练习。答错过的题目会自动归到这里。'
          : '还没有符合条件的记录。完成一次练习并提交后，记录会出现在这里。' }}
      </p>

      <div v-else class="records-body">
        <div class="records-toolbar">
          <label class="records-check-all">
            <input type="checkbox" :checked="allSelected" :disabled="records.length === 0" @change="toggleAll" />
            <span>{{ selected.length ? `已选 ${selected.length}` : '全选' }}</span>
          </label>
          <ErrorNotice v-if="deleteError" :error="deleteError" :show-retry="false" retry-label="重试" @retry="removeSelected" />
          <DivButton
            class="records-delete"
            type="button"
            :disabled="selected.length === 0 || deleting"
            @click="removeSelected"
          >
            {{ deleting ? '删除中…' : selected.length ? `删除 ${selected.length} 条` : '删除' }}
          </DivButton>
        </div>

        <!-- 题目集: one flat list, newest first. -->
        <section v-if="!isMistakes" class="records-list" aria-label="记录列表">
        <ul class="records-rows" role="list">
          <PracticeRecordRow
            v-for="record in records"
            :key="record.id"
            :record="record"
            :checked="selected.includes(record.id)"
            :title="PRACTICE_TYPE_LABELS[record.practiceType]"
            :meta="`${PRACTICE_SOURCE_LABELS[record.source]} · ${record.totalQuestions} 题 · ${formatSubmittedAt(record.submittedAt)}`"
            @toggle="toggleSelected(record.id)"
            @open="openRecord(record)"
          />
        </ul>

        <nav v-if="total > PAGE_SIZE" class="records-pager" aria-label="记录分页">
          <DivButton class="button-secondary button-small" type="button" :disabled="!canPrev || loading" @click="changePage(offset - PAGE_SIZE)">上一页</DivButton>
          <span>{{ page }} / {{ pages }}</span>
          <DivButton class="button-secondary button-small" type="button" :disabled="!canNext || loading" @click="changePage(offset + PAGE_SIZE)">下一页</DivButton>
        </nav>
      </section>

      <!-- 错题本: dates first; inside a day, one shelf per type unless a type is picked. -->
      <div v-else class="records-groups">
        <section v-for="day in dayGroups" :key="day.key" class="records-group" :aria-label="`${day.label}的错题`">
          <header class="records-group__head">
            <h2>{{ day.label }}</h2>
            <span class="records-group__count">{{ day.count }} 条</span>
          </header>

          <template v-if="practiceType === ''">
            <div v-for="group in day.types" :key="group.type" class="records-subgroup">
              <header class="records-subgroup__head">
                <TypeMark :type="group.type" :size="18" />
                <h3>{{ group.label }}</h3>
                <span>{{ group.items.length }} 条</span>
              </header>
              <ul class="records-rows" role="list">
                <PracticeRecordRow
                  v-for="record in group.items"
                  :key="record.id"
                  :record="record"
                  :checked="selected.includes(record.id)"
                  :show-mark="false"
                  :title="timeOfDay(record.submittedAt)"
                  :meta="`${PRACTICE_SOURCE_LABELS[record.source]} · ${record.totalQuestions} 题 · 错 ${record.wrongCount}`"
                  @toggle="toggleSelected(record.id)"
                  @open="openRecord(record)"
                />
              </ul>
            </div>
          </template>

          <ul v-else class="records-rows" role="list">
            <PracticeRecordRow
              v-for="record in day.items"
              :key="record.id"
              :record="record"
              :checked="selected.includes(record.id)"
              :show-mark="false"
              :title="timeOfDay(record.submittedAt)"
              :meta="`${PRACTICE_SOURCE_LABELS[record.source]} · ${record.totalQuestions} 题 · 错 ${record.wrongCount}`"
              @toggle="toggleSelected(record.id)"
              @open="openRecord(record)"
            />
          </ul>
        </section>

        <div v-if="canLoadMore" class="records-loadmore">
          <DivButton class="button-secondary button-small" type="button" :disabled="loadingMore" @click="loadMore">
            {{ loadingMore ? '读取中…' : '加载更多' }}
          </DivButton>
        </div>
        </div>
      </div>
    </template>
  </article>
</template>
