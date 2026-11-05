<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { RouterLink, useRoute, useRouter } from 'vue-router'
import AppIcon from '../components/AppIcon.vue'
import SvgPlateButton from '../components/SvgPlateButton.vue'
import ErrorNotice from '../components/ErrorNotice.vue'
import { createPracticeSession, deletePracticeSession, fetchPracticeUsage, listPracticeMistakes, listRecentPracticeSessions, PRACTICE_SOURCE_LABELS, PRACTICE_TYPE_LABELS, regeneratePracticeSession, type PracticeCreateInput, type PracticeDifficulty, type PracticeRecordSummary, type PracticeSessionSummary, type PracticeSource, type PracticeType, type PracticeUsage } from '../api/practice'
import { listWordbooks, type Wordbook } from '../api/wordbooks'
import { deleteBackgroundTask, listBackgroundTasks, retryBackgroundTask, type BackgroundTask } from '../api/background-tasks'
import { fetchLearningProfile, saveMemoryConfig } from '../api/learning'
import { useToast } from '../composables/useToast'
import PracticeSessionView from './PracticeSessionView.vue'

import '../practice.css'

const router = useRouter()
const route = useRoute()
const activeSessionId = computed(() => (typeof route.query.session === 'string' && route.query.session ? route.query.session : null))
const practiceTypes: PracticeType[] = ['fill_blank', 'reading', 'translation', 'writing']
function queryType(value: unknown): PracticeSelection | null {
  if (value === 'random') return 'random'
  return typeof value === 'string' && practiceTypes.includes(value as PracticeType) ? value as PracticeType : null
}
type PracticeSelection = PracticeType | 'random'
const practiceType = ref<PracticeSelection>(queryType(route.query.type) ?? 'fill_blank')
const source = ref<PracticeSource>('today_new')
const count = ref(practiceType.value === 'writing' ? 1 : 5)
const difficulty = ref<PracticeDifficulty>('CET6')
const wordbookId = ref('')
const creating = ref(false)
const createError = ref<unknown>(null)
const usage = ref<PracticeUsage | null>(null)
const usageError = ref<unknown>(null)
const sessions = ref<PracticeSessionSummary[]>([])
const poolTasks = ref<BackgroundTask[]>([])
const taskError = ref<unknown>(null)
const taskBusyId = ref<string | null>(null)
const taskTab = ref<'questions' | 'mistakes'>('questions')
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
const counts = computed(() => (
  practiceType.value === 'writing'
    ? [1]
    : practiceType.value === 'random'
      ? [1, 3, 5, 10, 15, 20]
      : [3, 5, 10, 15, 20]
))
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

function selectType(next: PracticeSelection): void {
  practiceType.value = next
  count.value = next === 'writing' ? 1 : 5
}

const typeIcons: Record<PracticeSelection, 'book' | 'cards' | 'arrow' | 'spark' | 'star'> = {
  fill_blank: 'book',
  reading: 'cards',
  translation: 'arrow',
  writing: 'spark',
  random: 'star',
}

const typeOptions = computed(() => [
  ...practiceTypes.map((type) => ({ key: type as PracticeSelection, label: PRACTICE_TYPE_LABELS[type] })),
  { key: 'random' as PracticeSelection, label: '随机' },
])

function chooseType(next: PracticeSelection): void {
  selectType(next)
  void router.replace({ query: { ...route.query, type: next === 'random' ? undefined : next } })
}

function resolveType(selection: PracticeSelection): PracticeType {
  if (selection !== 'random') return selection
  const pool = count.value === 1 ? practiceTypes : practiceTypes.filter((type) => type !== 'writing')
  return pool[Math.floor(Math.random() * pool.length)]
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
    practiceType: resolveType(practiceType.value),
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
      name: 'practice',
      query: {
        session: session.id,
        ...(timerLimit.value > 0 ? { timer: String(timerLimit.value) } : {}),
      },
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

interface TaskRow {
  key: string
  kind: 'session' | 'pool'
  id: string
  practiceType: PracticeType
  source: PracticeSource | null
  status: 'generating' | 'ready' | 'submitted' | 'failed' | 'cancelled'
  count: number
  score: number | null
  createdAt: string
  submittedAt: string | null
  errorCode: string | null
}

const taskRows = computed<TaskRow[]>(() => {
  const rows: TaskRow[] = [
    ...sessions.value.map((row) => ({
      key: `session-${row.id}`,
      kind: 'session' as const,
      id: row.id,
      practiceType: row.practiceType,
      source: row.source,
      status: row.status,
      count: row.questionCount,
      score: row.score,
      createdAt: row.createdAt,
      submittedAt: row.submittedAt,
      errorCode: row.errorCode,
    })),
    ...poolTasks.value.map((task) => ({
      key: `pool-${task.id}`,
      kind: 'pool' as const,
      id: task.id,
      practiceType: task.practiceType,
      source: null,
      status: task.status === 'ready' ? ('ready' as const) : task.status,
      count: task.questionCount,
      score: null,
      createdAt: task.createdAt,
      submittedAt: null,
      errorCode: task.errorCode,
    })),
  ]
  return rows.sort((left, right) => right.createdAt.localeCompare(left.createdAt)).slice(0, 12)
})

const TASK_STATUS_LABELS: Record<TaskRow['status'], string> = {
  generating: '生成中',
  ready: '待练习',
  submitted: '已完成',
  failed: '生成失败',
  cancelled: '已取消',
}

function taskStatusLabel(row: TaskRow): string {
  return TASK_STATUS_LABELS[row.status] ?? row.status
}

function taskSourceLabel(row: TaskRow): string {
  if (row.kind === 'pool') return '预生成套题'
  return row.source ? PRACTICE_SOURCE_LABELS[row.source] : '专项练习'
}

function formatTaskDate(value: string): string {
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return ''
  return new Intl.DateTimeFormat('zh-CN', {
    month: 'numeric',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  }).format(date)
}

function openTask(row: TaskRow): void {
  void router.push({ name: 'practice', query: { session: row.id } })
}

async function loadTasks(): Promise<void> {
  const [sessionResult, poolResult] = await Promise.allSettled([
    listRecentPracticeSessions(20),
    listBackgroundTasks(),
  ])
  if (sessionResult.status === 'fulfilled') sessions.value = sessionResult.value
  else sessions.value = []
  if (poolResult.status === 'fulfilled') poolTasks.value = poolResult.value
  else poolTasks.value = []
  taskError.value = sessionResult.status === 'rejected' ? sessionResult.reason : null
}

async function retryTask(row: TaskRow): Promise<void> {
  if (taskBusyId.value) return
  taskBusyId.value = row.id
  try {
    if (row.kind === 'pool') {
      await retryBackgroundTask(row.id)
    } else {
      await regeneratePracticeSession(row.id, newKey())
    }
    await loadTasks()
    toast.success('已重新开始生成', '稍后回来查看状态即可。')
  } catch {
    toast.error('重试失败', '请稍后再试。')
  } finally {
    taskBusyId.value = null
  }
}

async function removeTask(row: TaskRow): Promise<void> {
  if (taskBusyId.value) return
  const confirmed = window.confirm('删除这条题目？正在生成的题目会被取消。')
  if (!confirmed) return
  taskBusyId.value = row.id
  try {
    if (row.kind === 'pool') await deleteBackgroundTask(row.id)
    else await deletePracticeSession(row.id)
    await loadTasks()
    toast.push({ title: '已删除', tone: 'info' })
  } catch {
    toast.error('删除失败', '请稍后再试。')
  } finally {
    taskBusyId.value = null
  }
}

async function startPoolTask(row: TaskRow): Promise<void> {
  selectType(row.practiceType)
  count.value = row.count
  await create()
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

function quotaText(kind: 'question_generation' | 'subjective_grading'): string {
  const remaining = quotaRemaining(kind)
  if (remaining === null) return '—'
  return remaining < 0 ? '不限' : String(remaining)
}

onMounted(() => {
  void Promise.all([loadUsage(), loadTasks(), loadMistakes(), loadWordbooks()])
})
</script>

<template>
  <article class="practice-page practice-hub member-practice-page practice-workspace workspace-page">
    <PracticeSessionView v-if="activeSessionId" embedded :session-id="activeSessionId" />

    <template v-else>
    <header class="workspace-page-header">
      <div>
        <p class="workspace-kicker">AI 练习</p>
        <h1>做一组有针对性的练习</h1>
        <p class="workspace-page-lead">从今天的学习内容出题，计时和拼写挖空也在这里设置。</p>
      </div>
    </header>


      <div class="practice-hub-layout">
      <section class="workspace-card practice-create-panel" aria-labelledby="practice-create-title">
        <header class="workspace-section-header practice-create-heading">
          <div>
            <p class="workspace-kicker">新建练习</p>
            <h2 id="practice-create-title">今天想练什么</h2>
          </div>
          <div class="practice-quota-inline" aria-label="今日练习额度">
            <span title="今日还可用 AI 生成题目的次数">生成余量 <strong>{{ quotaText('question_generation') }}</strong></span>
            <span title="今日还可提交主观题评分的次数">评分余量 <strong>{{ quotaText('subjective_grading') }}</strong></span>
          </div>
        </header>
        <ErrorNotice v-if="usageError" :error="usageError" :show-retry="false" retry-label="重试" @retry="loadUsage" />

        <form class="practice-form" novalidate @submit.prevent="create">
          <div class="practice-type-picker" role="group" aria-label="题型">
            <DivButton
              v-for="option in typeOptions"
              :key="option.key"
              class="practice-type-pill"
              :class="[`practice-type-pill--${option.key}`, { 'is-active': practiceType === option.key }]"
              :aria-pressed="practiceType === option.key"
              type="button"
              @click="chooseType(option.key)"
            >
              <AppIcon :name="typeIcons[option.key]" />
              {{ option.label }}
            </DivButton>
          </div>
          <p v-if="practiceType === 'random'" class="field-hint">从可选题型里随机抽一种；题量选 1 题时也可能抽到作文。</p>
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

      <section class="workspace-card practice-tasks-card" aria-label="题目列表">
        <header class="workspace-section-header practice-tasks-head">
          <div>
            <h2>题目列表</h2>
            <p>每次生成都会多一条，按状态继续、重试或删除。</p>
          </div>
          <div class="practice-task-tabs" role="group" aria-label="题目列表切换">
            <DivButton class="practice-task-tab" :class="{ 'is-active': taskTab === 'questions' }" :aria-pressed="taskTab === 'questions'" type="button" @click="taskTab = 'questions'">题目列表</DivButton>
            <DivButton class="practice-task-tab" :class="{ 'is-active': taskTab === 'mistakes' }" :aria-pressed="taskTab === 'mistakes'" type="button" @click="taskTab = 'mistakes'">错题本</DivButton>
          </div>
        </header>

        <template v-if="taskTab === 'questions'">
          <ErrorNotice v-if="taskError" :error="taskError" :show-retry="false" retry-label="重试" @retry="loadTasks" />
          <div v-else-if="taskRows.length" role="list" class="practice-task-list" aria-label="题目列表">
            <div role="listitem" v-for="row in taskRows" :key="row.key" class="practice-task-row">
              <div class="practice-task-row__main">
                <span class="practice-task-type">{{ PRACTICE_TYPE_LABELS[row.practiceType] }}</span>
                <strong>{{ taskSourceLabel(row) }}</strong>
                <span class="practice-task-status" :class="`is-${row.status}`">{{ taskStatusLabel(row) }}</span>
                <small>
                  {{ row.count }} 题 · {{ formatTaskDate(row.createdAt) }}
                  <template v-if="row.score !== null"> · {{ row.score }} 分</template>
                </small>
              </div>
              <div class="practice-task-row__actions">
                <DivButton
                  v-if="row.kind === 'pool' && row.status === 'ready'"
                  class="button-secondary button-small"
                  type="button"
                  :disabled="taskBusyId !== null"
                  @click="startPoolTask(row)"
                >开始</DivButton>
                <DivButton
                  v-else-if="row.status === 'ready' || row.status === 'generating' || row.status === 'submitted'"
                  class="button-secondary button-small"
                  type="button"
                  @click="openTask(row)"
                >{{ row.status === 'submitted' ? '查看' : '继续' }}</DivButton>
                <DivButton
                  v-if="row.status === 'failed'"
                  class="button-secondary button-small"
                  type="button"
                  :disabled="taskBusyId !== null"
                  @click="retryTask(row)"
                >重试</DivButton>
                <DivButton
                  class="button-secondary button-small"
                  type="button"
                  :disabled="taskBusyId !== null"
                  @click="removeTask(row)"
                >删除</DivButton>
              </div>
            </div>
          </div>
          <div v-else class="practice-rail-empty">
            <strong>还没有题目</strong>
            <p>生成第一组练习后，这里会按状态列出。</p>
          </div>
        </template>

        <template v-else>
          <ErrorNotice v-if="mistakesError" :error="mistakesError" :show-retry="false" retry-label="重试" @retry="loadMistakes" />
          <div v-else-if="mistakes.length" role="list" class="practice-task-list" aria-label="错题本">
            <div role="listitem" v-for="record in mistakes" :key="record.id" class="practice-task-row">
              <div class="practice-task-row__main">
                <span class="practice-task-type">{{ PRACTICE_TYPE_LABELS[record.practiceType] }}</span>
                <strong>{{ record.source ? PRACTICE_SOURCE_LABELS[record.source] : '专项练习' }}</strong>
                <small>{{ record.totalQuestions }} 题 · {{ record.score === null ? '未评分' : `${record.score} 分` }}</small>
              </div>
              <div class="practice-task-row__actions">
                <RouterLink class="button-secondary button-small" :to="{ name: 'practice', query: { session: record.id } }">查看</RouterLink>
              </div>
            </div>
          </div>
          <div v-else class="practice-rail-empty">
            <strong>还没有错题</strong>
            <p>完成练习后，错题会出现在这里。</p>
          </div>
          <RouterLink v-if="mistakesTotal > 0" class="practice-task-all" to="/practice/mistakes">查看全部 {{ mistakesTotal }} 条错题</RouterLink>
        </template>

        <RouterLink class="practice-task-all" to="/practice/records">查看全部练习记录</RouterLink>
      </section>
      </div>
    </template>
  </article>
</template>
