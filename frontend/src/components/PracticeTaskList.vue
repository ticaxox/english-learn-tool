<script setup lang="ts">
/**
 * The live practice task list: sessions and pre-generated sets in one place.
 *
 * Rows only show summary text; clicking a row opens a floating dialog with the
 * available actions. The settings page no longer owns a separate background
 * task manager.
 */
import { computed, onMounted, ref } from 'vue'
import { RouterLink, useRouter } from 'vue-router'
import AppIcon from './AppIcon.vue'
import TypeMark from './TypeMark.vue'
import ErrorNotice from './ErrorNotice.vue'
import LoadingState from './LoadingState.vue'
import {
  createPracticeSession,
  deletePracticeSession,
  listRecentPracticeSessions,
  regeneratePracticeSession,
  PRACTICE_SOURCE_LABELS,
  PRACTICE_TYPE_LABELS,
  type PracticeSessionSummary,
  type PracticeSource,
  type PracticeType,
} from '../api/practice'
import {
  deleteBackgroundTask,
  listBackgroundTasks,
  retryBackgroundTask,
  type BackgroundTask,
} from '../api/background-tasks'
import { useToast } from '../composables/useToast'

const props = withDefaults(defineProps<{
  limit?: number
  showTabs?: boolean
  heading?: boolean
}>(), {
  limit: 0,
  showTabs: false,
  heading: true,
})

interface TaskRow {
  key: string
  kind: 'session' | 'pool'
  id: string
  practiceType: PracticeType
  source: PracticeSource | null
  status: 'generating' | 'ready' | 'submitted' | 'failed' | 'cancelled'
  count: number
  score: number | null
  errorCode: string | null
  createdAt: string
}

const router = useRouter()
const toast = useToast()
const sessions = ref<PracticeSessionSummary[]>([])
const poolTasks = ref<BackgroundTask[]>([])
const loading = ref(false)
const error = ref<unknown>(null)
const busyId = ref<string | null>(null)
const selected = ref<TaskRow | null>(null)

const STATUS_LABELS: Record<TaskRow['status'], string> = {
  generating: '生成中',
  ready: '待练习',
  submitted: '已完成',
  failed: '生成失败',
  cancelled: '已取消',
}

const rows = computed<TaskRow[]>(() => {
  const merged: TaskRow[] = [
    ...sessions.value.map((row) => ({
      key: `session-${row.id}`,
      kind: 'session' as const,
      id: row.id,
      practiceType: row.practiceType,
      source: row.source,
      status: row.status,
      count: row.questionCount,
      score: row.score,
      errorCode: row.errorCode,
      createdAt: row.createdAt,
    })),
    ...poolTasks.value.map((task) => ({
      key: `pool-${task.id}`,
      kind: 'pool' as const,
      id: task.id,
      practiceType: task.practiceType,
      source: null,
      status: task.status === 'ready' ? ('ready' as const) : task.status,
      count: task.questionCount,
      score: null,
      errorCode: task.errorCode,
      createdAt: task.createdAt,
    })),
  ]
  merged.sort((left, right) => right.createdAt.localeCompare(left.createdAt))
  return props.limit > 0 ? merged.slice(0, props.limit) : merged
})

function sourceLabel(row: TaskRow): string {
  if (row.kind === 'pool') return '预生成套题'
  return row.source ? PRACTICE_SOURCE_LABELS[row.source] : '专项练习'
}

/** Rows are named by when they were created, not by a generic source label. */
function taskName(row: TaskRow): string {
  const date = new Date(row.createdAt)
  if (Number.isNaN(date.getTime())) return '练习'
  const day = `${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`
  const time = `${String(date.getHours()).padStart(2, '0')}:${String(date.getMinutes()).padStart(2, '0')}`
  return `${day} ${time}`
}

function statusLabel(row: TaskRow): string {
  return STATUS_LABELS[row.status] ?? row.status
}

function canOpen(row: TaskRow): boolean {
  return ['ready', 'generating', 'submitted'].includes(row.status)
}

function canRetry(row: TaskRow): boolean {
  return row.status === 'failed'
}

async function load(): Promise<void> {
  loading.value = true
  error.value = null
  const [sessionResult, poolResult] = await Promise.allSettled([
    listRecentPracticeSessions(50),
    listBackgroundTasks(),
  ])
  sessions.value = sessionResult.status === 'fulfilled' ? sessionResult.value : []
  poolTasks.value = poolResult.status === 'fulfilled' ? poolResult.value : []
  error.value = sessionResult.status === 'rejected' ? sessionResult.reason : null
  loading.value = false
}

function openDialog(row: TaskRow): void {
  selected.value = row
}

function closeDialog(): void {
  selected.value = null
}

function openSession(row: TaskRow): void {
  void router.push({ name: 'practice', query: { session: row.id } })
  closeDialog()
}

async function startPool(row: TaskRow): Promise<void> {
  if (busyId.value) return
  busyId.value = row.id
  try {
    const session = await createPracticeSession(
      {
        practiceType: row.practiceType,
        source: 'today_new',
        count: row.count,
        difficulty: null,
        wordbookId: null,
      },
      `task-start-${row.id}-${Date.now()}`,
    )
    closeDialog()
    await router.push({ name: 'practice', query: { session: session.id } })
  } catch {
    toast.error('没有领取成功', '稍后重试或重新生成。')
  } finally {
    busyId.value = null
  }
}

async function retry(row: TaskRow): Promise<void> {
  if (busyId.value) return
  busyId.value = row.id
  try {
    if (row.kind === 'pool') {
      await retryBackgroundTask(row.id)
    } else {
      await regeneratePracticeSession(row.id, `task-retry-${row.id}-${Date.now()}`)
    }
    await load()
    closeDialog()
    toast.success('已重新开始生成', '稍后回来查看状态即可。')
  } catch {
    toast.error('重试失败', '请稍后再试。')
  } finally {
    busyId.value = null
  }
}

async function remove(row: TaskRow): Promise<void> {
  if (busyId.value) return
  const confirmed = window.confirm('删除这条题目？正在生成的题目会被取消。')
  if (!confirmed) return
  busyId.value = row.id
  try {
    if (row.kind === 'pool') await deleteBackgroundTask(row.id)
    else await deletePracticeSession(row.id)
    await load()
    closeDialog()
    toast.push({ title: '已删除', tone: 'info' })
  } catch {
    toast.error('删除失败', '请稍后再试。')
  } finally {
    busyId.value = null
  }
}

onMounted(() => {
  void load()
})
</script>

<template>
  <section class="workspace-card practice-tasks-card" :aria-label="heading ? undefined : '题目列表'" :aria-labelledby="heading ? 'practice-tasks-title' : undefined">
    <header class="workspace-section-header practice-tasks-head">
      <div v-if="heading">
        <h2 id="practice-tasks-title">题目列表</h2>
        <p v-if="!showTabs">每一条都能继续、重试或删除。</p>
      </div>
      <div v-if="showTabs" class="practice-task-tabs" role="group" aria-label="题目列表切换">
        <RouterLink
          class="practice-task-tab is-active"
          to="/practice/tasks"
          aria-current="page"
        >题目列表</RouterLink>
        <RouterLink class="practice-task-tab" to="/practice/records">题目集</RouterLink>
        <RouterLink class="practice-task-tab" to="/practice/mistakes">错题本</RouterLink>
      </div>
    </header>

    <LoadingState v-if="loading && rows.length === 0" label="正在读取题目…" />
    <ErrorNotice v-else-if="error" :error="error" retry-label="重新读取" @retry="load" />
    <div v-else-if="rows.length" role="list" class="practice-task-list" aria-label="题目列表">
      <DivButton
        v-for="row in rows"
        :key="row.key"
        role="listitem"
        type="button"
        class="practice-task-row"
        :aria-label="`${PRACTICE_TYPE_LABELS[row.practiceType]}，${taskName(row)}，${statusLabel(row)}，${row.count} 题`"
        @click="openDialog(row)"
      >
        <TypeMark class="practice-task-mark" :type="row.practiceType" :size="20" />
        <span class="practice-task-type">{{ PRACTICE_TYPE_LABELS[row.practiceType] }}</span>
        <strong>{{ taskName(row) }}</strong>
        <span class="practice-task-status" :class="`is-${row.status}`">{{ statusLabel(row) }}</span>
        <AppIcon name="arrow" />
      </DivButton>
    </div>
    <div v-else class="practice-rail-empty">
      <strong>还没有题目</strong>
      <p>生成第一组练习后，这里会按状态列出。</p>
    </div>

    <div v-if="selected" class="dialog-backdrop" @click.self="closeDialog">
      <section
        class="dialog-card practice-task-dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby="practice-task-dialog-title"
      >
        <header class="practice-task-dialog__head">
          <div>
            <p class="eyebrow">{{ sourceLabel(selected) }}</p>
            <h2 id="practice-task-dialog-title">{{ PRACTICE_TYPE_LABELS[selected.practiceType] }} · {{ selected.count }} 题</h2>
          </div>
          <DivButton class="button-secondary button-small" type="button" @click="closeDialog">关闭</DivButton>
        </header>

        <dl class="practice-task-dialog__meta">
          <div><dt>状态</dt><dd>{{ statusLabel(selected) }}</dd></div>
          <div v-if="selected.score !== null"><dt>得分</dt><dd>{{ selected.score }} 分</dd></div>
          <div v-if="selected.kind === 'pool'"><dt>来源</dt><dd>预生成套题</dd></div>
        </dl>
        <p v-if="selected.status === 'failed'" class="field-hint">这次生成没有成功，可以重试或删除。</p>

        <div class="button-row practice-task-dialog__actions">
          <DivButton
            v-if="selected.kind === 'pool' && selected.status === 'ready'"
            class="button"
            type="button"
            :disabled="busyId !== null"
            @click="startPool(selected)"
          >开始练习</DivButton>
          <DivButton
            v-else-if="canOpen(selected)"
            class="button"
            type="button"
            @click="openSession(selected)"
          >{{ selected.status === 'submitted' ? '查看结果' : '继续' }}</DivButton>
          <DivButton
            v-if="canRetry(selected)"
            class="button-secondary"
            type="button"
            :disabled="busyId !== null"
            @click="retry(selected)"
          >重试</DivButton>
          <DivButton
            class="button-danger"
            type="button"
            :disabled="busyId !== null"
            @click="remove(selected)"
          >删除</DivButton>
        </div>
      </section>
    </div>
  </section>
</template>
