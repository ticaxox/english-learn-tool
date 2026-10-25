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
      return 'AI 练习准备中'
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
      eyebrow: '热身',
      label: '新词',
      title: '学习今天的新词',
      completed: plan.value.newWords.completed,
      target: plan.value.newWords.target,
      unit: '词',
      icon: 'cards' as const,
      to: '/memory',
      cta: '开始学习',
    },
    {
      key: 'due-reviews',
      eyebrow: '复习',
      label: '到期复习',
      title: '完成到期复习',
      completed: plan.value.dueReviews.completed,
      target: plan.value.dueReviews.target,
      unit: '词',
      icon: 'spark' as const,
      to: '/memory',
      cta: '开始复习',
    },
    {
      key: 'learning-minutes',
      eyebrow: '专注',
      label: '学习分钟',
      title: '积累学习时间',
      completed: plan.value.minutes.active,
      target: plan.value.minutes.goal,
      unit: '分钟',
      icon: 'today' as const,
      to: '/settings',
      cta: '调整目标',
    },
  ].filter((task) => task.target > 0 || task.key === 'learning-minutes').map((task) => ({
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
  if (!plan.value) return '正在准备今天的学习计划。'
  if (!plan.value.wordbook) {
    return '先选一本词书，再开始今天的学习。'
  }
  if (plan.value.status === 'completed') {
    return "“" + plan.value.wordbook.name + "” 今日目标已完成。想继续也可以加练。"
  }
  const pendingNew = Math.max(plan.value.newWords.target - plan.value.newWords.completed, 0)
  const pendingReview = Math.max(plan.value.dueReviews.target - plan.value.dueReviews.completed, 0)
  const pending = []
  if (pendingNew > 0) pending.push(pendingNew + ' 个新词')
  if (pendingReview > 0) pending.push(pendingReview + ' 个复习')
  return pending.length ? '今天还有 ' + pending.join('、') + '。慢慢来。' : '今天的任务已经完成。'
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
        <p>选一本词书，就能开始今天的学习。</p>
        <RouterLink class="button" to="/wordbooks">前往词书页</RouterLink>
      </div>

    </section>

    <template v-else-if="plan">
      <header class="member-hero today-hero">
        <div class="member-hero-copy">
          <p class="eyebrow">今日学习 <span>•</span> {{ plan.localDate }}</p>
          <h1><span>今天，</span><em>学一点。</em></h1>
          <p class="lead">
            按今天的计划，一步一步来。
          </p>
          <div class="member-hero-actions">
            <RouterLink class="button member-primary-button" to="/memory">
              继续学习 <AppIcon name="arrow" />
            </RouterLink>
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
            <span>管家提示</span>
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
              <p class="eyebrow">今日任务</p>
              <h2 id="daily-trail-title">先完成这一件。</h2>
            </div>
            <span class="member-hand-badge">今日共 {{ todayTasks.length }} 站</span>
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
                  <span>{{ task.done ? '已完成' : '进行中' }}</span>
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
            <span v-else>按顺序完成即可，进度会自动保存。</span>
            <p v-if="plan.extraDueAvailable" class="inline-note">
              目标之外还有 {{ plan.extraDueCount }} 个到期词，可继续加练。
            </p>
          </div>
        </section>

        <aside class="member-side-stack">
          <section class="member-wordbook-slip" aria-labelledby="active-wordbook-title">
            <div class="member-slip-topline">
              <span>当前词书</span>
              <span>{{ plan.wordbook ? '可用' : '未选择' }}</span>
            </div>
            <div class="member-book-object" aria-hidden="true">
              <span>WHISKER PRESS</span>
              <strong>{{ plan.wordbook?.name.slice(0, 1) ?? 'W' }}</strong>
              <i>{{ plan.wordbook ? '打开' : '选择' }}</i>
            </div>
            <h2 id="active-wordbook-title">{{ plan.wordbook?.name ?? '尚未激活词书' }}</h2>
            <p>
              {{ plan.wordbook
                ? '今天从这本词书开始。'
                : '选择一本词书开始学习。' }}
            </p>
            <RouterLink class="member-text-link" to="/wordbooks">更换词书 <AppIcon name="arrow" /></RouterLink>
          </section>

          <StudyStatsPanel />
        </aside>
      </div>

      <div class="member-lower-grid">
        <section class="panel member-ai-card" aria-live="polite">
          <div class="member-ai-mark"><AppIcon name="spark" /></div>
          <div>
            <p class="eyebrow">AI 练习</p>
            <h2>{{ aiUnavailableLabel }}</h2>
            <p v-if="aiPractice?.state === 'available'" class="inline-note">现在可以做一次短练习。</p>
            <p v-else class="inline-note">准备好后就来试试。</p>
          </div>
          <RouterLink class="button-secondary" to="/practice">去练习</RouterLink>
        </section>

        <section class="member-margin-note">
          <span class="member-note-pin" aria-hidden="true"></span>
          <p class="eyebrow">小提示</p>
          <p>调整目标后，新计划从明天开始。</p>
          <RouterLink class="member-text-link" to="/settings">调整目标 <AppIcon name="arrow" /></RouterLink>
        </section>
      </div>

    </template>
  </article>
</template>
