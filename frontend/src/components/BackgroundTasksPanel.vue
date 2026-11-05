<script setup lang="ts">
/**
 * Background pre-generation tasks.
 *
 * The inventory panel only says how many sets are wanted; this dialog shows the
 * actual slots being generated, lets a failed one be retried and a slot be
 * deleted.
 */
import { computed, onMounted, ref } from 'vue'
import ErrorNotice from './ErrorNotice.vue'
import LoadingState from './LoadingState.vue'
import {
  deleteBackgroundTask,
  listBackgroundTasks,
  retryBackgroundTask,
  type BackgroundTask,
} from '../api/background-tasks'
import { useToast } from '../composables/useToast'

const TYPE_LABELS: Record<string, string> = {
  fill_blank: '填空',
  reading: '阅读',
  translation: '翻译',
  writing: '作文',
}
const STATUS_LABELS: Record<string, string> = {
  generating: '生成中',
  ready: '已就绪',
  failed: '失败',
}

const tasks = ref<BackgroundTask[]>([])
const open = ref(false)
const loading = ref(false)
const error = ref<unknown>(null)
const busyId = ref<string | null>(null)
const toast = useToast()

const counts = computed(() => ({
  generating: tasks.value.filter((task) => task.status === 'generating').length,
  ready: tasks.value.filter((task) => task.status === 'ready').length,
  failed: tasks.value.filter((task) => task.status === 'failed').length,
}))

function typeLabel(task: BackgroundTask): string {
  return TYPE_LABELS[task.practiceType] ?? task.practiceType
}

function statusLabel(task: BackgroundTask): string {
  return STATUS_LABELS[task.status] ?? task.status
}

function errorLabel(task: BackgroundTask): string {
  if (task.errorCode === 'AI_JOB_TIMEOUT' || task.errorCode === 'AI_GENERATION_TIMEOUT') {
    return '这次生成超时了，可以重试。'
  }
  return '这次生成没有成功，可以重试。'
}

function formatDate(value: string): string {
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return ''
  return new Intl.DateTimeFormat('zh-CN', {
    month: 'numeric',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  }).format(date)
}

async function load(): Promise<void> {
  loading.value = true
  error.value = null
  try {
    tasks.value = await listBackgroundTasks()
  } catch (loadError) {
    error.value = loadError
  } finally {
    loading.value = false
  }
}

function show(): void {
  open.value = true
  void load()
}

async function retry(task: BackgroundTask): Promise<void> {
  if (busyId.value) return
  busyId.value = task.id
  try {
    await retryBackgroundTask(task.id)
    await load()
    toast.success('已重新开始生成', '稍后回来查看状态即可。')
  } catch {
    toast.error('重试失败', '请稍后再试。')
  } finally {
    busyId.value = null
  }
}

async function remove(task: BackgroundTask): Promise<void> {
  if (busyId.value) return
  const confirmed = window.confirm('删除这个后台任务？正在生成的题目会被取消。')
  if (!confirmed) return
  busyId.value = task.id
  try {
    await deleteBackgroundTask(task.id)
    await load()
    toast.push({ title: '后台任务已删除', tone: 'info' })
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
  <section class="panel background-tasks-panel" aria-labelledby="background-tasks-title">
    <header class="background-tasks-panel__head">
      <div>
        <h3 id="background-tasks-title">后台任务</h3>
        <p class="field-hint">预生成题目的后台任务；可以查看进度、重试失败任务或删除。</p>
      </div>
      <DivButton class="button-secondary" type="button" @click="show">查看后台任务</DivButton>
    </header>
    <p class="background-tasks-summary">
      生成中 <strong>{{ counts.generating }}</strong>
      <span aria-hidden="true">·</span>
      已就绪 <strong>{{ counts.ready }}</strong>
      <span aria-hidden="true">·</span>
      失败 <strong :class="{ 'is-failed': counts.failed > 0 }">{{ counts.failed }}</strong>
    </p>
  </section>

  <div v-if="open" class="dialog-backdrop" @click.self="open = false">
    <section
      class="dialog-card background-tasks-dialog"
      role="dialog"
      aria-modal="true"
      aria-labelledby="background-tasks-dialog-title"
    >
      <header class="background-tasks-dialog__head">
        <div>
          <p class="eyebrow">AI 练习</p>
          <h2 id="background-tasks-dialog-title">后台任务</h2>
        </div>
        <div class="background-tasks-dialog__actions">
          <DivButton class="button-secondary button-small" type="button" :disabled="loading" @click="load">
            {{ loading ? '刷新中…' : '刷新' }}
          </DivButton>
          <DivButton class="button-secondary button-small" type="button" @click="open = false">
            关闭
          </DivButton>
        </div>
      </header>

      <LoadingState v-if="loading && tasks.length === 0" label="正在读取后台任务…" />
      <ErrorNotice v-else-if="error" :error="error" retry-label="重新读取" @retry="load" />

      <div v-else-if="tasks.length === 0" class="background-tasks-empty">
        <p>还没有后台任务。到学习设置里打开「AI 练习预生成」后，这里会出现正在准备的套题。</p>
      </div>

      <div v-else role="list" class="background-tasks-list" aria-label="后台任务列表">
        <div v-for="task in tasks" :key="task.id" role="listitem" class="background-task">
          <div class="background-task__main">
            <strong>{{ typeLabel(task) }} · {{ task.questionCount }} 题</strong>
            <span class="background-task__status" :class="`is-${task.status}`">{{ statusLabel(task) }}</span>
            <span class="background-task__meta">第 {{ task.attempts }} 次尝试 · {{ formatDate(task.createdAt) }}</span>
          </div>
          <p v-if="task.status === 'failed'" class="background-task__error">{{ errorLabel(task) }}</p>
          <div class="background-task__actions">
            <DivButton
              v-if="task.status === 'failed'"
              class="button-secondary button-small"
              type="button"
              :disabled="busyId !== null"
              @click="retry(task)"
            >
              重试
            </DivButton>
            <DivButton
              class="button-secondary button-small"
              type="button"
              :disabled="busyId !== null"
              @click="remove(task)"
            >
              删除
            </DivButton>
          </div>
        </div>
      </div>
    </section>
  </div>
</template>
