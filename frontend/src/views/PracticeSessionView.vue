<script setup lang="ts">
import { computed, onUnmounted, ref, watch } from 'vue'
import { RouterLink, useRoute, useRouter } from 'vue-router'
import AppIcon from '../components/AppIcon.vue'
import SvgPlateButton from '../components/SvgPlateButton.vue'
import ErrorNotice from '../components/ErrorNotice.vue'
import { timerLimitFromQuery, useSessionTimer } from '../composables/useSessionTimer'
import LoadingState from '../components/LoadingState.vue'
import PracticeQuestionCard from '../components/PracticeQuestionCard.vue'
import SpokenText from '../components/SpokenText.vue'
import PracticeResultView from '../components/PracticeResultView.vue'
import { usePracticeSession } from '../composables/usePracticeSession'
import { useToast } from '../composables/useToast'
import { isApiError } from '../api/errors'
import {
  PRACTICE_SOURCE_LABELS,
  PRACTICE_STATUS_LABELS,
  PRACTICE_TYPE_LABELS,
  type PracticeAnswerInput,
} from '../api/practice'
import PracticeTopBar from '../components/PracticeTopBar.vue'
import { fetchProgress } from '../api/progress'
import '../practice.css'

const props = withDefaults(defineProps<{ sessionId?: string; embedded?: boolean }>(), { embedded: false })

const route = useRoute()
const router = useRouter()
const sessionTimer = useSessionTimer()
const timerLimit = timerLimitFromQuery(route.query.timer)
const toast = useToast()
const sessionId = props.sessionId ?? String(route.params.sessionId)
const practice = usePracticeSession(sessionId)
const answers = ref<Record<string, string>>({})
const formError = ref<string | null>(null)
const draftSavedAt = ref<string | null>(null)
const hydratedKey = ref<string | null>(null)
let autosaveTimer: number | null = null
let pendingSubmitKey: string | null = null
let pendingSubmitSignature = ''
let pendingRegenerateKey: string | null = null
let hydrating = false

const session = practice.session

watch(() => session.value?.status, (status) => {
  if (status === 'ready') {
    if (!sessionTimer.running.value) sessionTimer.start(timerLimit)
  } else if (status === 'submitted' || status === 'failed') {
    sessionTimer.stop()
  }
}, { immediate: true })
const result = practice.result
const questions = computed(() => session.value?.questions ?? [])
const answeredCount = computed(() => questions.value.filter((question) => (answers.value[question.id] ?? '').trim()).length)
const allAnswered = computed(() => questions.value.length > 0 && answeredCount.value === questions.value.length)
const hasAnyAnswer = computed(() => answeredCount.value > 0)
const draftConflict = computed(
  () => isApiError(practice.draftError.value) && practice.draftError.value.code === 'PRACTICE_DRAFT_VERSION_CONFLICT',
)
const canRegenerate = computed(
  () => (session.value?.status === 'ready' || session.value?.status === 'failed') && !hasAnyAnswer.value && !practice.busy.value,
)
const generationTimedOut = computed(() => session.value?.errorCode === 'AI_JOB_TIMEOUT')

function newKey(prefix: string): string {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') return `${prefix}-${crypto.randomUUID()}`
  return `${prefix}-${Date.now()}-${Math.random().toString(16).slice(2)}`
}

function clearAutosave(): void {
  if (autosaveTimer !== null) {
    window.clearTimeout(autosaveTimer)
    autosaveTimer = null
  }
}

function hydrate(nextKey: string): void {
  if (!session.value) return
  hydrating = true
  answers.value = { ...session.value.draftAnswers }
  hydratedKey.value = nextKey
  formError.value = null
  draftSavedAt.value = null
  queueMicrotask(() => { hydrating = false })
}

watch(
  () => session.value ? `${session.value.id}:${session.value.generationNumber}` : null,
  (key) => {
    if (key && key !== hydratedKey.value) hydrate(key)
  },
  { immediate: true },
)

watch(
  answers,
  () => {
    if (hydrating || session.value?.status !== 'ready' || draftConflict.value) return
    clearAutosave()
    autosaveTimer = window.setTimeout(() => {
      autosaveTimer = null
      void saveDraft()
    }, 900)
  },
  { deep: true },
)

async function saveDraft(): Promise<void> {
  if (!session.value || session.value.status !== 'ready') return
  const saved = await practice.saveDraft(answers.value)
  if (saved) draftSavedAt.value = saved.savedAt
}

async function retryDraftAfterConflict(): Promise<void> {
  await practice.refresh()
  hydrate(`${sessionId}:${session.value?.generationNumber ?? 0}:refresh`)
}

function answerPayload(): PracticeAnswerInput[] {
  return questions.value.map((question) => ({
    questionId: question.id,
    answer: (answers.value[question.id] ?? '').trim(),
  }))
}

const award = ref<{ xp: number; crumbs: number; from: number; to: number } | null>(null)

async function submit(): Promise<void> {
  award.value = null
  formError.value = null
  if (!allAnswered.value) {
    formError.value = `还有 ${questions.value.length - answeredCount.value} 题未作答。请完成全部题目后提交。`
    return
  }
  const payload = answerPayload()
  const signature = JSON.stringify(payload)
  if (!pendingSubmitKey || pendingSubmitSignature !== signature) {
    pendingSubmitKey = newKey('practice-submit')
    pendingSubmitSignature = signature
  }
  const before = await fetchProgress().catch(() => null)
  const response = await practice.submit(payload, pendingSubmitKey)
  if (response) {
    pendingSubmitKey = null
    pendingSubmitSignature = ''
    // The server owns the numbers; diff two reads to show what this set earned.
    const after = await fetchProgress().catch(() => null)
    if (before && after) {
      const xp = after.xp - before.xp
      const crumbs = after.crumbs - before.crumbs
      if (xp > 0 || crumbs > 0 || after.level.level > before.level.level) {
        award.value = {
          xp,
          crumbs,
          from: before.level.level,
          to: after.level.level,
        }
      }
    }
  }
}

async function regenerate(): Promise<void> {
  if (!canRegenerate.value) return
  const confirmed = window.confirm('当前练习尚未作答，确定重新生成整组题目吗？旧题会被替换。')
  if (!confirmed) return
  pendingRegenerateKey ??= newKey('practice-regenerate')
  await practice.regenerate(pendingRegenerateKey)
  pendingRegenerateKey = null
}

const isReading = computed(() => session.value?.practiceType === 'reading')
// Reading is one passage followed by its questions, never one article per question.
const readingArticle = computed(() => questions.value.find((question) => question.article)?.article ?? '')
const readingWords = computed(() => [...new Set(questions.value.flatMap((question) => question.targetWords))])
// A mixed set may hold a passage whose questions share it; show the text once.
const repeatedArticles = computed(() => {
  const seen = new Set<string>()
  const repeated = new Set<string>()
  for (const question of questions.value) {
    if (!question.article) continue
    if (seen.has(question.article)) repeated.add(question.id)
    else seen.add(question.article)
  }
  return repeated
})
function hideArticle(question: { id: string }): boolean {
  return isReading.value || repeatedArticles.value.has(question.id)
}

async function cancelGeneration(): Promise<void> {
  // The server job is not aborted; leaving the session stops waiting for it.
  toast.push({ title: '已取消等待', description: '生成可能仍在后台完成，可以随时回到练习中心重新开始。', tone: 'info' })
  await router.push('/practice')
}

onUnmounted(clearAutosave)
void practice.load()
</script>

<template>
  <article class="practice-page practice-session-page member-practice-session-page" :class="{ 'is-embedded': embedded }">
    <PracticeTopBar v-if="!embedded" mode="practice" :active="session?.practiceType ?? null" />

    <header class="practice-session-header practice-stage-header">
      <div>
        <p class="eyebrow">AI 练习</p>
        <h1>{{ session ? `${PRACTICE_TYPE_LABELS[session.practiceType]}练习` : '练习会话' }}</h1>
        <p v-if="session" class="lead">
          {{ PRACTICE_SOURCE_LABELS[session.source] }} · {{ session.questionCount }} 题 · {{ PRACTICE_STATUS_LABELS[session.status] }}
        </p>
      </div>
    </header>

    <LoadingState v-if="practice.loading.value" label="正在读取练习会话…" />
    <section v-else-if="practice.error.value" class="panel">
      <ErrorNotice :error="practice.error.value" retry-label="重新读取会话" @retry="practice.refresh" />
      <RouterLink class="button" to="/practice">重新创建练习</RouterLink>
    </section>

    <template v-else-if="session">
      <section v-if="session.status === 'generating'" class="panel practice-generation-panel" aria-live="polite">
        <p class="eyebrow">正在生成练习</p>
        <h2>正在生成第 {{ session.generationNumber }} 组题目</h2>
        <p>题目正在生成，请稍候。</p>
        <p class="field-hint">通常需要 1–2 分钟；如果等待过久会自动结束，可以再重试。</p>
        <div class="practice-generation-loader" aria-hidden="true"><span></span><span></span><span></span></div>
        <div class="button-row">
          <DivButton class="button-secondary" type="button" @click="cancelGeneration">取消生成</DivButton>
          <RouterLink class="button-secondary" to="/practice">返回练习中心</RouterLink>
        </div>
      </section>

      <section v-else-if="session.status === 'failed'" class="panel">
        <p class="eyebrow">生成失败</p>
        <h2>题目生成失败</h2>
        <p v-if="generationTimedOut">这次等待 AI 的时间过长，题目还没有生成完。可以直接重试。</p>
        <p v-else>请稍后重试，或重新创建练习。</p>
        <div class="button-row">
          <DivButton class="button" type="button" :disabled="practice.busy.value" @click="regenerate">重新生成</DivButton>
          <RouterLink class="button-secondary" to="/practice">新建练习</RouterLink>
        </div>
      </section>

      <template v-else-if="result">
        <p v-if="award" class="practice-award" :class="{ 'is-levelup': award.to > award.from }" role="status">
          <span v-if="award.to > award.from" class="practice-award__levelup">
            升级到 Lv.{{ award.to }}！
          </span>
          <span>+{{ award.xp }} XP · +{{ award.crumbs }} 碎屑</span>
        </p>
        <PracticeResultView :result="result" :questions="questions" />
      </template>

      <section v-else-if="session.status === 'submitted'" class="panel" aria-live="polite">
        <p class="eyebrow">主观题评分中</p>
        <h2>正在评分，请稍候</h2>
        <p>评分完成前不会显示答案和分数。</p>
        <p v-if="practice.submitError.value" class="alert alert-warning">{{ String(practice.submitError.value) }}</p>
      </section>

      <template v-else-if="session.status === 'ready'">
        <section v-if="isReading && readingArticle" class="panel practice-article-panel practice-article-panel--wide">
          <p class="eyebrow">阅读材料</p>
          <SpokenText class="practice-article" :text="readingArticle" :highlight="readingWords" />
        </section>

        <div class="member-practice-session-layout">
          <div class="member-practice-workbench">

            <section v-if="draftConflict" class="alert alert-warning" role="alert">
              <strong>草稿版本冲突</strong>
              <p>答案已在其他页面更新，请重新加载后再编辑。</p>
              <DivButton class="button-secondary button-small" type="button" @click="retryDraftAfterConflict">读取最新草稿</DivButton>
            </section>
            <ErrorNotice v-else-if="practice.draftError.value" :error="practice.draftError.value" :show-retry="false" retry-label="重试" @retry="saveDraft" />

            <PracticeQuestionCard
              v-for="(question, index) in questions"
              :key="question.id"
              :question="question"
              :index="index"
              :total="questions.length"
              :hide-article="hideArticle(question)"
              :model-value="answers[question.id] ?? ''"
              :disabled="practice.busy.value"
              @update:model-value="answers[question.id] = $event"
            />

          </div>

          <aside class="member-practice-session-aside" aria-label="作答操作">
            <section class="panel practice-session-side" aria-label="作答操作">
              <div v-if="sessionTimer.running.value" class="practice-session-side__timer">
                <span class="practice-rail-clock__label">本次用时</span>
                <span class="practice-stage-clock" :class="{ 'is-expired': sessionTimer.expired.value }">
                  <AppIcon name="today" />
                  <span>{{ timerLimit ? '倒计时' : '正计时' }} {{ sessionTimer.label.value }}</span>
                </span>
              </div>
              <div class="practice-submit-progress">
                <div class="practice-submit-progress__top">
                  <span>已答 {{ answeredCount }} / {{ questions.length }}</span>
                </div>
                <div class="progress"><span :style="{ width: `${questions.length ? Math.round(answeredCount / questions.length * 100) : 0}%` }"></span></div>
              </div>
              <p v-if="formError" class="field-error" role="alert">{{ formError }}</p>
              <ErrorNotice v-if="practice.submitError.value" :error="practice.submitError.value" :show-retry="false" retry-label="重试" @retry="submit" />
              <SvgPlateButton class="practice-submit-button" block :disabled="practice.busy.value || !allAnswered" @click="submit">
                <span class="practice-submit-label">{{ practice.busy.value ? '正在提交…' : '提交全部答案' }}</span>
                <span class="practice-submit-label practice-submit-label--short">{{ practice.busy.value ? '提交中…' : '提交' }}</span>
                <AppIcon name="arrow" />
              </SvgPlateButton>
              <DivButton class="button-secondary practice-regenerate-button" type="button" :disabled="!canRegenerate" @click="regenerate">未作答重生成</DivButton>
            </section>
          </aside>
        </div>
      </template>
    </template>
  </article>
</template>