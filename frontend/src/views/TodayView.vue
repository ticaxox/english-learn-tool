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
      to: '/practice',
      cta: '继续学习',
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

const primaryTask = computed(() => todayTasks.value[activeTaskIndex.value] ?? null)
const completedTaskCount = computed(() => todayTasks.value.filter((task) => task.done).length)
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
  <article class="today-page member-today-page today-workspace workspace-page">
    <ContractGate
      v-if="!frozen"
      :endpoints="['GET /learning/today', 'POST /learning/daily-plan/ensure']"
    />

    <LoadingState v-else-if="loading" label="正在读取今日计划…" />

    <section v-else-if="error" class="panel workspace-card member-error-panel">
      <ErrorNotice :error="error" retry-label="重新读取今日计划" @retry="load()" />
      <div v-if="needsActiveWordbook" class="workspace-empty-state">
        <strong>先选择一本词书</strong>
        <p>选好词书后，今天的任务会自动出现。</p>
        <RouterLink class="button workspace-secondary-button" to="/wordbooks">前往词书</RouterLink>
      </div>
    </section>

    <template v-else-if="plan">
      <header class="workspace-page-header">
        <div>
          <p class="workspace-kicker">{{ plan.localDate }} · 今日学习</p>
          <h1>今天先完成这几件事</h1>
          <p class="workspace-page-lead">{{ heroNote }}</p>
        </div>
        <span class="workspace-status">{{ statusLabel }}</span>
      </header>

      <div class="today-workbench">
        <section class="workspace-card today-task-card" aria-labelledby="today-task-title">
          <header class="workspace-section-header">
            <div>
              <h2 id="today-task-title">今日任务</h2>
              <p>按自己的节奏完成，进度会自动保存。</p>
            </div>
            <span class="workspace-meta">{{ completedTaskCount }} / {{ todayTasks.length }} 完成</span>
          </header>

          <div v-if="!plan.wordbook" class="today-inline-notice">
            <span>今天还没有主词书。</span>
            <RouterLink to="/wordbooks">去选择词书</RouterLink>
          </div>

          <ol class="today-task-list" aria-label="今日任务">
            <li
              v-for="(task, index) in todayTasks"
              :key="task.key"
              class="today-tile today-task-row"
              :class="{ 'is-done': task.done, 'is-current': index === activeTaskIndex && !task.done }"
            >
              <span class="today-task-icon"><AppIcon :name="task.icon" /></span>
              <div class="today-task-copy">
                <div class="today-task-titleline">
                  <div>
                    <span class="today-task-label">{{ task.label }}</span>
                    <h3>{{ task.title }}</h3>
                  </div>
                  <span class="today-task-state">{{ task.done ? '已完成' : index === activeTaskIndex ? '现在做' : '待开始' }}</span>
                </div>
                <div class="today-task-progressline">
                  <span class="today-tile__value"><strong>{{ task.completed }}</strong><span>/ {{ task.target }} {{ task.unit }}</span></span>
                  <div
                    class="workspace-progress today-task-progress"
                    role="progressbar"
                    :aria-valuenow="task.completed"
                    :aria-valuemin="0"
                    :aria-valuemax="Math.max(task.target, 1)"
                    :aria-label="`${task.label}进度 ${task.completed} / ${task.target}`"
                  >
                    <span :style="{ width: `${task.percent}%` }"></span>
                  </div>
                </div>
              </div>
            </li>
          </ol>

          <div class="today-task-footer">
            <div>
              <p v-if="plan.extraDueAvailable" class="today-extra-note">还有 {{ plan.extraDueCount }} 个到期词，可加练。</p>
              <p v-else-if="plan.shortfallReason">{{ plan.shortfallReason }}</p>
              <p v-else>完成一项，就离今天的目标更近一点。</p>
            </div>
            <RouterLink
              v-if="primaryTask"
              class="button workspace-primary-button today-primary-action"
              :to="primaryTask.to"
            >
              {{ completedTaskCount === todayTasks.length ? '再练一次' : '继续学习' }} <AppIcon name="arrow" />
            </RouterLink>
          </div>
        </section>

        <aside class="today-summary-aside" aria-label="今日学习摘要">
          <section class="workspace-card today-progress-card">
            <div class="today-progress-heading">
              <div>
                <span class="workspace-kicker">今日进度</span>
                <strong>{{ overallProgress }}%</strong>
              </div>
              <span class="today-progress-ring" :style="{ '--today-progress': `${overallProgress * 3.6}deg` }" aria-hidden="true"></span>
            </div>
            <div
              class="workspace-progress"
              role="progressbar"
              :aria-valuenow="plan.newWords.completed + plan.dueReviews.completed"
              :aria-valuemin="0"
              :aria-valuemax="Math.max(plan.newWords.target + plan.dueReviews.target, 1)"
              aria-label="今日新词与到期复习总进度"
            >
              <span :style="{ width: `${overallProgress}%` }"></span>
            </div>
            <dl class="today-metric-list">
              <div><dt>新词</dt><dd>{{ plan.newWords.completed }} / {{ plan.newWords.target }}</dd></div>
              <div><dt>复习</dt><dd>{{ plan.dueReviews.completed }} / {{ plan.dueReviews.target }}</dd></div>
              <div><dt>学习时间</dt><dd>{{ plan.minutes.active }} / {{ plan.minutes.goal }} 分钟</dd></div>
            </dl>
          </section>

          <section class="workspace-card today-context-card">
            <div class="today-context-row">
              <span class="today-context-label">当前词书</span>
              <strong>{{ plan.wordbook?.name ?? '尚未选择' }}</strong>
              <RouterLink to="/wordbooks">{{ plan.wordbook ? '更换' : '选择' }}</RouterLink>
            </div>
            <div class="today-context-row">
              <span class="today-context-label">AI 练习</span>
              <strong>{{ aiUnavailableLabel }}</strong>
              <RouterLink to="/practice">去看看</RouterLink>
            </div>
            <div class="today-coach-note">
              <span>学习管家</span>
              <p>卡住时，可以先问一句。</p>
              <RouterLink to="/coach">去聊聊</RouterLink>
            </div>
          </section>
        </aside>
      </div>
    </template>
  </article>
</template>