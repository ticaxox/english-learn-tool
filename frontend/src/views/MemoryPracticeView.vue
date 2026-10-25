<script setup lang="ts">
/**
 * /memory — three-module training workspace.
 *
 * Session, question, grading and queue all come from the server. This page
 * only renders what the server returned and forwards learner actions with
 * idempotency keys. Heartbeats run while a session is open.
 */
import { computed, onMounted, ref } from 'vue'
import { RouterLink, useRoute } from 'vue-router'
import ErrorNotice from '../components/ErrorNotice.vue'
import LoadingState from '../components/LoadingState.vue'
import ContractGate from '../components/ContractGate.vue'
import FlashcardTrainer from '../components/FlashcardTrainer.vue'
import ChoiceTrainer from '../components/ChoiceTrainer.vue'
import SpellingTrainer from '../components/SpellingTrainer.vue'
import { fetchMemoryConfig } from '../api/learning'
import { isContractFrozen } from '../api/contract-adapter'
import { isApiError } from '../api/errors'
import { useMemorySession } from '../composables/useMemorySession'
import { useStudyHeartbeat } from '../composables/useStudyHeartbeat'
import {
  MEMORY_MODULES,
  MEMORY_MODULE_LABELS,
  type MemoryConfig,
  type MemoryModule,
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
const loadingConfig = ref(false)
const selectedModule = ref<MemoryModule | null>(null)

const session = useMemorySession()

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

async function begin(module: MemoryModule, existingSessionId?: string): Promise<void> {
  selectedModule.value = module
  try {
    await session.open(module, existingSessionId)
    heartbeat.start()
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
}

function restart(): void {
  session.reset()
  heartbeat.stop()
  selectedModule.value = null
  void loadConfig()
}

onMounted(async () => {
  await loadConfig()
  if (challengeSessionId.value && challengeModule.value) {
    await begin(challengeModule.value, challengeSessionId.value)
  }
})
</script>

<template>
  <article class="memory-page">
    <header class="memory-hero">
      <div>
        <p class="eyebrow">记忆训练</p>
        <h1>翻卡 · 选择 · 拼写</h1>
        <p class="lead">
          翻卡、选择或拼写，选一种方式开始复习。
        </p>
      </div>
      <div v-if="session.hasSession.value" class="memory-hero__actions">
        <span class="memory-hero__state" :class="`memory-hero__state--${heartbeat.state.value}`">
          {{ heartbeat.state.value === 'active' ? '计时中' : '已暂停' }}
        </span>
        <button class="button-secondary button-small" type="button" @click="endSession">结束本次</button>
      </div>
    </header>

    <div v-if="challengeId" class="inline-note challenge-memory-banner">
      <strong>当前记忆训练来自每日闯关节点。</strong>
      完成后返回地图即可。
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

    <section v-else-if="configError" class="panel">
      <ErrorNotice :error="configError" retry-label="重新读取配置" @retry="loadConfig" />
    </section>

    <template v-else>
      <!-- Module picker -->
      <section v-if="showModulePicker" class="panel">
        <h2>选择训练方式</h2>
        <div v-if="activeModules.length === 0" class="alert alert-warning">
          <strong>没有可用的训练方式</strong>
          <p>当前档案未启用任何记忆模块，请先在设置中至少开启一种。</p>
          <RouterLink class="button" to="/settings">前往学习设置</RouterLink>
        </div>
        <div v-else class="module-grid">
          <button
            v-for="module in activeModules"
            :key="module"
            class="module-card"
            type="button"
            @click="begin(module)"
          >
            <span class="module-card__title">{{ MEMORY_MODULE_LABELS[module] }}</span>
            <span class="module-card__hint">
              {{ module === 'flashcard' ? '看词回忆释义' : module === 'choice' ? '选出正确释义' : '按提示拼写' }}
            </span>
          </button>
        </div>
      </section>

      <!-- In-session error -->
      <section v-if="session.lastError.value" class="panel">
        <ErrorNotice
          :error="session.lastError.value"
          retry-label="重试当前操作"
          @retry="resume"
        />
        <div v-if="needsActiveWordbook" class="alert alert-warning">
          <strong>还没有激活的词书</strong>
          <p>激活词书后才能开始记忆训练。</p>
          <RouterLink class="button" to="/wordbooks">前往词书页</RouterLink>
        </div>
      </section>

      <!-- Feedback strip -->
      <section v-if="session.feedback.value" class="study-feedback" aria-live="polite">
        <strong>{{ session.feedback.value.headline }}</strong>
        <p v-if="session.feedback.value.detail">{{ session.feedback.value.detail }}</p>
        <p v-if="session.feedback.value.requeued" class="inline-note">这张卡会在稍后重新出现。</p>
      </section>

      <!-- Active question -->
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

      <!-- Finished -->
      <section v-if="session.finished.value" class="panel">
        <h2>本次队列已完成</h2>
        <p>本轮复习完成，辛苦了。</p>
        <div class="button-row">
          <button class="button" type="button" @click="restart">返回训练选择</button>
          <RouterLink class="button-secondary" to="/overview">查看今日进度</RouterLink>
          <RouterLink class="button-secondary" to="/memory/mistakes">查看错词</RouterLink>
        </div>
      </section>

      <!-- Resume prompt -->
      <section
        v-if="showModulePicker && selectedModule && session.lastError.value"
        class="panel"
      >
        <button class="button" type="button" @click="resume">继续上一次会话</button>
      </section>

      <p v-if="heartbeat.lastError.value" class="inline-note">
        学习计时暂时未同步，卡片操作不受影响。
      </p>
    </template>
  </article>
</template>
