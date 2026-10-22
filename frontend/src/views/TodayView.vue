<script setup lang="ts">
/**
 * /overview — today's real learning plan.
 *
 * Every number on this page comes from the server snapshot for `local_date`.
 * When the contract is not frozen, or the backend reports
 * ACTIVE_WORDBOOK_REQUIRED, the page says so plainly instead of inventing a plan.
 */
import { computed, onMounted, ref } from 'vue'
import { RouterLink } from 'vue-router'
import ErrorNotice from '../components/ErrorNotice.vue'
import LoadingState from '../components/LoadingState.vue'
import ContractGate from '../components/ContractGate.vue'
import StudyStatsPanel from '../components/StudyStatsPanel.vue'
import { ensureTodayPlan, fetchTodayPlan } from '../api/learning'
import { apiClient } from '../api/client'
import { isApiError } from '../api/errors'
import { isContractFrozen } from '../api/contract-adapter'
import {
  TODAY_STATUS_LABELS,
  type AiPracticeSummary,
  type TodayPlan,
} from '../types/learning'
import '../learning.css'

const plan = ref<TodayPlan | null>(null)
const loading = ref(false)
const error = ref<unknown>(null)
const requestId = ref<string | null>(null)

const frozen = computed(() => isContractFrozen())

/** Backend signals "no active wordbook" with a dedicated code. */
const needsActiveWordbook = computed(
  () => isApiError(error.value) && error.value.code === 'ACTIVE_WORDBOOK_REQUIRED',
)

const statusLabel = computed(() =>
  plan.value ? TODAY_STATUS_LABELS[plan.value.status] : null,
)

const aiPractice = computed<AiPracticeSummary | null>(() => plan.value?.aiPractice ?? null)

const aiUnavailableLabel = computed(() => {
  if (!aiPractice.value) {
    return null
  }
  switch (aiPractice.value.state) {
    case 'not_available':
      return 'AI 练习尚未开放'
    case 'not_configured':
      return 'AI 练习尚未配置'
    case 'available':
      return 'AI 练习可用'
    default:
      return 'AI 练习状态未知'
  }
})

function percent(completed: number, target: number): number {
  if (target <= 0) {
    return 0
  }
  return Math.min(100, Math.round((completed / target) * 100))
}

async function load(createIfMissing = false): Promise<void> {
  if (!frozen.value) {
    return
  }
  loading.value = true
  error.value = null
  requestId.value = null

  try {
    plan.value = createIfMissing ? await ensureTodayPlan() : await fetchTodayPlan()
    requestId.value = apiClient.getLastRequestId()
  } catch (requestError) {
    plan.value = null
    error.value = requestError
    // A missing plan for today is expected on the first visit; the server
    // creates the snapshot idempotently via /daily-plan/ensure.
    if (isApiError(requestError) && requestError.status === 404) {
      try {
        plan.value = await ensureTodayPlan()
        error.value = null
        requestId.value = apiClient.getLastRequestId()
      } catch (ensureError) {
        plan.value = null
        error.value = ensureError
        requestId.value = apiClient.getLastRequestId()
      }
    }
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  void load()
})
</script>

<template>
  <article class="today-page">
    <header class="today-hero">
      <div>
        <p class="eyebrow">今日学习</p>
        <h1>今天的学习计划</h1>
        <p class="lead">
          计划由服务端按你的学习档案与词书状态生成。目标与集合在当天保持不变，档案改动次日生效。
        </p>
      </div>
      <div v-if="plan" class="today-hero__badge">
        <span class="today-hero__date">{{ plan.localDate }}</span>
        <span class="today-hero__status">{{ statusLabel }}</span>
      </div>
    </header>

    <ContractGate
      v-if="!frozen"
      :endpoints="['GET /learning/today', 'POST /learning/daily-plan/ensure']"
    />

    <LoadingState v-else-if="loading" label="正在读取今日计划…" />

    <section v-else-if="error" class="panel">
      <ErrorNotice :error="error" retry-label="重新读取今日计划" @retry="load()" />
      <div v-if="needsActiveWordbook" class="alert alert-warning">
        <strong>还没有激活的词书</strong>
        <p>激活一本词书后，服务端才会为你生成今日计划。</p>
        <RouterLink class="button" to="/wordbooks">前往词书页</RouterLink>
      </div>
      <p v-if="requestId" class="inline-note">Request ID：<code>{{ requestId }}</code></p>
    </section>

    <template v-else-if="plan">
      <section v-if="!plan.wordbook" class="alert alert-warning">
        <strong>当前没有激活词书</strong>
        <p>今日计划缺少词书来源。请先激活一本词书。</p>
        <RouterLink class="button" to="/wordbooks">前往词书页</RouterLink>
      </section>

      <section class="today-grid" aria-label="今日任务">
        <div class="today-tile">
          <p class="today-tile__label">新词</p>
          <p class="today-tile__value">
            <strong>{{ plan.newWords.completed }}</strong>
            <span>/ {{ plan.newWords.target }}</span>
          </p>
          <div
            class="progress"
            role="progressbar"
            :aria-valuenow="plan.newWords.completed"
            :aria-valuemin="0"
            :aria-valuemax="Math.max(plan.newWords.target, 1)"
            :aria-label="`新词进度 ${plan.newWords.completed} / ${plan.newWords.target}`"
          >
            <span :style="{ width: `${percent(plan.newWords.completed, plan.newWords.target)}%` }"></span>
          </div>
        </div>

        <div class="today-tile">
          <p class="today-tile__label">到期复习</p>
          <p class="today-tile__value">
            <strong>{{ plan.dueReviews.completed }}</strong>
            <span>/ {{ plan.dueReviews.target }}</span>
          </p>
          <div
            class="progress"
            role="progressbar"
            :aria-valuenow="plan.dueReviews.completed"
            :aria-valuemin="0"
            :aria-valuemax="Math.max(plan.dueReviews.target, 1)"
            :aria-label="`到期复习进度 ${plan.dueReviews.completed} / ${plan.dueReviews.target}`"
          >
            <span :style="{ width: `${percent(plan.dueReviews.completed, plan.dueReviews.target)}%` }"></span>
          </div>
        </div>

        <div class="today-tile">
          <p class="today-tile__label">学习分钟</p>
          <p class="today-tile__value">
            <strong>{{ plan.minutes.active }}</strong>
            <span>/ {{ plan.minutes.goal }} 分钟</span>
          </p>
          <div
            class="progress"
            role="progressbar"
            :aria-valuenow="plan.minutes.active"
            :aria-valuemin="0"
            :aria-valuemax="Math.max(plan.minutes.goal, 1)"
            :aria-label="`学习分钟进度 ${plan.minutes.active} / ${plan.minutes.goal}`"
          >
            <span :style="{ width: `${percent(plan.minutes.active, plan.minutes.goal)}%` }"></span>
          </div>
        </div>
      </section>

      <section class="panel">
        <h2>开始学习</h2>
        <p v-if="plan.shortfallReason" class="alert alert-warning">
          {{ plan.shortfallReason }}
        </p>
        <div class="button-row">
          <RouterLink class="button" to="/memory">进入记忆训练</RouterLink>
          <RouterLink class="button-secondary" to="/settings">调整学习档案</RouterLink>
        </div>
        <p v-if="plan.extraDueAvailable" class="inline-note">
          目标之外还有新的到期词，可继续加练；它们不会改变今天的固定目标。
        </p>
        <p class="inline-note">
          修改学习档案后新目标从次日起生效，今日快照保持不变。
        </p>
      </section>

      <section class="panel" aria-live="polite">
        <h2>AI 练习</h2>
        <p class="today-ai" :class="`today-ai--${plan.aiPractice.state}`">
          <strong>{{ aiUnavailableLabel }}</strong>
        </p>
        <p v-if="plan.aiPractice.message">{{ plan.aiPractice.message }}</p>
        <p v-else class="inline-note">
          AI 练习尚未实现，本页如实显示状态，不会把它标记为已完成。
        </p>
      </section>

      <StudyStatsPanel />

      <footer v-if="plan.calculationVersion || plan.generatedAt" class="panel today-meta">
        <p v-if="plan.generatedAt" class="inline-note">计划生成时间：{{ plan.generatedAt }}</p>
        <p v-if="plan.calculationVersion" class="inline-note">
          计划版本：<code>{{ plan.calculationVersion }}</code>
        </p>
      </footer>
    </template>
  </article>
</template>
