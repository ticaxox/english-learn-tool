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
import FlashcardTrainer from '../components/FlashcardTrainer.vue'
import ChoiceTrainer from '../components/ChoiceTrainer.vue'
import SpellingTrainer from '../components/SpellingTrainer.vue'
import { fetchMemoryConfig, fetchTodayPlan } from '../api/learning'
import { isContractFrozen } from '../api/contract-adapter'
import { isApiError } from '../api/errors'
import { useMemorySession } from '../composables/useMemorySession'
import { useStudyHeartbeat } from '../composables/useStudyHeartbeat'
import { timerLimitFromQuery, useSessionTimer } from '../composables/useSessionTimer'
import {
  MEMORY_MODULES,
  MEMORY_MODULE_LABELS,
  type MemoryConfig,
  type MemoryModule,
  type TodayPlan,
} from '../types/learning'
import PracticeTopBar from '../components/PracticeTopBar.vue'
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

async function answerChoice(questionId: string, optionId: string): Promise<void> {
  await session.answerChoice(questionId, optionId)
  heartbeat.markInteraction()
}

async function answerSpelling(questionId: string, answer: string): Promise<void> {
  await session.answerSpelling(questionId, answer)
  heartbeat.markInteraction()
}

async function master(questionId: string): Promise<void> {
  await session.markMastered(questionId)
  heartbeat.markInteraction()
}

async function endSession(): Promise<void> {
  const confirmed = window.confirm('结束本次会话后，未完成的目标不会被算作完成。确定结束吗？')
  if (!confirmed) {
    return
  }
  await session.endSession()
  heartbeat.stop()
  timer.stop()
}

function restart(): void {
  session.reset()
  heartbeat.stop()
  timer.reset()
  selectedModule.value = null
  void loadConfig()
}

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
    <PracticeTopBar mode="memory" :active="selectedModule ?? challengeModule ?? null" />

    <header v-if="!session.hasSession.value && !session.finished.value" class="workspace-page-header">
      <div>
        <p class="workspace-kicker">记忆训练</p>
        <h1>选一种方式开始复习</h1>
        <p class="workspace-page-lead">翻卡、选择或拼写，都从今天的真实队列开始。</p>
      </div>
    </header>

    <header v-else class="memory-stage-header">
      <div>
        <p class="eyebrow">记忆练习</p>
        <h1>{{ selectedModule ? MEMORY_MODULE_LABELS[selectedModule] : '记忆练习' }}</h1>
      </div>
      <div class="memory-session-actions">
        <span class="workspace-status" :class="`memory-timer--${heartbeat.state.value}`">
          {{ timer.running.value ? `${timerLimit > 0 ? '倒计时' : '正计时'} ${timer.label.value}` : '已暂停' }}
        </span>
        <button class="button-secondary button-small" type="button" @click="endSession">结束本次</button>
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

    <div v-else class="memory-workbench-grid">
      <section class="workspace-card memory-main-card">
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
            </div>
          </header>

          <div v-if="activeModules.length === 0" class="workspace-inline-banner memory-no-modules">
            <span>还没有启用训练方式。</span>
            <RouterLink to="/settings">去设置开启</RouterLink>
          </div>
          <div class="module-grid memory-action-grid">
            <button
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
            </button>
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

        <section v-if="session.feedback.value" class="study-feedback" aria-live="polite">
          <strong>{{ session.feedback.value.headline }}</strong>
          <p v-if="session.feedback.value.detail">{{ session.feedback.value.detail }}</p>
          <p v-if="session.feedback.value.requeued" class="inline-note">这张卡会在稍后重新出现。</p>
        </section>

        <LoadingState v-if="session.busy.value && !session.question.value" label="正在提交…" />

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

        <section v-if="session.finished.value" class="workspace-complete-state">
          <span class="workspace-status">本轮完成</span>
          <h2>这次复习完成了</h2>
          <p>可以回到今日进度，或继续查看错词。</p>
          <div class="button-row">
            <button class="button workspace-primary-button" type="button" @click="restart">再练一轮</button>
            <RouterLink class="button workspace-secondary-button" to="/overview">查看今日进度</RouterLink>
            <RouterLink class="button workspace-secondary-button" to="/memory/mistakes">查看错词</RouterLink>
          </div>
        </section>

        <section v-if="showModulePicker && selectedModule && session.lastError.value" class="memory-resume-row">
          <button class="button workspace-secondary-button" type="button" @click="resume">继续上一次会话</button>
        </section>

        <p v-if="heartbeat.lastError.value" class="workspace-inline-note">
          学习计时暂时未同步，卡片操作不受影响。
        </p>
      </section>

      <aside class="workspace-card memory-context-card" aria-label="当前学习信息">
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
  </article>
</template>