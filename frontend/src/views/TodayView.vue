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
import ChallengeView from './ChallengeView.vue'
import GoalRing from '../components/ui/GoalRing.vue'
import CrumboMark from '../components/CrumboMark.vue'
import ErrorNotice from '../components/ErrorNotice.vue'
import LoadingState from '../components/LoadingState.vue'
import ContractGate from '../components/ContractGate.vue'
import StudyStatsPanel from '../components/StudyStatsPanel.vue'
import GameHud from '../components/GameHud.vue'
import BadgeWall from '../components/BadgeWall.vue'
import WeeklyReport from '../components/WeeklyReport.vue'
import { useGamification } from '../composables/useGamification'
import { ensureTodayPlan, fetchTodayPlan } from '../api/learning'
import { apiClient } from '../api/client'
import { isApiError } from '../api/errors'
import { isContractFrozen } from '../api/contract-adapter'
import { TODAY_STATUS_LABELS, type TodayPlan } from '../types/learning'
import '../learning.css'

const gamification = useGamification()
const crumboMood = computed(() => gamification.crumboMood.value)
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
const todayTaskSentence = computed(() => {
  const phrases = todayTasks.value.map((task) => {
    if (task.key === 'new-words') return `学习 ${task.target} 个新词`
    if (task.key === 'due-reviews') return `完成 ${task.target} 个到期复习`
    if (task.key === 'learning-minutes') return `积累 ${task.target} 分钟学习时间`
    return `${task.title} ${task.target} ${task.unit}`
  })
  return phrases.length ? `今天要${phrases.join('，')}。` : ''
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
/** The ring tracks whichever quest the learner should do next. */
const ringTask = computed(() => primaryTask.value ?? todayTasks.value[0] ?? null)
const completedTaskCount = computed(() => todayTasks.value.filter((task) => task.done).length)

const crumboTip = computed(() => {
  const remaining = todayTasks.value.filter((task) => !task.done)
  if (remaining.length === 0) return '今天的任务都完成了，可以再走一圈，也可以明天再来。'
  const next = remaining[0]
  const left = Math.max(0, next.target - next.completed)
  if (next.key === 'due-reviews') return `还差 ${left} 个到期复习，先清掉它们最划算。`
  if (next.key === 'new-words') return `还有 ${left} 个新词没学，学完今天的词就齐了。`
  if (next.key === 'learning-minutes') return `再学 ${left} 分钟就攒够今天的时间了。`
  return `接下来做「${next.title}」。`
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
  void gamification.load()
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
        <CrumboMark size="medium" :mood="crumboMood" />
        <div>
          <strong>先选一本词书，路线才能开始。</strong>
          <p>选好词书后，今天的任务会自动出现。</p>
          <RouterLink class="crumb-inline-link" to="/wordbooks">去词书页</RouterLink>
        </div>
      </div>
      <ErrorNotice v-else :error="error" retry-label="重新读取今日计划" @retry="load()" />
    </section>

    <template v-else-if="plan">
      <GameHud />

      <section class="crumb-today-board crumb-trail-board crumb-merged">
        <div class="crumb-merged-main">
          <span class="crumb-eyebrow">今日学习 · 今日任务</span>
          <h1 class="crumb-merged-title">
            下一步：<b>{{ primaryTask ? primaryTask.title : '今天的任务已完成' }}</b>
          </h1>
          <p class="today-task-sentence">{{ todayTaskSentence }}</p>

          <div class="crumb-merged-actions">
            <RouterLink
              v-if="primaryTask"
              class="button crumb-primary-action crumb-board-cta"
              :to="primaryTask.to"
            >
              {{ completedTaskCount === todayTasks.length ? '再走一圈' : '继续学习' }}
              <AppIcon name="arrow" />
            </RouterLink>
            <span class="crumb-merged-count">{{ completedTaskCount }} / {{ todayTasks.length }} 完成</span>
          </div>

          <ul class="crumb-task-list" aria-label="今日任务进度">
            <li v-for="(task, index) in todayTasks" :key="task.key" :class="{ 'is-done': task.done }">
              <RouterLink :to="task.to" class="crumb-task-row">
                <span class="crumb-task-state" aria-hidden="true">{{ task.done ? '✓' : index + 1 }}</span>
                <span class="crumb-task-body">
                  <span class="crumb-task-title">{{ task.title }}</span>
                  <span class="crumb-task-bar" aria-hidden="true">
                    <span :style="{ width: `${task.percent}%` }"></span>
                  </span>
                </span>
                <span class="crumb-task-value">{{ task.completed }} / {{ task.target }} {{ task.unit }}</span>
              </RouterLink>
            </li>
          </ul>

          <div class="crumb-tip">
            <CrumboMark size="small" :mood="crumboMood" />
            <p>{{ crumboTip }}</p>
          </div>
        </div>

        <aside class="crumb-merged-side crumb-today-side">
          <div class="crumb-merged-ring">
            <GoalRing
              v-if="ringTask"
              :value="ringTask.completed"
              :max="ringTask.target"
              :size="128"
              :stroke="11"
              :caption="ringTask.label"
            />
            <div class="crumb-merged-stamp">
              <span>{{ plan.localDate }}</span>
              <strong>{{ statusLabel }}</strong>
            </div>
          </div>

          <div class="crumb-merged-book">
            <span class="crumb-eyebrow">当前词书</span>
            <strong>{{ plan.wordbook?.name ?? '尚未选择' }}</strong>
            <RouterLink class="crumb-inline-link" to="/wordbooks">
              {{ plan.wordbook ? '换一本' : '去选择' }}
            </RouterLink>
          </div>

          <StudyStatsPanel compact />
        </aside>
      </section>

      <ChallengeView embedded />

      <section class="today-extras">
        <WeeklyReport />
        <BadgeWall />
      </section>
    </template>
  </article>
</template>
