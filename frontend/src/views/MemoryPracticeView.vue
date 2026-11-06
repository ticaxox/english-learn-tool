<script setup lang="ts">
/**
 * /memory — three-module training workspace.
 *
 * Session, question, grading and queue all come from the server. This page
 * only renders what the server returned and forwards learner actions with
 * idempotency keys. Heartbeats run while a session is open.
 */
import { computed, onMounted, ref, watch } from 'vue'
import { RouterLink, useRoute } from 'vue-router'
import AppIcon from '../components/AppIcon.vue'
import ErrorNotice from '../components/ErrorNotice.vue'
import LoadingState from '../components/LoadingState.vue'
import ContractGate from '../components/ContractGate.vue'
import SpeakButton from '../components/SpeakButton.vue'
import FlashcardTrainer from '../components/FlashcardTrainer.vue'
import ChoiceTrainer from '../components/ChoiceTrainer.vue'
import SpellingTrainer from '../components/SpellingTrainer.vue'
import { fetchMemoryConfig, fetchTodayPlan, resetMemoryProgress } from '../api/learning'
import { isContractFrozen } from '../api/contract-adapter'
import { isApiError } from '../api/errors'
import { useMemorySession } from '../composables/useMemorySession'
import { useStudyHeartbeat } from '../composables/useStudyHeartbeat'
import { useToast } from '../composables/useToast'
import { timerLimitFromQuery, useSessionTimer } from '../composables/useSessionTimer'
import {
  MEMORY_MODULES,
  MEMORY_MODULE_LABELS,
  type MemoryConfig,
  type MemoryModule,
  type TodayPlan,
} from '../types/learning'
import '../learning.css'

const route = useRoute()
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
const cardIndex = computed(() => Math.min(sessionTotal.value, cardsDone.value + 1))
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

async function rateFlashcard(questionId: string, rating: 'again' | 'good'): Promise<void> {
  await session.rateFlashcard(questionId, rating)
  heartbeat.markInteraction()
}

interface WrongCard {
  word: string
  phonetic: string | null
  partOfSpeech: string | null
  meaning: string
  kind: 'choice' | 'spelling'
  typed: string | null
}

function typedLetterIsWrong(card: WrongCard, index: number): boolean {
  const typed = card.typed ?? ''
  const correct = card.word
  return (typed[index] ?? '').toLowerCase() !== (correct[index] ?? '').toLowerCase()
}

const wrongCard = ref<WrongCard | null>(null)

async function answerChoice(questionId: string, optionId: string): Promise<void> {
  const question = session.question.value
  const feedback = await session.answerChoice(questionId, optionId)
  heartbeat.markInteraction()
  if (feedback?.gradedCorrect === false) {
    wrongCard.value = {
      word: feedback.correctAnswer ?? '',
      phonetic: question?.kind === 'choice' ? question.phonetic : null,
      partOfSpeech: question?.kind === 'choice' ? question.partOfSpeech : null,
      meaning: question?.kind === 'choice' ? question.prompt : '',
      kind: 'choice',
      typed: null,
    }
    return
  }
  if (feedback) await session.advance()
}

async function answerSpelling(questionId: string, answer: string): Promise<void> {
  const question = session.question.value
  const feedback = await session.answerSpelling(questionId, answer)
  heartbeat.markInteraction()
  if (feedback?.gradedCorrect === false) {
    wrongCard.value = {
      word: feedback.correctAnswer ?? '',
      phonetic: question?.kind === 'spelling' ? question.phonetic : null,
      partOfSpeech: question?.kind === 'spelling' ? question.partOfSpeech : null,
      meaning: question?.kind === 'spelling' ? question.definition : '',
      kind: 'spelling',
      typed: answer,
    }
    return
  }
  if (feedback) await session.advance()
}

async function continueAfterWrong(): Promise<void> {
  wrongCard.value = null
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

function restart(): void {
  wrongCard.value = null
  session.reset()
  heartbeat.stop()
  timer.reset()
  selectedModule.value = null
  void loadConfig()
}

// A finished or ended session returns straight to the module picker.
watch(
  () => session.finished.value,
  (finished) => {
    if (finished) restart()
  },
)

onMounted(async () => {
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
    <header v-if="!session.hasSession.value && !session.finished.value" class="workspace-page-header">
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
      <p
        v-if="session.hasSession.value || session.finished.value"
        class="memory-session-kicker"
      >
        记忆练习
      </p>

      <div class="memory-workbench-grid" :class="{ 'is-session': Boolean(session.question.value) || session.finished.value }">
        <section class="workspace-card memory-main-card" :class="{ 'is-picker': showModulePicker }">
        <template v-if="showModulePicker">
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
          <div class="module-grid memory-action-grid">
            <DivButton
              v-for="module in MEMORY_MODULES"
              :key="module"
              class="module-card memory-action-card"
              :class="[
                `memory-action-card--${module}`,
                { 'is-disabled': !activeModules.includes(module) },
              ]"
              type="button"
              :disabled="!activeModules.includes(module)"
              @click="begin(module)"
            >
              <span class="memory-action-icon"><AppIcon :name="module === 'spelling' ? 'star' : module === 'choice' ? 'cards' : 'book'" /></span>
              <span class="memory-action-copy">
                <strong class="module-card__title">{{ MEMORY_MODULE_LABELS[module] }}</strong>
                <span class="module-card__hint">
                  {{ module === 'flashcard' ? '看词回忆释义' : module === 'choice' ? '选出正确释义' : '按提示拼写' }}
                </span>
              </span>
              <span class="memory-action-status" :class="{ 'is-disabled': !activeModules.includes(module) }">
                <strong>{{ activeModules.includes(module) ? (dueRemaining === null ? '读取中' : `${dueRemaining} 个待复习`) : '未启用' }}</strong>
                <small>{{ activeModules.includes(module) ? '可开始' : '到设置开启' }}</small>
              </span>
              <AppIcon :name="activeModules.includes(module) ? 'arrow' : 'lock'" />
            </DivButton>
          </div>
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

        <section v-if="wrongCard" class="memory-wrong-detail" aria-live="polite">
          <div class="workspace-card memory-wrong-detail__card">
            <div class="memory-wrong-detail__grid">
              <div class="memory-wrong-detail__word">
                <div class="memory-wrong-detail__word-row">
                <h2 v-if="wrongCard.kind !== 'spelling'">{{ wrongCard.word }}</h2>
                <h2 v-else class="memory-wrong-detail__word-letters">
                  <span
                    v-for="(letter, index) in wrongCard.word"
                    :key="index"
                    :class="{ 'is-wrong': typedLetterIsWrong(wrongCard, index) }"
                  >{{ letter }}</span>
                </h2>
                <SpeakButton class="memory-wrong-detail__speak" :text="wrongCard.word" />
                </div>
                <p v-if="wrongCard.phonetic" class="memory-wrong-detail__phonetic">{{ wrongCard.phonetic }}</p>
              </div>
              <div class="memory-wrong-detail__side">
                <p class="memory-wrong-detail__meaning">
                  <span v-if="wrongCard.partOfSpeech" class="memory-wrong-detail__pos">{{ wrongCard.partOfSpeech }}</span>
                  <span class="memory-wrong-detail__definition">{{ wrongCard.meaning }}</span>
                </p>
              </div>
            </div>
          </div>
          <DivButton class="button memory-wrong-detail__continue" type="button" @click="continueAfterWrong">
            继续
          </DivButton>
        </section>

        <FlashcardTrainer
          v-else-if="session.question.value?.kind === 'flashcard'"
          :question="session.question.value"
          :disabled="session.busy.value"
          @reveal="() => session.recordReveal(session.question.value!.questionId)"
          @rate="(rating) => rateFlashcard(session.question.value!.questionId, rating)"
          @master="() => master(session.question.value!.questionId)"
        />

        <ChoiceTrainer
          v-else-if="session.question.value?.kind === 'choice'"
          :question="session.question.value"
          :disabled="session.busy.value"
          @answer="(optionId) => answerChoice(session.question.value!.questionId, optionId)"
        />

        <SpellingTrainer
          v-else-if="session.question.value?.kind === 'spelling'"
          :question="session.question.value"
          :disabled="session.busy.value"
          @answer="(value) => answerSpelling(session.question.value!.questionId, value)"
        />

        <section v-if="showModulePicker && selectedModule && session.lastError.value" class="memory-resume-row">
          <DivButton class="button workspace-secondary-button" type="button" @click="resume">继续上一次会话</DivButton>
        </section>

        <p v-if="heartbeat.lastError.value" class="workspace-inline-note">
          学习计时暂时未同步，卡片操作不受影响。
        </p>
      </section>

      <aside v-if="session.hasSession.value || session.finished.value" class="workspace-card memory-session-rail" aria-label="本次训练">
        <div class="memory-rail-head">
          <p v-if="session.question.value" class="memory-rail-remaining">
            本轮剩余 <strong>{{ session.question.value.remaining }}</strong> 张
          </p>
          <p v-else class="memory-rail-remaining">本轮已完成</p>
          <div class="memory-rail-progress">
            <span class="memory-rail-count">第 {{ cardIndex }} / {{ sessionTotal || '—' }} 张</span>
            <span class="memory-rail-track" aria-hidden="true">
              <span :style="{ width: `${progressPercent}%` }"></span>
            </span>
          </div>
        </div>

        <div class="memory-rail-block">
          <span class="memory-rail-label">本次用时</span>
          <span class="workspace-status memory-rail-clock" :class="`memory-timer--${heartbeat.state.value}`">
            {{ timer.running.value ? `${timerLimit > 0 ? '倒计时' : '正计时'} ${timer.label.value}` : '已暂停' }}
          </span>
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
      </aside>

      <aside v-else class="workspace-card memory-context-card" aria-label="当前学习信息">
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