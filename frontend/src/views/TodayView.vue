<script setup lang="ts">
/**
 * /overview — today's real learning plan.
 *
 * Every number on this page comes from the server snapshot for local_date.
 * The member redesign changes the visual narrative and information hierarchy,
 * never the source of truth.
 */
import { computed, onMounted, ref } from 'vue'
import { RouterLink } from 'vue-router'
import AppIcon from '../components/AppIcon.vue'
import ErrorNotice from '../components/ErrorNotice.vue'
import LoadingState from '../components/LoadingState.vue'
import ContractGate from '../components/ContractGate.vue'
import StudyStatsPanel from '../components/StudyStatsPanel.vue'
import WhiskerCrumbMark from '../components/WhiskerCrumbMark.vue'
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
const needsActiveWordbook = computed(
  () => isApiError(error.value) && error.value.code === 'ACTIVE_WORDBOOK_REQUIRED',
)
const statusLabel = computed(() =>
  plan.value ? TODAY_STATUS_LABELS[plan.value.status] : null,
)
const aiPractice = computed<AiPracticeSummary | null>(() => plan.value?.aiPractice ?? null)

const aiUnavailableLabel = computed(() => {
  if (!aiPractice.value) return null
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
  if (target <= 0) return 0
  return Math.min(100, Math.round((completed / target) * 100))
}

const todayTasks = computed(() => {
  if (!plan.value) return []
  return [
    {
      key: 'new-words',
      eyebrow: 'WARM-UP',
      label: '新词',
      title: '唤醒今天的新词',
      completed: plan.value.newWords.completed,
      target: plan.value.newWords.target,
      unit: '词',
      icon: 'cards' as const,
      to: '/memory',
      cta: '进入记忆训练',
    },
    {
      key: 'due-reviews',
      eyebrow: 'MEMORY TUNE-UP',
      label: '到期复习',
      title: '把到期词汇重新叫醒',
      completed: plan.value.dueReviews.completed,
      target: plan.value.dueReviews.target,
      unit: '词',
      icon: 'spark' as const,
      to: '/memory',
      cta: '开始复习',
    },
    {
      key: 'learning-minutes',
      eyebrow: 'STEADY MINUTES',
      label: '学习分钟',
      title: '留下今天的学习时间',
      completed: plan.value.minutes.active,
      target: plan.value.minutes.goal,
      unit: '分钟',
      icon: 'today' as const,
      to: '/settings',
      cta: '调整学习目标',
    },
  ].map((task) => ({
    ...task,
    percent: percent(task.completed, task.target),
    done: task.target > 0 && task.completed >= task.target,
  }))
})

const activeTaskIndex = computed(() => {
  const index = todayTasks.value.findIndex((task) => !task.done)
  return index === -1 ? todayTasks.value.length - 1 : index
})

const overallProgress = computed(() => {
  if (!plan.value) return 0
  const completed = plan.value.newWords.completed + plan.value.dueReviews.completed
  const target = plan.value.newWords.target + plan.value.dueReviews.target
  return percent(completed, target)
})

const heroNote = computed(() => {
  if (!plan.value) return '等待服务端生成本日计划。'
  if (!plan.value.wordbook) {
    return '先为学习空间选择一本词书。计划不会在缺少词书来源时凭空生成。'
  }
  if (plan.value.status === 'completed') {
    return `“${plan.value.wordbook.name}” 的今日目标已由服务端标记完成。可以加练，但不必把休息当成退步。`
  }
  const pendingNew = Math.max(plan.value.newWords.target - plan.value.newWords.completed, 0)
  const pendingReview = Math.max(plan.value.dueReviews.target - plan.value.dueReviews.completed, 0)
  return `从 “${plan.value.wordbook.name}” 开始：还有 ${pendingNew} 个新词、${pendingReview} 个到期复习。一次只处理一小口。`
})

async function load(createIfMissing = false): Promise<void> {
  if (!frozen.value) return
  loading.value = true
  error.value = null
  requestId.value = null

  try {
    plan.value = createIfMissing ? await ensureTodayPlan() : await fetchTodayPlan()
    requestId.value = apiClient.getLastRequestId()
  } catch (requestError) {
    plan.value = null
    error.value = requestError
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
  <article class="today-page member-today-page">
    <ContractGate
      v-if="!frozen"
      :endpoints="['GET /learning/today', 'POST /learning/daily-plan/ensure']"
    />

    <LoadingState v-else-if="loading" label="正在读取今日计划…" />

    <section v-else-if="error" class="panel member-error-panel">
      <ErrorNotice :error="error" retry-label="重新读取今日计划" @retry="load()" />
      <div v-if="needsActiveWordbook" class="alert alert-warning">
        <strong>还没有激活的词书</strong>
        <p>激活一本词书后，服务端才会为你生成今日计划。</p>
        <RouterLink class="button" to="/wordbooks">前往词书页</RouterLink>
      </div>
      <p v-if="requestId" class="inline-note">Request ID：<code>{{ requestId }}</code></p>
    </section>

    <template v-else-if="plan">
      <header class="member-hero today-hero">
        <div class="member-hero-copy">
          <p class="eyebrow">THE DAILY EDITION <span>•</span> {{ plan.localDate }}</p>
          <h1><span>A little curious.</span><em>A lot fluent.</em></h1>
          <p class="lead">
            今日计划由服务端根据你的学习档案和词书状态生成。这里展示的是当天固定快照，档案改动从次日起生效。
          </p>
          <div class="member-hero-actions">
            <RouterLink class="button member-primary-button" to="/memory">
              继续今日路线 <AppIcon name="arrow" />
            </RouterLink>
            <RouterLink class="button-secondary" to="/settings">调整学习档案</RouterLink>
            <span class="member-status-stamp">{{ statusLabel }}</span>
          </div>
          <div class="member-hero-progress">
            <div><span>今日目标进度</span><strong>{{ overallProgress }}%</strong></div>
            <div
              class="progress member-progress"
              role="progressbar"
              :aria-valuenow="plan.newWords.completed + plan.dueReviews.completed"
              :aria-valuemin="0"
              :aria-valuemax="Math.max(plan.newWords.target + plan.dueReviews.target, 1)"
              aria-label="今日新词与到期复习总进度"
            >
              <span :style="{ width: `${overallProgress}%` }"></span>
            </div>
          </div>
        </div>

        <aside class="member-concierge-card">
          <div class="member-speech-note">
            <span>MR. WHISKER'S READING OF THE PLAN</span>
            <p>{{ heroNote }}</p>
          </div>
          <div class="member-hero-mascot">
            <WhiskerCrumbMark size="hero" />
            <span class="member-mascot-tag">MR. WHISKER</span>
          </div>
          <div class="member-mini-vitals">
            <div><span>新词</span><strong>{{ plan.newWords.completed }}/{{ plan.newWords.target }}</strong></div>
            <div><span>复习</span><strong>{{ plan.dueReviews.completed }}/{{ plan.dueReviews.target }}</strong></div>
            <div><span>分钟</span><strong>{{ plan.minutes.active }}/{{ plan.minutes.goal }}</strong></div>
          </div>
        </aside>
      </header>

      <section v-if="!plan.wordbook" class="alert alert-warning">
        <strong>当前没有激活词书</strong>
        <p>今日计划缺少词书来源。请先激活一本词书。</p>
        <RouterLink class="button" to="/wordbooks">前往词书页</RouterLink>
      </section>

      <div class="member-dashboard-grid">
        <section class="panel member-trail-panel" aria-labelledby="daily-trail-title">
          <div class="member-section-heading">
            <div>
              <p class="eyebrow">THE DAILY TRAIL <span>•</span> REAL SERVER SNAPSHOT</p>
              <h2 id="daily-trail-title">One curious turn at a time.</h2>
            </div>
            <span class="member-hand-badge">今日共 3 站</span>
          </div>

          <ol class="member-trail-list" aria-label="今日任务">
            <li
              v-for="(task, index) in todayTasks"
              :key="task.key"
              class="today-tile member-trail-stop"
              :class="{ 'is-done': task.done, 'is-current': index === activeTaskIndex && !task.done }"
            >
              <span class="member-trail-node"><AppIcon :name="task.icon" /></span>
              <div class="member-trail-copy">
                <span class="member-stop-eyebrow">{{ task.eyebrow }}</span>
                <p class="today-tile__label">{{ task.label }}</p>
                <h3>{{ task.title }}</h3>
                <p class="member-stop-meta">
                  <span class="today-tile__value"><strong>{{ task.completed }}</strong><span>/ {{ task.target }} {{ task.unit }}</span></span>
                  <span>{{ task.done ? '服务端已完成' : '等待继续' }}</span>
                </p>
                <div
                  class="progress member-task-progress"
                  role="progressbar"
                  :aria-valuenow="task.completed"
                  :aria-valuemin="0"
                  :aria-valuemax="Math.max(task.target, 1)"
                  :aria-label="`${task.label}进度 ${task.completed} / ${task.target}`"
                >
                  <span :style="{ width: `${task.percent}%` }"></span>
                </div>
              </div>
              <RouterLink class="member-stop-action" :to="task.to">
                {{ task.done ? '再次练习' : task.cta }} <AppIcon name="arrow" />
              </RouterLink>
            </li>
          </ol>

          <div class="member-trail-footer">
            <span v-if="plan.shortfallReason">{{ plan.shortfallReason }}</span>
            <span v-else>目标与集合来自服务端；页面不会在本地自行推进复习间隔。</span>
            <p v-if="plan.extraDueAvailable" class="inline-note">
              目标之外还有 {{ plan.extraDueCount }} 个到期词，可继续加练。
            </p>
          </div>
        </section>

        <aside class="member-side-stack">
          <section class="member-wordbook-slip" aria-labelledby="active-wordbook-title">
            <div class="member-slip-topline">
              <span>ACTIVE VOLUME</span>
              <span>{{ plan.wordbook ? 'READY' : 'NONE' }}</span>
            </div>
            <div class="member-book-object" aria-hidden="true">
              <span>WHISKER PRESS</span>
              <strong>{{ plan.wordbook?.name.slice(0, 1) ?? 'W' }}</strong>
              <i>{{ plan.wordbook ? 'OPEN' : 'PICK' }}</i>
            </div>
            <h2 id="active-wordbook-title">{{ plan.wordbook?.name ?? '尚未激活词书' }}</h2>
            <p>
              {{ plan.wordbook
                ? '当前词书由服务端学习计划引用。词条数量与学习状态在词书工作区读取。'
                : '今日计划没有词书来源；不会在本地补造词汇集合。' }}
            </p>
            <RouterLink class="member-text-link" to="/wordbooks">Browse the word shelf <AppIcon name="arrow" /></RouterLink>
          </section>

          <StudyStatsPanel />
        </aside>
      </div>

      <div class="member-lower-grid">
        <section class="panel member-ai-card" aria-live="polite">
          <div class="member-ai-mark"><AppIcon name="spark" /></div>
          <div>
            <p class="eyebrow">AI PRACTICE</p>
            <h2>{{ aiUnavailableLabel }}</h2>
            <p v-if="plan.aiPractice.message">{{ plan.aiPractice.message }}</p>
            <p v-else class="inline-note">当前状态由服务端返回，不会在本地把不可用能力标记为已完成。</p>
          </div>
          <RouterLink class="button-secondary" to="/practice">前往练习室</RouterLink>
        </section>

        <section class="member-margin-note">
          <span class="member-note-pin" aria-hidden="true"></span>
          <p class="eyebrow">PLAN MARGIN NOTE</p>
          <p>修改学习档案后，新目标从次日起生效；今日快照保持不变。</p>
          <RouterLink class="member-text-link" to="/settings">调整学习偏好 <AppIcon name="arrow" /></RouterLink>
        </section>
      </div>

      <footer v-if="plan.calculationVersion || plan.generatedAt" class="panel member-plan-meta">
        <span v-if="plan.generatedAt">计划生成时间：{{ plan.generatedAt }}</span>
        <span v-if="plan.calculationVersion">版本：<code>{{ plan.calculationVersion }}</code></span>
      </footer>
    </template>
  </article>
</template>
