<script setup lang="ts">
import { computed, nextTick, onUnmounted, ref, watch } from 'vue'
import { RouterLink, useRoute, useRouter } from 'vue-router'
import AppIcon from '../components/AppIcon.vue'
import ArtImage from '../components/ArtImage.vue'
import { hobActions, illustration } from '../assets/halloween'
import SvgPlateButton from '../components/SvgPlateButton.vue'
import ErrorNotice from '../components/ErrorNotice.vue'
import { timerLimitFromQuery, useSessionTimer } from '../composables/useSessionTimer'
import LoadingState from '../components/LoadingState.vue'
import PracticeQuestionCard from '../components/PracticeQuestionCard.vue'
import PracticeConversation from '../components/PracticeConversation.vue'
import SpokenText from '../components/SpokenText.vue'
import PracticeResultView from '../components/PracticeResultView.vue'
import { usePracticeSession } from '../composables/usePracticeSession'
import { loadWordGlossary } from '../composables/useWordGlossary'
import { useToast } from '../composables/useToast'
import { isApiError } from '../api/errors'
import { type PracticeAnswerInput } from '../api/practice'
import PracticeTopBar from '../components/PracticeTopBar.vue'
import { useRuneSurface } from '../composables/useRuneSurface'
import LevelUpOverlay from '../components/LevelUpOverlay.vue'
import { fetchProgress } from '../api/progress'
import '../practice.css'

const props = withDefaults(defineProps<{ sessionId?: string; embedded?: boolean }>(), { embedded: false })

const route = useRoute()
// The reading passage is its own sheet, so it binds the paper itself: the card
// below sets the variables on its own element and would not hand them down.
const { surface } = useRuneSurface()
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
// The sprite sits on the clock rail, on top of the wood card — not inside a question card.
const railSprite = computed(() => hobActions[session.value?.practiceType ?? ''] ?? hobActions.mixed)

// Words in the passage that belong to the learner's wordbook open a little
// gloss; the whole book is read once per session.
watch(
  () => session.value?.wordbookId,
  (wordbookId) => { void loadWordGlossary(wordbookId) },
  { immediate: true },
)
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

const levelUp = ref<{ level: number; title: string } | null>(null)

async function submit(): Promise<void> {
  formError.value = null
  // A learner may hand in what they have: the empty ones count as wrong.
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
    // The server owns the numbers; only a level change still needs saying aloud.
    const after = await fetchProgress().catch(() => null)
    if (before && after && after.level.level > before.level.level) {
      await nextTick()
      levelUp.value = { level: after.level.level, title: after.level.title }
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

    <LoadingState v-if="practice.loading.value" label="正在读取练习会话…" />
    <section v-else-if="practice.error.value" class="panel">
      <ErrorNotice :error="practice.error.value" retry-label="重新读取会话" @retry="practice.refresh" />
      <RouterLink class="button" to="/practice">重新创建练习</RouterLink>
    </section>

    <template v-else-if="session">
      <section v-if="session.status === 'generating'" class="panel practice-generation-panel" aria-live="polite">
        <ArtImage class="practice-generation__mascot" :set="illustration.brewing" />
        <div class="practice-generation__copy">
          <p class="eyebrow">正在生成练习</p>
          <h2>正在生成第 {{ session.generationNumber }} 组题目</h2>
          <p>题目正在生成，请稍候。</p>
          <p class="field-hint">通常需要 1–2 分钟；如果等待过久会自动结束，可以再重试。</p>
          <div class="practice-generation-loader" aria-hidden="true"><span></span><span></span><span></span></div>
          <div class="button-row">
            <DivButton class="button-secondary" type="button" @click="cancelGeneration">取消生成</DivButton>
            <RouterLink class="button-secondary" to="/practice">返回练习中心</RouterLink>
          </div>
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
        <LevelUpOverlay
          v-if="levelUp"
          :level="levelUp.level"
          :title="levelUp.title"
          @close="levelUp = null"
        />
        <PracticeResultView :result="result" :questions="questions" />
      </template>

      <!-- Grading is the same wait as generation, so it wears the same sheet. -->
      <section v-else-if="session.status === 'submitted'" class="panel practice-generation-panel" aria-live="polite">
        <img class="practice-generation__mascot" :src="hobActions.grading" alt="" />
        <div class="practice-generation__copy">
          <p class="eyebrow">正在评卷</p>
          <h2>正在批改这一组答案</h2>
          <p>评分完成前不会显示答案和分数。</p>
          <p class="field-hint">通常需要几十秒；改卷完成后这一页会自己打开成绩。</p>
          <div class="practice-generation-loader" aria-hidden="true"><span></span><span></span><span></span></div>
          <p v-if="practice.submitError.value" class="alert alert-warning">{{ String(practice.submitError.value) }}</p>
        </div>
      </section>

      <template v-else-if="session.status === 'ready'">
        <div class="member-practice-session-layout">
          <!-- The passage shares the two columns below it, so its right edge
               lands on the timer card and its left edge on the questions. -->
          <section
            v-if="isReading && readingArticle"
            class="panel practice-article-panel practice-article-panel--wide"
            :style="surface"
          >
            <p class="eyebrow">阅读材料</p>
            <SpokenText class="practice-article" :text="readingArticle" :highlight="readingWords" />
          </section>

          <div class="member-practice-workbench">

            <section v-if="draftConflict" class="alert alert-warning" role="alert">
              <strong>草稿版本冲突</strong>
              <p>答案已在其他页面更新，请重新加载后再编辑。</p>
              <DivButton class="button-secondary button-small" type="button" @click="retryDraftAfterConflict">读取最新草稿</DivButton>
            </section>
            <ErrorNotice v-else-if="practice.draftError.value" :error="practice.draftError.value" :show-retry="false" retry-label="重试" @retry="saveDraft" />

            <template v-for="(question, index) in questions" :key="question.id">
              <PracticeConversation
                v-if="question.questionType === 'conversation'"
                :session-id="sessionId"
                :question="question"
                @answer="answers[question.id] = $event"
              />
              <PracticeQuestionCard
                v-else
                :question="question"
                :index="index"
                :total="questions.length"
                :hide-article="hideArticle(question)"
                :model-value="answers[question.id] ?? ''"
                :disabled="practice.busy.value"
                @update:model-value="answers[question.id] = $event"
              />
            </template>

          </div>

          <aside class="member-practice-session-aside" aria-label="作答操作">
            <section class="panel practice-session-side" aria-label="作答操作">
              <div class="practice-rail-head">
                <span class="practice-rail-count">{{ answeredCount }}/{{ questions.length }}</span>
                <span class="practice-rail-clock" :class="{ 'is-expired': sessionTimer.expired.value }">
                  {{ sessionTimer.running.value ? sessionTimer.label.value : '已暂停' }}
                </span>
              </div>
              <span class="practice-rail-track" aria-hidden="true">
                <span :style="{ width: `${questions.length ? Math.round(answeredCount / questions.length * 100) : 0}%` }"></span>
              </span>
              <p v-if="formError" class="field-error" role="alert">{{ formError }}</p>
              <ErrorNotice v-if="practice.submitError.value" :error="practice.submitError.value" :show-retry="false" retry-label="重试" @retry="submit" />
              <p v-if="!allAnswered" class="practice-submit-hint">
                还有 {{ questions.length - answeredCount }} 题空着，提交后按错题计。
              </p>
              <SvgPlateButton class="practice-submit-button" block :disabled="practice.busy.value" @click="submit">
                <span class="practice-submit-label">{{ practice.busy.value ? '正在提交…' : '提交全部答案' }}</span>
                <span class="practice-submit-label practice-submit-label--short">{{ practice.busy.value ? '提交中…' : '提交' }}</span>
                <AppIcon name="arrow" />
              </SvgPlateButton>
              <DivButton class="button-secondary practice-regenerate-button" type="button" :disabled="!canRegenerate" @click="regenerate">未作答重生成</DivButton>
            </section>

            <!-- Hob stands below the answering rail, on the page rather than
                 inside the clock card. Every question type shares this slot. -->
            <div class="practice-aside-hob" aria-hidden="true">
              <img class="practice-rail-sprite" :src="railSprite" alt="" />
            </div>
          </aside>
        </div>
      </template>
    </template>
  </article>
</template>