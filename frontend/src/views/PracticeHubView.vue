<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { RouterLink, useRouter } from 'vue-router'
import ErrorNotice from '../components/ErrorNotice.vue'
import { createPracticeSession, fetchPracticeUsage, listPracticeRecords, PRACTICE_SOURCE_LABELS, PRACTICE_TYPE_LABELS, type PracticeCreateInput, type PracticeDifficulty, type PracticeRecordSummary, type PracticeSource, type PracticeType, type PracticeUsage } from '../api/practice'
import { listWordbooks, type Wordbook } from '../api/wordbooks'
import '../practice.css'

const router = useRouter()
const practiceType = ref<PracticeType>('fill_blank')
const source = ref<PracticeSource>('today_new')
const count = ref(5)
const difficulty = ref<PracticeDifficulty>('CET6')
const wordbookId = ref('')
const creating = ref(false)
const createError = ref<unknown>(null)
const usage = ref<PracticeUsage | null>(null)
const usageError = ref<unknown>(null)
const records = ref<PracticeRecordSummary[]>([])
const recordsError = ref<unknown>(null)
const wordbooks = ref<Wordbook[]>([])
const wordbooksError = ref<unknown>(null)
const formError = ref<string | null>(null)
let pendingKey: string | null = null
let pendingSignature = ''

const types: PracticeType[] = ['fill_blank', 'reading', 'translation', 'writing']
const sources: PracticeSource[] = ['today_new', 'today_review', 'memory_mistakes', 'whole_book', 'difficulty']
const difficulties: PracticeDifficulty[] = ['CET4', 'CET6', 'POSTGRAD', 'IELTS', 'TOEFL']
const counts = computed(() => (practiceType.value === 'writing' ? [1] : [3, 5, 10, 15, 20]))
const needsDifficulty = computed(() => source.value === 'difficulty')
const needsWordbook = computed(() => source.value !== 'difficulty')

function newKey(): string {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') return crypto.randomUUID()
  return `practice-${Date.now()}-${Math.random().toString(16).slice(2)}`
}

function signature(input: PracticeCreateInput): string {
  return JSON.stringify(input)
}

function selectType(next: PracticeType): void {
  practiceType.value = next
  count.value = next === 'writing' ? 1 : 5
}

function validate(): string | null {
  if (!counts.value.includes(count.value)) return '题量不符合当前题型允许值。'
  if (needsDifficulty.value && !difficulty.value) return '按难度练习必须选择考试难度。'
  return null
}

async function create(): Promise<void> {
  formError.value = validate()
  if (formError.value) return
  const input: PracticeCreateInput = {
    practiceType: practiceType.value,
    source: source.value,
    count: count.value,
    difficulty: needsDifficulty.value ? difficulty.value : null,
    wordbookId: needsWordbook.value && wordbookId.value ? wordbookId.value : null,
  }
  const sig = signature(input)
  if (!pendingKey || pendingSignature !== sig) {
    pendingKey = newKey()
    pendingSignature = sig
  }
  creating.value = true
  createError.value = null
  try {
    const session = await createPracticeSession(input, pendingKey)
    pendingKey = null
    pendingSignature = ''
    await router.push({ name: 'practice-session', params: { sessionId: session.id } })
  } catch (error) {
    createError.value = error
  } finally {
    creating.value = false
  }
}

async function loadUsage(): Promise<void> {
  try {
    usage.value = await fetchPracticeUsage()
    usageError.value = null
  } catch (error) {
    usage.value = null
    usageError.value = error
  }
}

async function loadRecords(): Promise<void> {
  try {
    const page = await listPracticeRecords({ limit: 5 })
    records.value = page.items
    recordsError.value = null
  } catch (error) {
    records.value = []
    recordsError.value = error
  }
}

async function loadWordbooks(): Promise<void> {
  try {
    const page = await listWordbooks({ limit: 100 })
    wordbooks.value = page.items.filter((book) => book.status === 'ready')
    wordbooksError.value = null
  } catch (error) {
    wordbooks.value = []
    wordbooksError.value = error
  }
}

function quotaRemaining(kind: 'question_generation' | 'subjective_grading'): number | null {
  return usage.value?.quotas.find((quota) => quota.quotaKind === kind)?.remaining ?? null
}

onMounted(() => {
  void Promise.all([loadUsage(), loadRecords(), loadWordbooks()])
})
</script>

<template>
  <article class="practice-page practice-hub">
    <header class="practice-hero">
      <div>
        <p class="eyebrow">AI 练习</p>
        <h1>把今天的词，练成真正会用的能力</h1>
        <p class="lead">四类练习由服务端生成和评分。提交前只展示题面，不展示答案、解析、参考内容或分数。</p>
      </div>
      <div class="practice-hero__actions">
        <RouterLink class="button-secondary" to="/practice/records">练习记录</RouterLink>
        <RouterLink class="button-secondary" to="/practice/mistakes">错题</RouterLink>
      </div>
    </header>

    <section class="practice-quota-strip" aria-label="今日练习额度">
      <div><span>题目生成剩余</span><strong>{{ quotaRemaining('question_generation') ?? '—' }}</strong></div>
      <div><span>主观评分剩余</span><strong>{{ quotaRemaining('subjective_grading') ?? '—' }}</strong></div>
      <div><span>并发占用</span><strong>{{ usage ? `${usage.concurrency.inUse} / ${usage.concurrency.limit}` : '—' }}</strong></div>
      <p v-if="usage" class="inline-note">统计日期 {{ usage.localDate }} · 额度与并发由服务端实时返回。</p>
      <ErrorNotice v-else-if="usageError" :error="usageError" :show-retry="false" retry-label="重试" @retry="loadUsage" />
    </section>

    <div class="practice-hub-grid">
      <section class="panel practice-create-panel">
        <div class="section-heading">
          <div><p class="eyebrow">新建练习</p><h2>选择练习方式</h2></div>
        </div>

        <div class="practice-type-grid" role="group" aria-label="练习类型">
          <button
            v-for="type in types"
            :key="type"
            class="practice-type-card"
            :class="{ 'practice-type-card--active': practiceType === type }"
            type="button"
            :aria-pressed="practiceType === type"
            @click="selectType(type)"
          >
            <strong>{{ PRACTICE_TYPE_LABELS[type] }}</strong>
            <span>{{ type === 'fill_blank' ? '词义与语境' : type === 'reading' ? '文章理解' : type === 'translation' ? '英译中/中译英' : 'AI 评分作文' }}</span>
          </button>
        </div>

        <form class="practice-form" novalidate @submit.prevent="create">
          <div class="practice-form-grid">
            <div class="field">
              <label for="practice-source">来源</label>
              <select id="practice-source" v-model="source">
                <option v-for="item in sources" :key="item" :value="item">{{ PRACTICE_SOURCE_LABELS[item] }}</option>
              </select>
            </div>
            <div v-if="needsDifficulty" class="field">
              <label for="practice-difficulty">难度</label>
              <select id="practice-difficulty" v-model="difficulty">
                <option v-for="item in difficulties" :key="item" :value="item">{{ item }}</option>
              </select>
            </div>
            <div class="field">
              <label for="practice-count">题量</label>
              <select id="practice-count" v-model.number="count">
                <option v-for="item in counts" :key="item" :value="item">{{ item }} 题</option>
              </select>
            </div>
            <div v-if="needsWordbook" class="field">
              <label for="practice-wordbook">词书</label>
              <select id="practice-wordbook" v-model="wordbookId">
                <option value="">使用当前激活词书</option>
                <option v-for="book in wordbooks" :key="book.id" :value="book.id">{{ book.name }}</option>
              </select>
              <p v-if="wordbooksError" class="field-hint">词书列表读取失败；仍可留空使用当前激活词书。</p>
            </div>
          </div>

          <p v-if="formError" class="field-error" role="alert">{{ formError }}</p>
          <ErrorNotice v-if="createError" :error="createError" :show-retry="false" retry-label="重试创建" @retry="create" />
          <div class="button-row">
            <button class="button" type="submit" :disabled="creating">{{ creating ? '正在提交生成任务…' : '生成练习' }}</button>
            <span class="inline-note">创建请求返回 202 后进入真实生成/轮询页面。</span>
          </div>
        </form>
      </section>

      <aside class="practice-side-stack">
        <section class="panel">
          <div class="section-heading"><h2>最近记录</h2><RouterLink to="/practice/records">全部</RouterLink></div>
          <ErrorNotice v-if="recordsError" :error="recordsError" :show-retry="false" retry-label="重试" @retry="loadRecords" />
          <ul v-else-if="records.length" class="record-mini-list">
            <li v-for="record in records" :key="record.id">
              <RouterLink :to="{ name: 'practice-session', params: { sessionId: record.id } }">
                <strong>{{ PRACTICE_TYPE_LABELS[record.practiceType] }}</strong>
                <span>{{ PRACTICE_SOURCE_LABELS[record.source] }} · {{ record.totalQuestions }} 题</span>
                <small>{{ record.score === null ? '评分中/未评分' : `${record.score} 分` }}</small>
              </RouterLink>
            </li>
          </ul>
          <p v-else class="inline-note">还没有练习记录。完成一次练习后，结果会保存在服务端。</p>
        </section>

        <section class="panel">
          <h2>传统学习入口</h2>
          <p class="inline-note">AI 不可用时，词书与记忆训练仍然可用。</p>
          <div class="button-row">
            <RouterLink class="button-secondary" to="/wordbooks">查看词书</RouterLink>
            <RouterLink class="button-secondary" to="/memory">记忆训练</RouterLink>
          </div>
        </section>
      </aside>
    </div>
  </article>
</template>