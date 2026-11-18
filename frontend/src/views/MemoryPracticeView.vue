<script setup lang="ts">
/**
 * /memory — three-module training workspace.
 *
 * Session, question, grading and queue all come from the server. This page
 * only renders what the server returned and forwards learner actions with
 * idempotency keys. Heartbeats run while a session is open.
 */
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { RouterLink, useRoute, useRouter } from 'vue-router'
import AppIcon from '../components/AppIcon.vue'
import ErrorNotice from '../components/ErrorNotice.vue'
import LoadingState from '../components/LoadingState.vue'
import ContractGate from '../components/ContractGate.vue'
import FlashcardTrainer from '../components/FlashcardTrainer.vue'
import ChoiceTrainer from '../components/ChoiceTrainer.vue'
import SpellingTrainer from '../components/SpellingTrainer.vue'
import LevelUpOverlay from '../components/LevelUpOverlay.vue'
import { hobActions, illustration } from '../assets/halloween'
import ShelfPicker from '../components/ShelfPicker.vue'
import { fetchMemoryConfig, fetchTodayPlan, resetMemoryProgress } from '../api/learning'
import { isContractFrozen } from '../api/contract-adapter'
import { isApiError } from '../api/errors'
import { useMemorySession } from '../composables/useMemorySession'
import { useGamification } from '../composables/useGamification'
import { useStudyHeartbeat } from '../composables/useStudyHeartbeat'
import { useToast } from '../composables/useToast'
import { sparkBurst, shake } from '../composables/useMotion'
import { timerLimitFromQuery, useSessionTimer } from '../composables/useSessionTimer'
import {
  MEMORY_MODULES,
  MEMORY_MODULE_LABELS,
  type MemoryConfig,
  type MemoryModule,
  type TodayPlan,
} from '../types/learning'
import '../learning.css'
import ArtImage from '../components/ArtImage.vue'

const route = useRoute()
const router = useRouter()
const props = withDefaults(defineProps<{ embedded?: boolean }>(), { embedded: false })
const frozen = computed(() => isContractFrozen())
const challengeSessionId = computed(() => typeof route.query.sessionId === 'string' ? route.query.sessionId : null)
const challengeId = computed(() => typeof route.query.challengeId === 'string' ? route.query.challengeId : null)
const challengeModule = computed<MemoryModule | null>(() => {
  const value = route.query.module
  return value === 'flashcard' || value === 'choice' || value === 'spelling' ? value : null
})

const config = ref<MemoryConfig | null>(null)
const configError = ref<unknown>(null)
const todayPlan = ref<TodayPlan | null>(null)
const planError = ref<unknown>(null)
const planLoading = ref(false)
const loadingConfig = ref(false)
const selectedModule = ref<MemoryModule | null>(null)

const session = useMemorySession()

const timer = useSessionTimer()
const toast = useToast()
const resetting = ref(false)
const timerLimit = ref<number>(timerLimitFromQuery(route.query.timer) ?? 0)

function startClock(): void {
  timer.start(timerLimit.value > 0 ? timerLimit.value : null)
}

function onTimerLimitChange(event: Event): void {
  timerLimit.value = Number((event.target as HTMLSelectElement).value) || 0
}

const heartbeat = useStudyHeartbeat({
  enabled: () => session.hasSession.value && !session.finished.value,
  sessionId: () => session.sessionId.value,
})

const activeModules = computed<MemoryModule[]>(() => {
  if (!config.value) {
    return []
  }
  return MEMORY_MODULES.filter((module) => config.value?.[module].enabled)
})

const needsActiveWordbook = computed(
  () => isApiError(session.lastError.value) && session.lastError.value.code === 'ACTIVE_WORDBOOK_REQUIRED',
)

const dueRemaining = computed(() => {
  if (!todayPlan.value) return null
  return Math.max(todayPlan.value.dueReviews.target - todayPlan.value.dueReviews.completed, 0)
})

/** Session position, from the server's summary rather than local counting. */
const sessionTotal = computed(() => session.total.value ?? 0)
const cardsDone = computed(() => Math.max(0, sessionTotal.value - (session.question.value?.remaining ?? 0)))
/**
 * `remaining` drops the moment a card is graded, not when the queue moves on.
 * While the verdict is held the learner is still looking at the card just
 * answered, so the rail must not step to the next number until it does.
 */
const cardIndex = computed(() => {
  const position = verdict.value ? cardsDone.value : cardsDone.value + 1
  return Math.max(1, Math.min(sessionTotal.value, position))
})
watch(
  () => session.question.value?.questionId,
  () => { flashRevealed.value = false },
)

const progressPercent = computed(() => {
  if (sessionTotal.value <= 0) return 0
  return Math.round((cardsDone.value / sessionTotal.value) * 100)
})

const showModulePicker = computed(() => !session.hasSession.value && !session.finished.value)

async function loadConfig(): Promise<void> {
  if (!frozen.value) {
    return
  }
  loadingConfig.value = true
  configError.value = null
  try {
    config.value = await fetchMemoryConfig()
  } catch (error) {
    configError.value = error
  } finally {
    loadingConfig.value = false
  }
}

async function loadTodayPlan(): Promise<void> {
  planLoading.value = true
  try {
    todayPlan.value = await fetchTodayPlan()
    planError.value = null
  } catch (error) {
    todayPlan.value = null
    planError.value = error
  } finally {
    planLoading.value = false
  }
}
async function begin(module: MemoryModule, existingSessionId?: string): Promise<void> {
  selectedModule.value = module
  resetRun()
  try {
    await session.open(module, existingSessionId)
    heartbeat.start()
    startClock()
  } catch {
    // Error already captured by the session composable for display.
  }
}

async function resume(): Promise<void> {
  if (!selectedModule.value) {
    return
  }
  try {
    await session.open(selectedModule.value)
    heartbeat.start()
    if (!timer.running.value) startClock()
  } catch {
    // handled by the composable
  }
}

/** The flip happens inside the card; the rail needs to hear about it. */
function onFlashReveal(): void {
  flashRevealed.value = true
  const current = session.question.value
  if (current) void session.recordReveal(current.questionId)
}

async function rateFlashcard(questionId: string, rating: 'again' | 'good'): Promise<void> {
  await session.rateFlashcard(questionId, rating)
  heartbeat.markInteraction()
  if (rating === 'good') sparkBurst(document.querySelector('.memory-main-card'), 8)
}

interface Verdict {
  correct: boolean
  headline: string
}

const MAX_HEARTS = 5

/**
 * The beat after an answer. A miss holds the card — the wrong plate stays red,
 * the answer's plate goes green, and the rail offers the only way on. A hit
 * does not hold anything: the plate flashes green and the next card lands by
 * itself, which is the whole point of a drill.
 */
const verdict = ref<Verdict | null>(null)
const reveal = ref<{ word: string | null; phonetic: string | null; partOfSpeech: string | null; meaning: string | null } | null>(null)
const combo = ref(0)
const bestCombo = ref(0)
const hearts = ref(MAX_HEARTS)
/** The flip card asks for a rating, not an answer, so nothing there costs
    a life — its rail shows the count and the clock only. */
const showsLives = computed(() => (selectedModule.value ?? session.module.value) !== 'flashcard')
const railSprite = computed(() => hobActions[selectedModule.value ?? session.module.value ?? ''] ?? hobActions.flashcard)
/** This run's own tally — the server keeps the durable record. */
const runCorrect = ref(0)
const runWrong = ref(0)
const showSummary = ref(false)
/** Mirrors the flashcard's own flip so the rail can offer ratings for it. */
const flashRevealed = ref(false)

const runAccuracy = computed(() => {
  const graded = runCorrect.value + runWrong.value
  return graded > 0 ? Math.round((runCorrect.value / graded) * 100) : 0
})

/** How long a right answer stays green before the next card lands. */
const RIGHT_ANSWER_BEAT_MS = 720

let advanceTimer: number | null = null

function clearAdvance(): void {
  if (advanceTimer !== null) {
    window.clearTimeout(advanceTimer)
    advanceTimer = null
  }
}

function scheduleAdvance(): void {
  clearAdvance()
  advanceTimer = window.setTimeout(() => {
    advanceTimer = null
    void continueAfterVerdict()
  }, RIGHT_ANSWER_BEAT_MS)
}

onBeforeUnmount(clearAdvance)

function resetRun(): void {
  clearAdvance()
  verdict.value = null
  reveal.value = null
  combo.value = 0
  bestCombo.value = 0
  hearts.value = MAX_HEARTS
  runCorrect.value = 0
  runWrong.value = 0
  showSummary.value = false
}

function showVerdict(correct: boolean, headline: string): void {
  if (correct) {
    combo.value += 1
    bestCombo.value = Math.max(bestCombo.value, combo.value)
    runCorrect.value += 1
  } else {
    combo.value = 0
    runWrong.value += 1
    hearts.value = Math.max(0, hearts.value - 1)
  }
  verdict.value = { correct, headline }
}

function rememberForReview(entry: { word: string | null; phonetic: string | null; partOfSpeech: string | null; meaning: string | null }): void {
  reveal.value = entry
}

async function answerChoice(questionId: string, optionId: string): Promise<void> {
  const question = session.question.value
  const feedback = await session.answerChoice(questionId, optionId)
  heartbeat.markInteraction()
  if (!feedback || feedback.gradedCorrect === null) {
    if (feedback) await session.advance()
    return
  }
  const correct = feedback.gradedCorrect
  if (correct) {
    reveal.value = null
  } else {
    // The card takes the hit before the correction lands.
    void nextTick(() => shake(document.querySelector('.choice-list') ?? document.querySelector('.study-card')))
    rememberForReview({
      word: feedback.correctAnswer,
      phonetic: question?.kind === 'choice' ? question.phonetic : null,
      partOfSpeech: question?.kind === 'choice' ? question.partOfSpeech : null,
      meaning: question?.kind === 'choice' ? question.prompt : null,
    })
  }
  showVerdict(correct, feedback.headline)
  // Right answers are not held: the plate goes green, then the queue moves.
  if (correct) scheduleAdvance()
}

async function answerSpelling(questionId: string, answer: string): Promise<void> {
  const question = session.question.value
  const feedback = await session.answerSpelling(questionId, answer)
  heartbeat.markInteraction()
  if (!feedback || feedback.gradedCorrect === null) {
    if (feedback) await session.advance()
    return
  }
  const correct = feedback.gradedCorrect
  if (correct) {
    reveal.value = null
  } else {
    void nextTick(() => shake(document.querySelector('.study-card')))
    rememberForReview({
      word: feedback.correctAnswer,
      phonetic: question?.kind === 'spelling' ? question.phonetic : null,
      partOfSpeech: question?.kind === 'spelling' ? question.partOfSpeech : null,
      meaning: question?.kind === 'spelling' ? question.definition : null,
    })
  }
  showVerdict(correct, feedback.headline)
  if (correct) scheduleAdvance()
}

/** Leaving the pause: clear the marks and pull the next card. */
async function continueAfterVerdict(): Promise<void> {
  clearAdvance()
  verdict.value = null
  reveal.value = null
  // Hearts are the only thing that can end a run early; otherwise the queue
  // decides. Zero hearts ends it on the spot, the way a run in a game does.
  if (hearts.value <= 0) {
    try {
      await session.endSession()
    } catch {
      // The summary still reports what happened even if the close call fails.
      showSummary.value = true
    }
    return
  }
  await session.advance()
}

async function master(questionId: string): Promise<void> {
  await session.markMastered(questionId)
  heartbeat.markInteraction()
}

const endConfirmOpen = ref(false)
const ending = ref(false)
const endError = ref<unknown>(null)

function endSession(): void {
  endError.value = null
  endConfirmOpen.value = true
}

async function confirmEndSession(): Promise<void> {
  if (ending.value) return
  ending.value = true
  endError.value = null
  try {
    await session.endSession()
    heartbeat.stop()
    timer.stop()
    endConfirmOpen.value = false
  } catch (error) {
    endError.value = error
  } finally {
    ending.value = false
  }
}

async function resetTodayProgress(): Promise<void> {
  if (resetting.value) return
  const confirmed = window.confirm(
    '重置今天的记忆进度？今天已完成的记录会被清空，今天的单词会重新回到队列。',
  )
  if (!confirmed) return
  resetting.value = true
  try {
    const result = await resetMemoryProgress()
    restart()
    await loadTodayPlan()
    toast.success('已重置今天的进度', `${result.wordsReset} 个单词已回到队列。`)
  } catch {
    toast.error('重置失败', '请稍后重试。')
  } finally {
    resetting.value = false
  }
}

/** Same module, fresh run. */
function startAgain(): void {
  const module = selectedModule.value ?? session.module.value
  showSummary.value = false
  restart()
  if (module) void begin(module)
}

/** Back to the shelf of books. */
function backToPicker(): void {
  showSummary.value = false
  restart()
}

function restart(): void {
  if (props.embedded) {
    // The hub owns the module picker, so a finished session returns to it.
    void router.replace({ name: 'practice' })
    return
  }
  resetRun()
  session.reset()
  heartbeat.stop()
  timer.reset()
  selectedModule.value = null
  void loadConfig()
}

// A finished run lands on its own summary first — the numbers are the point of
// finishing. Leaving the card and being dropped back on a picker skips that.
watch(
  () => session.finished.value,
  (finished) => {
    if (!finished) return
    timer.stop()
    heartbeat.stop()
    if (props.embedded) {
      void router.replace({ name: 'practice' })
      return
    }
    showSummary.value = true
  },
)

/** A finished run is worth the same celebration a submitted practice gets. */
const gamification = useGamification()
const levelUp = ref<{ level: number; title: string } | null>(null)
let levelBefore = 0

watch(showSummary, async (open) => {
  if (!open) return
  await gamification.load()
  const now = gamification.progress.value
  if (!now) return
  if (levelBefore > 0 && now.level.level > levelBefore) {
    levelUp.value = { level: now.level.level, title: now.level.title }
  }
  levelBefore = now.level.level
})

onMounted(async () => {
  void gamification.load().then(() => {
    levelBefore = gamification.progress.value?.level.level ?? 0
  })
  await Promise.all([loadConfig(), loadTodayPlan()])
  if (challengeSessionId.value && challengeModule.value) {
    await begin(challengeModule.value, challengeSessionId.value)
  } else if (challengeModule.value && !session.hasSession.value) {
    await begin(challengeModule.value)
  }
})

// The practice top bar switches modes by changing the query.
watch(challengeModule, async (module, previous) => {
  if (!module || module === previous) return
  await begin(module)
})
</script>

<template>
  <article class="memory-page memory-workbench workspace-page">
    <header
      v-if="!props.embedded && !session.hasSession.value && !session.finished.value"
      class="workspace-page-header"
    >
      <div>
        <p class="workspace-kicker">记忆训练</p>
        <h1>选一种方式开始复习</h1>
        <p class="workspace-page-lead">翻卡、选择或拼写，都从今天的真实队列开始。</p>
      </div>
    </header>

    <div v-if="challengeId" class="workspace-inline-banner challenge-memory-banner">
      <span>本次训练来自每日闯关节点。</span>
      <RouterLink :to="`/challenges/${challengeId}`">返回今日闯关</RouterLink>
    </div>

    <ContractGate
      v-if="!frozen"
      :endpoints="[
        'GET /memory/config',
        'POST /memory/sessions',
        'GET /memory/sessions/{id}',
        'POST /memory/sessions/{id}/events',
        'POST /memory/sessions/{id}/complete',
        'PATCH /memory/words/{state_id}/master',
        'POST /learning/heartbeat',
      ]"
      title="记忆训练暂时不可用"
    />

    <LoadingState v-else-if="loadingConfig" label="正在读取记忆配置…" />

    <section v-else-if="configError" class="workspace-card workspace-error-card">
      <ErrorNotice :error="configError" retry-label="重新读取配置" @retry="loadConfig" />
    </section>

    <template v-else>
      <!-- No strip above the card: where you are and the way out both live in
        the rail, and the card is the only thing at the top of the page. -->

      <!-- The payoff: what this run actually earned, then one way forward. -->
      <section v-if="showSummary" class="lesson-summary" aria-labelledby="lesson-summary-title">
        <ArtImage class="lesson-summary__art" :set="illustration.result" />
        <div class="lesson-summary__body">
          <p class="lesson-summary__kicker">本轮完成</p>
          <h2 id="lesson-summary-title">{{ bestCombo >= 5 ? '手感正热' : '又清掉一轮' }}</h2>
          <dl class="lesson-summary__stats">
            <div><dt>答对</dt><dd>{{ runCorrect }}</dd></div>
            <div><dt>答错</dt><dd>{{ runWrong }}</dd></div>
            <div><dt>正确率</dt><dd>{{ runAccuracy }}%</dd></div>
            <div><dt>连击</dt><dd>{{ bestCombo }}</dd></div>
          </dl>
          <div class="lesson-summary__actions">
            <DivButton class="button" type="button" @click="startAgain">再来一轮</DivButton>
            <DivButton class="button-secondary" type="button" @click="backToPicker">换一种练法</DivButton>
          </div>
        </div>
      </section>

      <div v-else class="memory-workbench-grid" :class="{ 'is-session': Boolean(session.question.value) || session.finished.value }">
        <section class="workspace-card memory-main-card" :class="{ 'is-picker': showModulePicker }">
        <template v-if="showModulePicker && !props.embedded">
          <header class="workspace-section-header">
            <div>
              <h2>今天练什么</h2>
              <p>选一个入口，直接进入当前队列。</p>
            </div>
            <div class="memory-picker-tools">
              <label class="memory-timer-control">
                <span>计时</span>
                <select :value="timerLimit" @change="onTimerLimitChange">
                  <option :value="0">不限（正计时）</option>
                  <option :value="5">5 分钟</option>
                  <option :value="10">10 分钟</option>
                  <option :value="15">15 分钟</option>
                  <option :value="20">20 分钟</option>
                  <option :value="30">30 分钟</option>
                </select>
              </label>
              <span class="workspace-meta">{{ activeModules.length }} 种可用</span>
              <DivButton class="memory-reset-link" type="button" :disabled="resetting" @click="resetTodayProgress">
                重置今日进度
              </DivButton>
            </div>
          </header>

          <div v-if="activeModules.length === 0" class="workspace-inline-banner memory-no-modules">
            <span>还没有启用训练方式。</span>
            <RouterLink to="/settings">去设置开启</RouterLink>
          </div>
          <ShelfPicker
            :modules="MEMORY_MODULES"
            :enabled="activeModules"
            :labels="MEMORY_MODULE_LABELS"
            @pick="begin"
          />
          <LevelUpOverlay
    v-if="levelUp"
    :level="levelUp.level"
    :title="levelUp.title"
    @close="levelUp = null"
  />
</template>

        <section v-if="session.lastError.value" class="memory-session-error">
          <ErrorNotice
            :error="session.lastError.value"
            retry-label="重试当前操作"
            @retry="resume"
          />
          <div v-if="needsActiveWordbook" class="workspace-empty-state">
            <strong>还没有激活的词书</strong>
            <p>激活词书后才能开始记忆训练。</p>
            <RouterLink class="button workspace-secondary-button" to="/wordbooks">前往词书</RouterLink>
          </div>
        </section>


        <LoadingState v-if="session.busy.value && !session.question.value" label="正在提交…" />

        <!-- The card is the only thing on the page, so the change of question
          is the transition: the answered card leaves upwards, the next one
          rises into place. -->
        <Transition name="memory-swap" mode="out-in">
          <div :key="session.question.value?.questionId ?? 'empty'" class="memory-card-slot">
            <FlashcardTrainer
              v-if="session.question.value?.kind === 'flashcard'"
              :question="session.question.value"
              :disabled="session.busy.value || Boolean(verdict)"
              :show-rating="false"
              @reveal="onFlashReveal"
              @rate="(rating) => rateFlashcard(session.question.value!.questionId, rating)"
              @master="() => master(session.question.value!.questionId)"
            />

            <ChoiceTrainer
              v-else-if="session.question.value?.kind === 'choice'"
              :question="session.question.value"
              :disabled="session.busy.value || Boolean(verdict)"
              :outcome="verdict ? (verdict.correct ? 'correct' : 'wrong') : null"
              :correct-label="verdict && !verdict.correct ? reveal?.word ?? null : null"
              :missed="Boolean(verdict && !verdict.correct)"
              :hit="Boolean(verdict && verdict.correct)"
              @answer="(optionId) => answerChoice(session.question.value!.questionId, optionId)"
              @continue="continueAfterVerdict"
            />

            <SpellingTrainer
              v-else-if="session.question.value?.kind === 'spelling'"
              :question="session.question.value"
              :disabled="session.busy.value || Boolean(verdict)"
              :outcome="verdict ? (verdict.correct ? 'correct' : 'wrong') : null"
              :result="verdict && !verdict.correct ? reveal?.word ?? null : null"
              :missed="Boolean(verdict && !verdict.correct)"
              :hit="Boolean(verdict && verdict.correct)"
              @answer="(value) => answerSpelling(session.question.value!.questionId, value)"
              @continue="continueAfterVerdict"
            />
          </div>
        </Transition>

        <section v-if="showModulePicker && selectedModule && session.lastError.value" class="memory-resume-row">
          <DivButton class="button workspace-secondary-button" type="button" @click="resume">继续上一次会话</DivButton>
        </section>

        <p v-if="heartbeat.lastError.value" class="workspace-inline-note">
          学习计时暂时未同步，卡片操作不受影响。
        </p>
      </section>

      <aside v-if="session.hasSession.value || session.finished.value" class="memory-session-side" aria-label="本次训练">
        <div class="workspace-card memory-session-rail">
          <!-- One readout: the lives over the count, the clock beside it. No
            labels — the hearts and a clock need none. The flip card has no
            lives to lose, so its rail starts at the count. -->
          <div class="memory-rail-head">
            <span v-if="showsLives" class="memory-rail-heartrow" :aria-label="`剩余 ${hearts} 颗心`">
              <svg v-for="n in MAX_HEARTS" :key="n" viewBox="0 0 24 24" aria-hidden="true"
                   :class="{ 'is-empty': n > hearts }">
                <path d="M12 20s-7-4.4-7-9.1A4 4 0 0 1 12 8a4 4 0 0 1 7 2.9C19 15.6 12 20 12 20Z" />
              </svg>
            </span>
            <div class="memory-rail-progress">
              <span class="memory-rail-count">{{ cardIndex }}/{{ sessionTotal || '—' }}</span>
              <span class="memory-rail-clock" :class="`memory-timer--${heartbeat.state.value}`">
                {{ timer.running.value ? timer.label.value : '已暂停' }}
              </span>
            </div>
            <span class="memory-rail-track" aria-hidden="true">
              <span :style="{ width: `${progressPercent}%` }"></span>
            </span>
            <p v-if="!session.question.value" class="memory-rail-state">本轮已完成</p>
          </div>

          <DivButton
            v-if="!session.finished.value"
            class="button-secondary memory-rail-end"
            type="button"
            @click="endSession"
          >
            结束本次
          </DivButton>
          <p v-else class="memory-rail-state">本轮训练已结束，成绩会记入今日进度。</p>

          <!-- Hob sits at the foot of the rail, inside the same card, so the
               clock card and the question card share one height. -->
          <div class="memory-aside-hob" aria-hidden="true">
            <img class="memory-rail-sprite" :src="railSprite" alt="" />
          </div>
        </div>

        <!-- What you make of the card is the one thing to do after it turns
          over, so it stands on its own under the rail instead of sitting in a
          labelled slot inside it. -->
        <div
          v-if="flashRevealed && session.question.value?.kind === 'flashcard' && !session.finished.value"
          class="memory-ratings"
        >
          <DivButton
            class="memory-rating memory-rating--again"
            type="button"
            :disabled="session.busy.value || Boolean(verdict)"
            @click="rateFlashcard(session.question.value!.questionId, 'again')"
          >
            无印象
          </DivButton>
          <DivButton
            class="memory-rating memory-rating--good"
            type="button"
            :disabled="session.busy.value || Boolean(verdict)"
            @click="rateFlashcard(session.question.value!.questionId, 'good')"
          >
            有印象
          </DivButton>
          <DivButton
            class="memory-rating memory-rating--mastered"
            type="button"
            :disabled="session.busy.value || Boolean(verdict)"
            @click="master(session.question.value!.questionId)"
          >
            已记住
          </DivButton>
        </div>
      </aside>

      <aside v-else-if="!props.embedded" class="workspace-card memory-context-card" aria-label="当前学习信息">
        <div>
          <p class="workspace-kicker">当前词书</p>
          <strong>{{ planLoading ? '正在读取…' : todayPlan?.wordbook?.name ?? (planError ? '暂未读取' : '尚未选择') }}</strong>
          <RouterLink to="/wordbooks">更换词书</RouterLink>
        </div>
        <dl class="memory-context-stats">
          <div><dt>今日到期</dt><dd>{{ dueRemaining ?? '—' }}</dd></div>
          <div><dt>可用方式</dt><dd>{{ activeModules.length }}</dd></div>
          <div><dt>训练状态</dt><dd>{{ session.hasSession.value ? '进行中' : '未开始' }}</dd></div>
        </dl>
        <RouterLink class="memory-settings-link" to="/settings">调整训练与目标 <AppIcon name="settings" /></RouterLink>
      </aside>
      </div>
    </template>

    <div v-if="endConfirmOpen" class="dialog-backdrop" @click.self="endConfirmOpen = false">
      <section class="dialog-card memory-end-dialog" role="dialog" aria-modal="true" aria-labelledby="memory-end-title">
        <header class="dialog-heading">
          <div>
            <p class="eyebrow">本次训练</p>
            <h2 id="memory-end-title">结束本次训练？</h2>
          </div>
        </header>
        <p class="field-hint">未完成的目标不会被算作完成，已记住的词会保留。</p>
        <ErrorNotice v-if="endError" :error="endError" :show-retry="false" />
        <div class="button-row">
          <DivButton class="button-danger" type="button" :disabled="ending" @click="confirmEndSession">
            {{ ending ? '正在结束…' : '结束本次' }}
          </DivButton>
          <DivButton class="button-secondary" type="button" :disabled="ending" @click="endConfirmOpen = false">继续学习</DivButton>
        </div>
      </section>
    </div>
  </article>
</template>