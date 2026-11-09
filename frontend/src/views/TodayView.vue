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
import { ensureTodayPlan, fetchTodayPlan } from '../api/learning'
import { apiClient } from '../api/client'
import { isApiError } from '../api/errors'
import { isContractFrozen } from '../api/contract-adapter'
import { TODAY_STATUS_LABELS, type TodayPlan } from '../types/learning'
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
                <span class="crumb-task-title">{{ task.title }}</span>
                <span class="crumb-task-value">{{ task.completed }} / {{ task.target }} {{ task.unit }}</span>
              </RouterLink>
            </li>
          </ul>
        </div>

        <aside class="crumb-merged-side crumb-today-side">
          <div class="crumb-merged-ring">
            <GoalRing
              v-if="newWordsTask"
              :value="newWordsTask.completed"
              :max="newWordsTask.target"
              :size="128"
              :stroke="11"
              caption="新词"
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
    </template>
  </article>
</template>

<style scoped>
.crumb-merged {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 250px;
  gap: 28px;
  align-items: start;
  padding: 22px 24px;
  border: 1.5px solid var(--ink, #35240f);
  border-radius: 16px;
  background: var(--surface, #fffdf6);
}
.crumb-merged-main { min-width: 0; display: flex; flex-direction: column; }
.crumb-merged-title {
  font: 800 26px/1.28 "PingFang SC", "Microsoft YaHei", system-ui, sans-serif;
  margin: 6px 0 4px;
  letter-spacing: -0.02em;
}
.crumb-merged-title b { color: var(--accent-ink, #2f6e33); font-weight: 800; }
.today-task-sentence { margin: 0 0 14px; color: var(--muted, #6f5a3d); font-size: 13px; }
.crumb-merged-actions { display: flex; align-items: center; gap: 14px; margin-bottom: 12px; }
.crumb-merged-count { font-size: 12px; color: var(--muted, #6f5a3d); }
.crumb-task-list { list-style: none; margin: 0; padding: 0; }
.crumb-task-list li { border-top: 1px dashed var(--line, #e4d7bd); }
.crumb-task-list li:last-child { border-bottom: 1px dashed var(--line, #e4d7bd); }
.crumb-task-row {
  display: grid;
  grid-template-columns: 22px minmax(0, 1fr) auto;
  align-items: center;
  gap: 10px;
  padding: 10px 4px;
  text-decoration: none;
  color: inherit;
}
.crumb-task-state {
  width: 22px; height: 22px; border-radius: 50%;
  border: 1.5px solid var(--line, #e4d7bd);
  display: grid; place-items: center;
  font-size: 11px; color: var(--muted, #6f5a3d);
}
.crumb-task-row:hover .crumb-task-state { border-color: var(--accent, #3e8e41); }
.crumb-task-title { font-size: 13.5px; }
.crumb-task-list li.is-done .crumb-task-state {
  background: var(--accent-soft, #e3f0e1);
  border-color: var(--accent, #3e8e41);
  color: var(--accent-ink, #2f6e33);
}
.crumb-task-value { font-size: 12.5px; color: var(--muted, #6f5a3d); font-variant-numeric: tabular-nums; }
.crumb-task-list li.is-done .crumb-task-value { color: var(--accent-ink, #2f6e33); }
.crumb-merged-side { display: flex; flex-direction: column; gap: 14px; min-width: 0; }
.crumb-merged-ring { display: flex; flex-direction: column; align-items: center; gap: 8px; }
.crumb-merged-stamp { text-align: center; font-size: 11.5px; color: var(--muted, #6f5a3d); }
.crumb-merged-stamp strong { display: block; color: var(--ink, #35240f); }
.crumb-merged-book {
  display: flex; flex-direction: column; gap: 2px;
  border-top: 1px dashed var(--line, #e4d7bd); padding-top: 12px;
}
.crumb-merged-book strong { font-size: 14px; }
@media (max-width: 900px) {
  .crumb-merged { grid-template-columns: 1fr; gap: 18px; }
}
</style>
