<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import ErrorNotice from '../components/ErrorNotice.vue'
import LoadingState from '../components/LoadingState.vue'
import PracticeResultView from '../components/PracticeResultView.vue'
import {
  deletePracticeRecords,
  getPracticeRecord,
  listPracticeMistakes,
  listPracticeRecords,
  PRACTICE_SOURCE_LABELS,
  PRACTICE_STATUS_LABELS,
  PRACTICE_TYPE_LABELS,
  type PracticeRecordDetail,
  type PracticeRecordSummary,
  type PracticeSource,
  type PracticeType,
} from '../api/practice'
import '../practice.css'

const props = withDefaults(defineProps<{ onlyMistakes?: boolean }>(), { onlyMistakes: false })

const records = ref<PracticeRecordSummary[]>([])
const total = ref(0)
const offset = ref(0)
const limit = 20
const practiceType = ref<PracticeType | ''>('')
const source = ref<PracticeSource | ''>('')
const mistakesOnly = ref(props.onlyMistakes)
const loading = ref(false)
const error = ref<unknown>(null)
const detail = ref<PracticeRecordDetail | null>(null)
const detailLoading = ref(false)
const detailError = ref<unknown>(null)
const selected = ref<string[]>([])
const deleting = ref(false)
const deleteError = ref<unknown>(null)
let pendingDeleteKey: string | null = null
let pendingDeleteSignature = ''

const practiceTypes: PracticeType[] = ['fill_blank', 'reading', 'translation', 'writing']
const practiceSources: PracticeSource[] = ['today_new', 'today_review', 'memory_mistakes', 'whole_book', 'difficulty']
const page = computed(() => Math.floor(offset.value / limit) + 1)
const pages = computed(() => Math.max(1, Math.ceil(total.value / limit)))
const canPrev = computed(() => offset.value > 0)
const canNext = computed(() => offset.value + limit < total.value)

function newKey(): string {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') return crypto.randomUUID()
  return `practice-delete-${Date.now()}-${Math.random().toString(16).slice(2)}`
}

async function load(): Promise<void> {
  loading.value = true
  error.value = null
  try {
    const pageData = mistakesOnly.value
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

async function openDetail(record: PracticeRecordSummary): Promise<void> {
  detailLoading.value = true
  detailError.value = null
  detail.value = null
  try {
    detail.value = await getPracticeRecord(record.id)
  } catch (requestError) {
    detailError.value = requestError
  } finally {
    detailLoading.value = false
  }
}

function toggleSelected(id: string): void {
  selected.value = selected.value.includes(id)
    ? selected.value.filter((item) => item !== id)
    : [...selected.value, id]
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
    await deletePracticeRecords(selected.value, pendingDeleteKey)
    pendingDeleteKey = null
    pendingDeleteSignature = ''
    selected.value = []
    detail.value = null
    await load()
  } catch (requestError) {
    deleteError.value = requestError
  } finally {
    deleting.value = false
  }
}

function changePage(nextOffset: number): void {
  offset.value = Math.max(0, nextOffset)
  void load()
}

watch([practiceType, source, mistakesOnly], () => {
  offset.value = 0
  detail.value = null
  void load()
})

onMounted(() => {
  void load()
})
</script>

<template>
  <article class="practice-page practice-records-page">
    <header class="practice-session-header">
      <div>
        <p class="eyebrow">{{ props.onlyMistakes ? 'AI 练习错题' : '练习记录' }}</p>
        <h1>{{ props.onlyMistakes ? '需要再练的 AI 题' : '练习记录与结果' }}</h1>
        <p class="lead">只展示当前账号的真实练习记录；提交前内容与用户答案不会出现在这里。</p>
      </div>
      <RouterLink class="button-secondary" to="/practice">返回练习中心</RouterLink>
    </header>

    <section class="panel practice-filter-bar">
      <div class="field">
        <label for="record-type">题型</label>
        <select id="record-type" v-model="practiceType">
          <option value="">全部题型</option>
          <option v-for="type in practiceTypes" :key="type" :value="type">{{ PRACTICE_TYPE_LABELS[type] }}</option>
        </select>
      </div>
      <div v-if="!props.onlyMistakes" class="field">
        <label for="record-source">来源</label>
        <select id="record-source" v-model="source">
          <option value="">全部来源</option>
          <option v-for="item in practiceSources" :key="item" :value="item">{{ PRACTICE_SOURCE_LABELS[item] }}</option>
        </select>
      </div>
      <label v-if="!props.onlyMistakes" class="checkbox record-mistake-toggle">
        <input v-model="mistakesOnly" type="checkbox" /> 只看错题
      </label>
      <p class="inline-note">当前契约按提交时间倒序返回，暂未提供时间范围查询参数。</p>
    </section>

    <LoadingState v-if="loading" label="正在读取练习记录…" />
    <section v-else-if="error" class="panel">
      <ErrorNotice :error="error" retry-label="重新读取记录" @retry="load" />
    </section>
    <section v-else-if="records.length === 0" class="panel empty-state">
      <h2>没有符合条件的记录</h2>
      <p>完成一次真实练习并提交后，记录会出现在这里。AI 不可用时仍可使用词书和记忆训练。</p>
      <RouterLink class="button" to="/practice">开始练习</RouterLink>
    </section>

    <template v-else>
      <section class="panel practice-records-table-wrap">
        <div class="button-row practice-records-actions">
          <strong>共 {{ total }} 条 · 第 {{ page }} / {{ pages }} 页</strong>
          <button class="button-danger button-small" type="button" :disabled="selected.length === 0 || deleting" @click="removeSelected">
            {{ deleting ? '删除中…' : `删除选中（${selected.length}）` }}
          </button>
        </div>
        <ErrorNotice v-if="deleteError" :error="deleteError" :show-retry="false" retry-label="重试" @retry="removeSelected" />
        <table class="practice-records-table">
          <caption class="visually-hidden">AI 练习记录</caption>
          <thead><tr><th scope="col">选择</th><th scope="col">题型</th><th scope="col">来源</th><th scope="col">结果</th><th scope="col">提交时间</th><th scope="col">操作</th></tr></thead>
          <tbody>
            <tr v-for="record in records" :key="record.id">
              <td><input type="checkbox" :checked="selected.includes(record.id)" :aria-label="`选择${PRACTICE_TYPE_LABELS[record.practiceType]}记录`" @change="toggleSelected(record.id)" /></td>
              <td>{{ PRACTICE_TYPE_LABELS[record.practiceType] }}<br /><small>{{ record.totalQuestions }} 题</small></td>
              <td>{{ PRACTICE_SOURCE_LABELS[record.source] }}</td>
              <td>
                <span class="status-badge" :class="record.status === 'submitted' ? 'status-badge--success' : 'status-badge--muted'">{{ PRACTICE_STATUS_LABELS[record.status] }}</span>
                <small v-if="record.score !== null"> · {{ record.score }} 分</small>
                <small v-if="record.wrongCount !== null"> · {{ record.wrongCount }} 错</small>
              </td>
              <td>{{ record.submittedAt ?? '—' }}</td>
              <td><button class="link-button" type="button" @click="openDetail(record)">查看结果</button></td>
            </tr>
          </tbody>
        </table>
        <nav class="pager" aria-label="练习记录分页">
          <button class="button-secondary button-small" type="button" :disabled="!canPrev || loading" @click="changePage(offset - limit)">上一页</button>
          <span>第 {{ page }} / {{ pages }} 页</span>
          <button class="button-secondary button-small" type="button" :disabled="!canNext || loading" @click="changePage(offset + limit)">下一页</button>
        </nav>
      </section>

      <LoadingState v-if="detailLoading" label="正在读取练习结果…" />
      <section v-else-if="detailError" class="panel"><ErrorNotice :error="detailError" retry-label="重新读取结果" @retry="detail && openDetail(detail)" /></section>
      <PracticeResultView v-else-if="detail?.result" :result="detail.result" />
      <section v-else-if="detail" class="panel"><p class="inline-note">该记录暂无可用结果，可能仍在评分或评分失败。</p></section>
    </template>
  </article>
</template>