<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { RouterLink, useRoute, useRouter } from 'vue-router'
import AppIcon from '../components/AppIcon.vue'
import SvgPlateButton from '../components/SvgPlateButton.vue'
import ErrorNotice from '../components/ErrorNotice.vue'
import { createPracticeSession, fetchPracticeUsage, listPracticeMistakes, listPracticeRecords, PRACTICE_SOURCE_LABELS, PRACTICE_TYPE_LABELS, type PracticeCreateInput, type PracticeDifficulty, type PracticeRecordSummary, type PracticeSource, type PracticeType, type PracticeUsage } from '../api/practice'
import { listWordbooks, type Wordbook } from '../api/wordbooks'
import { fetchLearningProfile, saveMemoryConfig } from '../api/learning'
import { useToast } from '../composables/useToast'

import PracticeTopBar from '../components/PracticeTopBar.vue'
import '../practice.css'

const router = useRouter()
const route = useRoute()
const practiceTypes: PracticeType[] = ['fill_blank', 'reading', 'translation', 'writing']
function queryType(value: unknown): PracticeType | null {
  return typeof value === 'string' && practiceTypes.includes(value as PracticeType) ? value as PracticeType : null
}
const practiceType = ref<PracticeType>(queryType(route.query.type) ?? 'fill_blank')
const source = ref<PracticeSource>('today_new')
const count = ref(practiceType.value === 'writing' ? 1 : 5)
const difficulty = ref<PracticeDifficulty>('CET6')
const wordbookId = ref('')
const creating = ref(false)
const createError = ref<unknown>(null)
const usage = ref<PracticeUsage | null>(null)
const usageError = ref<unknown>(null)
const records = ref<PracticeRecordSummary[]>([])
const recordsError = ref<unknown>(null)
const mistakes = ref<PracticeRecordSummary[]>([])
const mistakesTotal = ref(0)
const mistakesError = ref<unknown>(null)
const wordbooks = ref<Wordbook[]>([])
const wordbooksError = ref<unknown>(null)
const toast = useToast()
const spellingBlankMode = ref('')
const timerLimit = ref<number>(0)

function onTimerLimitChange(event: Event): void {
  timerLimit.value = Number((event.target as HTMLSelectElement).value) || 0
}

async function loadSpellingMode(): Promise<void> {
  try {
    const profile = await fetchLearningProfile()
    spellingBlankMode.value = profile.memoryConfig.spelling.blankType ?? ''
  } catch {
    spellingBlankMode.value = ''
  }
}

async function saveSpellingMode(): Promise<void> {
  try {
    const profile = await fetchLearningProfile()
    await saveMemoryConfig({
      ...profile.memoryConfig,
      spelling: {
        ...profile.memoryConfig.spelling,
        blankType: (spellingBlankMode.value || null) as typeof profile.memoryConfig.spelling.blankType,
      },
    })
    toast.success('拼写挖空方式已保存')
  } catch {
    toast.error('没有保存成功', '稍后再试一次。')
  }
}
const formError = ref<string | null>(null)
let pendingKey: string | null = null
let pendingSignature = ''

const sources: PracticeSource[] = ['today_new', 'today_review', 'memory_mistakes', 'whole_book', 'difficulty']
const difficulties: PracticeDifficulty[] = ['CET4', 'CET6', 'POSTGRAD', 'IELTS', 'TOEFL']
const counts = computed(() => (practiceType.value === 'writing' ? [1] : [3, 5, 10, 15, 20]))
const needsDifficulty = computed(() => source.value === 'difficulty')
const needsWordbook = computed(() => source.value !== 'difficulty')
onMounted(() => { void loadSpellingMode() })

watch(() => route.query.type, (value) => {
  const next = queryType(value)
  if (next && next !== practiceType.value) selectType(next)
})

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
    await router.push({
      name: 'practice-session',
      params: { sessionId: session.id },
      query: timerLimit.value > 0 ? { timer: String(timerLimit.value) } : {},
    })
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

async function loadMistakes(): Promise<void> {
  try {
    const page = await listPracticeMistakes({ limit: 5 })
    mistakes.value = page.items
    mistakesTotal.value = page.total
    mistakesError.value = null
  } catch (error) {
    mistakes.value = []
    mistakesTotal.value = 0
    mistakesError.value = error
  }
}
async function loadWordbooks(): Promise<void> {
  try {
    const page = await listWordbooks({ limit: 100 })
    wordbooks.value = page.items.filter((book) => book.status === 'ready' && book.visibility === 'private')
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
  void Promise.all([loadUsage(), loadRecords(), loadMistakes(), loadWordbooks()])
})
</script>

<template>
  <article class="practice-page practice-hub member-practice-page practice-workspace workspace-page">
    <PracticeTopBar mode="practice" :active="practiceType" />

    <header class="workspace-page-header">
      <div>
        <p class="workspace-kicker">AI 练习</p>
        <h1>做一组有针对性的练习</h1>
        <p class="workspace-page-lead">从今天的学习内容里出题，提交后再看答案与解析。</p>
      </div>
      <div class="workspace-header-actions">
        <RouterLink class="button workspace-secondary-button" to="/practice/records">练习记录</RouterLink>
        <RouterLink class="button workspace-secondary-button" to="/practice/mistakes">错题本</RouterLink>
      </div>
    </header>


      <section class="workspace-card practice-create-panel" aria-labelledby="practice-create-title">
        <header class="workspace-section-header practice-create-heading">
          <div>
            <p class="workspace-kicker">新建练习</p>
            <h2 id="practice-create-title">今天想练什么</h2>
          </div>
          <div class="practice-quota-inline" aria-label="今日练习额度">
            <span title="今日还可用 AI 生成题目的次数">生成余量 <strong>{{ quotaRemaining('question_generation') ?? '—' }}</strong></span>
            <span title="今日还可提交主观题评分的次数">评分余量 <strong>{{ quotaRemaining('subjective_grading') ?? '—' }}</strong></span>
          </div>
        </header>
        <ErrorNotice v-if="usageError" :error="usageError" :show-retry="false" retry-label="重试" @retry="loadUsage" />

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
            <div class="field">
              <label for="practice-spelling-mode">拼写挖空方式</label>
              <select id="practice-spelling-mode" v-model="spellingBlankMode" @change="saveSpellingMode">
                <option value="">随机（推荐）</option>
                <option value="full">整词挖空</option>
                <option value="partial">部分字母</option>
                <option value="first_letter">只留首字母</option>
                <option value="middle">中间挖空</option>
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
          <div v-if="creating" class="practice-generation-state is-loading" role="status" aria-live="polite">
            <span class="spinner" aria-hidden="true"></span>
            <div><strong>正在生成练习</strong><span>正在读取素材并准备题目，请稍候。</span></div>
          </div>
          <div v-else-if="createError" class="practice-generation-state is-error" role="status">
            <strong>这次没有生成成功</strong>
            <span>可以调整条件后重试，当前设置会保留。</span>
          </div>
          <ErrorNotice v-if="createError" :error="createError" :show-retry="false" retry-label="重试创建" @retry="create" />
          <div class="practice-create-footer">
            <div class="practice-create-footer__meta">
              <label class="practice-timer-control">
                <span>计时</span>
                <select id="practice-timer" :value="timerLimit" @change="onTimerLimitChange">
                  <option :value="0">不限（正计时）</option>
                  <option :value="5">5 分钟</option>
                  <option :value="10">10 分钟</option>
                  <option :value="15">15 分钟</option>
                  <option :value="20">20 分钟</option>
                  <option :value="30">30 分钟</option>
                </select>
              </label>
              <p>答案与解析只在提交后出现。</p>
            </div>
            <SvgPlateButton class="practice-generate-action" type="submit" :disabled="creating">
              {{ creating ? '正在生成…' : '生成练习' }} <AppIcon name="arrow" />
            </SvgPlateButton>
          </div>
        </form>
      </section>

    <section class="workspace-card practice-records-rail" aria-label="最近练习">
        <header class="workspace-section-header practice-rail-heading">
          <div>
            <h2>最近记录</h2>
            <p>接着上次继续。</p>
          </div>
          <RouterLink to="/practice/records">全部</RouterLink>
        </header>
        <ErrorNotice v-if="recordsError" :error="recordsError" :show-retry="false" retry-label="重试" @retry="loadRecords" />
        <div role="list" v-else-if="records.length" class="practice-record-list practice-record-list--row">
          <div role="listitem" v-for="record in records" :key="record.id">
            <RouterLink :to="{ name: 'practice-session', params: { sessionId: record.id } }">
              <span class="practice-record-type">{{ PRACTICE_TYPE_LABELS[record.practiceType] }}</span>
              <strong>{{ record.source ? PRACTICE_SOURCE_LABELS[record.source] : '专项练习' }}</strong>
              <small>{{ record.totalQuestions }} 题 · {{ record.score === null ? '未评分' : `${record.score} 分` }}</small>
            </RouterLink>
          </div>
        </div>
        <div v-else class="practice-rail-empty">
          <strong>还没有记录</strong>
          <p>生成第一组练习后，记录会出现在这里。</p>
        </div>
    </section>
  </article>
</template>
