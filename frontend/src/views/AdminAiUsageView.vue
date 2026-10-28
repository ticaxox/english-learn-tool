<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import ErrorNotice from '../components/ErrorNotice.vue'
import LoadingState from '../components/LoadingState.vue'
import {
  fetchAiUsage,
  PROMPT_LABELS,
  QUOTA_LABELS,
  TASK_STATUS_LABELS,
  type AiUsage,
} from '../api/ai-admin'
import { todayIsoDate } from '../lib/learning-validation'
import '../ai-admin.css'

function offsetDate(days: number): string {
  const date = new Date()
  date.setDate(date.getDate() + days)
  return todayIsoDate(date)
}

const dateFrom = ref(offsetDate(-29))
const dateTo = ref(todayIsoDate())
const usage = ref<AiUsage | null>(null)
const loading = ref(false)
const error = ref<unknown>(null)
const filterError = ref<string | null>(null)

const providerTotals = computed(() => {
  if (!usage.value) return { jobs: 0, succeeded: 0, failed: 0 }
  return usage.value.providers.reduce(
    (total, provider) => ({
      jobs: total.jobs + provider.jobs,
      succeeded: total.succeeded + provider.succeeded,
      failed: total.failed + provider.failed,
    }),
    { jobs: 0, succeeded: 0, failed: 0 },
  )
})

function successRate(succeeded: number, jobs: number): string {
  if (jobs <= 0) return '—'
  return `${Math.round((succeeded / jobs) * 100)}%`
}

async function load(): Promise<void> {
  filterError.value = null
  if (!dateFrom.value || !dateTo.value) {
    filterError.value = '请选择完整的起止日期。'
    return
  }
  if (dateFrom.value > dateTo.value) {
    filterError.value = '开始日期不能晚于结束日期。'
    return
  }
  loading.value = true
  error.value = null
  try {
    usage.value = await fetchAiUsage(dateFrom.value, dateTo.value)
  } catch (requestError) {
    usage.value = null
    error.value = requestError
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  void load()
})
</script>

<template>
  <article class="ai-admin-page usage-page">
    <header class="ai-admin-hero">
      <div>
        <p class="eyebrow">管理员 · AI 配置</p>
        <h1>AI 用量</h1>
        <p class="lead">只展示聚合任务、额度与提供商结果，不提供用户题目、对话、草稿或私密词书正文。</p>
      </div>
    </header>

    <form class="panel usage-filter" @submit.prevent="load">
      <div class="field">
        <label for="usage-from">开始日期</label>
        <input id="usage-from" v-model="dateFrom" type="date" />
      </div>
      <div class="field">
        <label for="usage-to">结束日期</label>
        <input id="usage-to" v-model="dateTo" type="date" />
      </div>
      <button class="button" type="submit" :disabled="loading">{{ loading ? '读取中…' : '应用范围' }}</button>
    </form>
    <p v-if="filterError" class="field-error" role="alert">{{ filterError }}</p>

    <LoadingState v-if="loading" label="正在读取聚合 AI 用量…" />

    <section v-else-if="error" class="panel">
      <ErrorNotice :error="error" retry-label="重新读取用量" @retry="load" />
    </section>

    <template v-else-if="usage">
      <section class="ai-summary-strip" aria-label="AI 用量摘要">
        <div><strong>{{ usage.totalJobs }}</strong><span>任务总数</span></div>
        <div><strong>{{ usage.activeJobs }}</strong><span>活跃任务</span></div>
        <div><strong>{{ providerTotals.succeeded }}</strong><span>成功结果</span></div>
        <div><strong>{{ providerTotals.failed }}</strong><span>失败结果</span></div>
      </section>
      <p class="inline-note">统计范围：{{ usage.dateFrom }} 至 {{ usage.dateTo }} · 全部数据来自服务端聚合。</p>

      <div class="usage-grid">
        <section class="panel">
          <div class="section-heading"><h2>提供商结果</h2></div>
          <table class="ai-table">
            <thead><tr><th>提供商</th><th>任务</th><th>成功</th><th>失败</th><th>成功率</th></tr></thead>
            <tbody>
              <tr v-for="provider in usage.providers" :key="provider.providerId ?? provider.providerName">
                <td>{{ provider.providerName }}</td>
                <td>{{ provider.jobs }}</td>
                <td>{{ provider.succeeded }}</td>
                <td>{{ provider.failed }}</td>
                <td>{{ successRate(provider.succeeded, provider.jobs) }}</td>
              </tr>
              <tr v-if="usage.providers.length === 0"><td colspan="5">服务端未返回提供商聚合。</td></tr>
            </tbody>
          </table>
        </section>

        <section class="panel">
          <div class="section-heading"><h2>额度使用</h2></div>
          <table class="ai-table">
            <thead><tr><th>额度</th><th>每人上限</th><th>使用用户</th><th>已消耗</th><th>预留</th><th>释放</th></tr></thead>
            <tbody>
              <tr v-for="quota in usage.quotas" :key="quota.quotaKind">
                <td>{{ QUOTA_LABELS[quota.quotaKind] }}</td>
                <td>{{ quota.limitPerUser }}</td>
                <td>{{ quota.usersWithUsage }}</td>
                <td>{{ quota.consumed }}</td>
                <td>{{ quota.reserved }}</td>
                <td>{{ quota.released }}</td>
              </tr>
              <tr v-if="usage.quotas.length === 0"><td colspan="6">服务端未返回额度聚合。</td></tr>
            </tbody>
          </table>
        </section>
      </div>

      <section class="panel">
        <div class="section-heading"><h2>任务状态</h2></div>
        <table class="ai-table">
          <thead><tr><th>任务类型</th><th>状态</th><th>数量</th></tr></thead>
          <tbody>
            <tr v-for="task in usage.tasks" :key="`${task.taskType}:${task.status}`">
              <td>{{ PROMPT_LABELS[task.taskType] }} <code>{{ task.taskType }}</code></td>
              <td>{{ TASK_STATUS_LABELS[task.status] }} <code>{{ task.status }}</code></td>
              <td>{{ task.count }}</td>
            </tr>
            <tr v-if="usage.tasks.length === 0"><td colspan="3">服务端未返回任务聚合。</td></tr>
          </tbody>
        </table>
      </section>
    </template>
  </article>
</template>