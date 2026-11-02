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
import GoalRing from '../components/ui/GoalRing.vue'
import CrumboMark from '../components/CrumboMark.vue'
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

const newWordsTask = computed(() => todayTasks.value.find((task) => task.key === 'new-words') ?? null)

const activeTaskIndex = computed(() => {
  const index = todayTasks.value.findIndex((task) => !task.done)
  return index === -1 ? todayTasks.value.length - 1 : index
})

const shortfallText = computed(() => plan.value?.shortfallReason ? '今天的目标尚未全部完成。' : '')

const primaryTask = computed(() => todayTasks.value[activeTaskIndex.value] ?? null)
const completedTaskCount = computed(() => todayTasks.value.filter((task) => task.done).length)

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
  <article class="today-page member-today-page crumb-today workspace-page">
    <ContractGate
      v-if="!frozen"
      :endpoints="['GET /learning/today', 'POST /learning/daily-plan/ensure']"
    />

    <LoadingState v-else-if="loading" label="正在读取今日计划…" />

    <section v-else-if="error" class="crumb-state-panel" :class="needsActiveWordbook ? 'crumb-empty-state' : 'crumb-error-panel'">
      <div v-if="needsActiveWordbook" class="crumb-empty-note">
        <CrumboMark size="medium" />
        <div>
          <strong>先选一本词书，路线才能开始。</strong>
          <p>选好词书后，今天的任务会自动出现。</p>
          <RouterLink class="crumb-inline-link" to="/wordbooks">去词书页</RouterLink>
        </div>
      </div>
      <ErrorNotice v-else :error="error" retry-label="重新读取今日计划" @retry="load()" />
    </section>

    <template v-else-if="plan">
      <header class="crumb-today-header">
        <div class="crumb-today-intro">
          <div class="crumb-mascot-lockup">
            <CrumboMark size="large" />
            <div>
              <p class="crumb-brand-kicker">CRUMBTRAIL · 今日学习路线</p>
              <h1>跟着 Crumbo，捡完今天的知识碎屑。</h1>
            </div>
          </div>
          <p class="crumb-today-note">{{ heroNote }}</p>
          <RouterLink
            v-if="primaryTask"
            class="button crumb-primary-action crumb-today-mobile-cta"
            :to="primaryTask.to"
          >
            {{ completedTaskCount === todayTasks.length ? '再走一圈' : '继续学习' }}
            <AppIcon name="arrow" />
          </RouterLink>
        </div>
        <div class="crumb-hero-status">
          <GoalRing
            v-if="newWordsTask"
            :value="newWordsTask.completed"
            :max="newWordsTask.target"
            :size="124"
            :stroke="12"
            caption="新词"
            class="crumb-hero-ring"
          />
          <div class="crumb-today-stamp">
            <span>{{ plan.localDate }}</span>
            <strong>{{ statusLabel }}</strong>
          </div>
        </div>
      </header>

      <div class="crumb-today-layout">
        <section class="crumb-trail-board">
          <header class="crumb-trail-board-head">
            <div>
              <span class="crumb-eyebrow">今日任务 · 面包屑路线</span>
              <h2>今天要捡 {{ todayTasks.length }} 块</h2>
            </div>
            <strong>{{ completedTaskCount }} / {{ todayTasks.length }} 完成</strong>
          </header>

          <div
            class="crumb-route-progress"
            :style="{ '--crumb-progress': `${todayTasks.length ? (completedTaskCount / todayTasks.length) * 100 : 0}%` }"
            role="progressbar"
            :aria-valuenow="completedTaskCount"
            aria-valuemin="0"
            :aria-valuemax="Math.max(todayTasks.length, 1)"
            aria-label="今日面包屑路线进度"
          >
            <span v-for="(task, index) in todayTasks" :key="task.key" :class="{ 'is-done': task.done, 'is-current': index === activeTaskIndex && !task.done }">
              {{ index + 1 }}
            </span>
          </div>

          <div role="list" class="crumb-trail-list" aria-label="今日任务">
            <div role="listitem"
              v-for="(task, index) in todayTasks"
              :key="task.key"
              class="today-tile crumb-stop"
              :class="[`crumb-stop--${task.key}`, { 'is-done': task.done, 'is-current': index === activeTaskIndex && !task.done }]"
            >
              <div class="crumb-stop-marker" aria-hidden="true">
                <span>{{ index + 1 }}</span>
              </div>
              <div class="crumb-stop-card">
                <div class="crumb-stop-heading">
                  <div>
                    <span class="crumb-stop-label">{{ task.eyebrow }} · {{ task.label }}</span>
                    <h3>{{ task.title }}</h3>
                  </div>
                  <span class="crumb-stop-state">{{ task.done ? '已拾取' : index === activeTaskIndex ? '正在走' : '下一站' }}</span>
                </div>
                <div class="crumb-stop-meta">
                  <span class="today-tile__value"><strong>{{ task.completed }}</strong><span>/ {{ task.target }} {{ task.unit }}</span></span>
                  <div
                    class="crumb-task-progress"
                    role="progressbar"
                    :aria-valuenow="task.completed"
                    aria-valuemin="0"
                    :aria-valuemax="Math.max(task.target, 1)"
                    :aria-label="`${task.label}进度 ${task.completed} / ${task.target}`"
                  >
                    <span :style="{ width: `${task.percent}%` }"></span>
                  </div>
                </div>
              </div>
              <AppIcon :name="task.icon" />
            </div>
          </div>

          <footer class="crumb-trail-footer">
            <div class="crumb-guide-note">
              <CrumboMark size="medium" />
              <div>
                <span>CRUMBO 提示</span>
                <p v-if="plan.extraDueAvailable">还有 {{ plan.extraDueCount }} 块到期复习，可以继续捡。</p>
                <p v-else-if="shortfallText">{{ shortfallText }}</p>
                <p v-else>跟着这条路线走，今天就算稳稳落地。</p>
              </div>
            </div>
            <RouterLink
              v-if="primaryTask"
              class="button crumb-primary-action today-primary-action"
              :to="primaryTask.to"
            >
              {{ completedTaskCount === todayTasks.length ? '再走一圈' : '继续学习' }}
              <AppIcon name="arrow" />
            </RouterLink>
          </footer>
        </section>

        <aside class="crumb-today-side">
          <section class="crumb-book-note">
            <span class="crumb-eyebrow">当前词书</span>
            <div class="crumb-book-note-body">
              <span class="crumb-mini-cover">{{ plan.wordbook?.name.slice(0, 1) ?? '?' }}</span>
              <div>
                <h2>{{ plan.wordbook?.name ?? '尚未选择' }}</h2>
                <p>{{ plan.wordbook ? '今天的面包屑都来自这本书。' : '先去词书页选一本。' }}</p>
              </div>
            </div>
            <RouterLink class="crumb-inline-link" to="/wordbooks">{{ plan.wordbook ? '换一本' : '去选择' }}</RouterLink>
          </section>

          <StudyStatsPanel compact />

          <section class="crumb-ai-note">
            <span class="crumb-ai-dot" aria-hidden="true"><AppIcon name="spark" /></span>
            <div>
              <span class="crumb-eyebrow">AI 练习</span>
              <strong>{{ aiUnavailableLabel }}</strong>
              <p>想加练时，再开一轮。</p>
            </div>
            <RouterLink class="crumb-inline-link" to="/practice">去看看</RouterLink>
          </section>
        </aside>
      </div>
    </template>
  </article>
</template>
