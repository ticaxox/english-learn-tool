<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import ErrorNotice from '../components/ErrorNotice.vue'
import LoadingState from '../components/LoadingState.vue'
import {
  fetchAdminDashboard,
  type AdminDashboardResponse,
  type DashboardNumber,
} from '../api/admin-dashboard'
import '../admin-dashboard.css'

const SHANGHAI_TIMEZONE = 'Asia/Shanghai'
const QUOTA_LABELS = {
  coach_messages: '教练消息',
  question_generation: '题目生成',
  subjective_grading: '主观评分',
} as const

function shanghaiToday(): string {
  return new Intl.DateTimeFormat('en-CA', { timeZone: SHANGHAI_TIMEZONE }).format(new Date())
}

function shiftIsoDate(value: string, days: number): string {
  const date = new Date(`${value}T12:00:00Z`)
  date.setUTCDate(date.getUTCDate() + days)
  return date.toISOString().slice(0, 10)
}

function formatInteger(value: DashboardNumber): string {
  if (value === null) return '—'
  return new Intl.NumberFormat('zh-CN', { maximumFractionDigits: 0 }).format(value)
}

function formatDecimal(value: DashboardNumber): string {
  if (value === null) return '—'
  return new Intl.NumberFormat('zh-CN', { maximumFractionDigits: 2 }).format(value)
}

function formatPercent(value: DashboardNumber): string {
  if (value === null) return '—'
  return `${(value * 100).toFixed(1)}%`
}

function formatDate(value: string): string {
  const date = new Date(`${value}T12:00:00+08:00`)
  if (Number.isNaN(date.getTime())) return value
  return new Intl.DateTimeFormat('zh-CN', { month: '2-digit', day: '2-digit' }).format(date)
}

function formatGeneratedAt(value: string, timezone: string): string {
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  try {
    return new Intl.DateTimeFormat('zh-CN', {
      timeZone: timezone || SHANGHAI_TIMEZONE,
      dateStyle: 'medium',
      timeStyle: 'short',
    }).format(date)
  } catch {
    return value
  }
}

function daysBetween(from: string, to: string): number {
  const start = Date.parse(`${from}T00:00:00Z`)
  const end = Date.parse(`${to}T00:00:00Z`)
  return Math.floor((end - start) / 86_400_000)
}

const dateFrom = ref(shiftIsoDate(shanghaiToday(), -6))
const dateTo = ref(shanghaiToday())
const department = ref('')
const learningGroup = ref('')
const pageSize = ref(10)
const page = ref(1)
const dashboard = ref<AdminDashboardResponse | null>(null)
const loading = ref(false)
const error = ref<unknown>(null)
const filterError = ref<string | null>(null)
let requestSerial = 0

const hasNoAggregate = computed(() => {
  if (!dashboard.value || dashboard.value.privacy.suppressed) return false
  return dashboard.value.metrics.totalMembers === 0
})

const summaryCards = computed(() => {
  const metrics = dashboard.value?.metrics
  if (!metrics) return []
  return [
    { label: '组织成员', value: formatInteger(metrics.totalMembers), hint: '当前筛选范围' },
    { label: '活跃成员', value: formatInteger(metrics.activeMembers), hint: `活跃率 ${formatPercent(metrics.activeMemberRate)}` },
    { label: '学习分钟', value: formatDecimal(metrics.studyMinutes), hint: '服务端学习活动聚合' },
    { label: '任务完成率', value: formatPercent(metrics.taskCompletionRate), hint: `${formatInteger(metrics.plansCompleted)} / ${formatInteger(metrics.plansTotal)} 份计划` },
  ]
})

const learningCards = computed(() => {
  const metrics = dashboard.value?.metrics
  if (!metrics) return []
  return [
    { label: '新词完成', value: formatInteger(metrics.newWordsCompleted), hint: '计划新词完成数' },
    { label: '到期复习完成', value: formatInteger(metrics.dueWordsCompleted), hint: '到期复习完成数' },
    { label: '记忆事件', value: formatInteger(metrics.memoryEvents), hint: '服务端学习事件' },
    { label: '平均连续学习', value: `${formatDecimal(metrics.averageCurrentStreakDays)} 天`, hint: `${formatInteger(metrics.membersWithStreak7d)} 人达到 7 天` },
  ]
})

const practiceCards = computed(() => {
  const metrics = dashboard.value?.metrics
  if (!metrics) return []
  return [
    { label: '练习提交', value: formatInteger(metrics.practiceSubmissions), hint: '已提交练习会话' },
    { label: '练习正确率', value: formatPercent(metrics.practiceCorrectRate), hint: '服务端判分聚合' },
    { label: '错题标记', value: formatInteger(metrics.mistakeFlags), hint: `${formatInteger(metrics.highPriorityMistakes)} 个高优先级` },
    { label: '完成闯关', value: formatInteger(metrics.challengesCompleted), hint: '当天主线完成次数' },
  ]
})

const aiCards = computed(() => {
  const metrics = dashboard.value?.metrics
  if (!metrics) return []
  return [
    { label: 'AI 任务', value: formatInteger(metrics.aiJobs), hint: '窗口内任务总数' },
    { label: 'AI 失败', value: formatInteger(metrics.aiFailed), hint: `失败率 ${formatPercent(metrics.aiFailureRate)}` },
  ]
})

const trendMax = computed(() => {
  const values = dashboard.value?.trend
    .map((point) => point.studyMinutes)
    .filter((value): value is number => value !== null) ?? []
  return values.length > 0 ? Math.max(...values, 1) : 0
})

function trendHeight(value: DashboardNumber): string {
  if (value === null || trendMax.value <= 0) return '0%'
  return `${Math.max(value === 0 ? 0 : 5, Math.round((value / trendMax.value) * 100))}%`
}

const trendHasValues = computed(() => trendMax.value > 0)

const trendSummary = computed(() => {
  const points = dashboard.value?.trend ?? []
  if (points.length === 0) return '当前范围没有逐日趋势数据。'
  const studyValues = points.map((point) => point.studyMinutes).filter((value): value is number => value !== null)
  const activeValues = points.map((point) => point.activeMembers).filter((value): value is number => value !== null)
  const totalMinutes = studyValues.reduce((sum, value) => sum + value, 0)
  const peak = studyValues.length > 0 ? Math.max(...studyValues) : null
  const averageActive = activeValues.length > 0
    ? activeValues.reduce((sum, value) => sum + value, 0) / activeValues.length
    : null
  return `${points.length} 天趋势；学习分钟合计 ${formatDecimal(totalMinutes)}，峰值 ${formatDecimal(peak)}；日均活跃成员 ${formatDecimal(averageActive)}。柱高按当前窗口内学习分钟相对值展示。`
})

function quotaLabel(kind: keyof typeof QUOTA_LABELS): string {
  return QUOTA_LABELS[kind]
}

function validateFilters(): boolean {
  filterError.value = null
  if (!dateFrom.value || !dateTo.value) {
    filterError.value = '请选择完整的起止日期。'
    return false
  }
  if (dateFrom.value > dateTo.value) {
    filterError.value = '开始日期不能晚于结束日期。'
    return false
  }
  if (daysBetween(dateFrom.value, dateTo.value) > 90) {
    filterError.value = '日期范围最多为 90 天。'
    return false
  }
  return true
}

async function load(): Promise<void> {
  if (!validateFilters()) return
  const serial = ++requestSerial
  loading.value = true
  error.value = null
  try {
    const response = await fetchAdminDashboard({
      dateFrom: dateFrom.value,
      dateTo: dateTo.value,
      department: department.value,
      learningGroup: learningGroup.value,
      page: page.value,
      pageSize: pageSize.value,
    })
    if (serial !== requestSerial) return
    dashboard.value = response
    page.value = response.groupPage
    pageSize.value = response.groupPageSize
  } catch (requestError) {
    if (serial !== requestSerial) return
    dashboard.value = null
    error.value = requestError
  } finally {
    if (serial === requestSerial) loading.value = false
  }
}

async function applyFilters(): Promise<void> {
  page.value = 1
  await load()
}

async function changePage(delta: number): Promise<void> {
  const next = page.value + delta
  if (next < 1) return
  page.value = next
  await load()
}

async function changePageSize(): Promise<void> {
  page.value = 1
  await load()
}

onMounted(() => {
  void load()
})
</script>

<template>
  <article class="dashboard-page">
    <header class="dashboard-hero">
      <div>
        <p class="eyebrow">Administrator · organization health</p>
        <h1>组织学习看板</h1>
        <p class="lead">只读取服务端聚合白名单，不提供成员答题正文、草稿、教练对话或私密词书内容。</p>
      </div>
      <div class="dashboard-hero__actions">
        <span class="dashboard-source">GET /api/v1/admin/dashboard</span>
        <DivButton class="button-secondary" type="button" :disabled="loading" @click="load">刷新看板</DivButton>
      </div>
    </header>

    <form class="panel dashboard-filters" aria-label="组织看板筛选" @submit.prevent="applyFilters">
      <div class="field">
        <label for="dashboard-from">开始日期</label>
        <input id="dashboard-from" v-model="dateFrom" type="date" required />
      </div>
      <div class="field">
        <label for="dashboard-to">结束日期</label>
        <input id="dashboard-to" v-model="dateTo" type="date" required />
      </div>
      <div class="field">
        <label for="dashboard-department">部门</label>
        <input id="dashboard-department" v-model="department" type="text" maxlength="100" placeholder="留空表示全部部门" />
      </div>
      <div class="field">
        <label for="dashboard-group">学习小组</label>
        <input id="dashboard-group" v-model="learningGroup" type="text" maxlength="100" placeholder="留空表示全部小组" />
      </div>
      <div class="field dashboard-filters__size">
        <label for="dashboard-page-size">小组每页</label>
        <select id="dashboard-page-size" v-model.number="pageSize" @change="changePageSize">
          <option :value="10">10</option>
          <option :value="20">20</option>
          <option :value="50">50</option>
        </select>
      </div>
      <DivButton class="button" type="submit" :disabled="loading">{{ loading ? '读取中…' : '应用筛选' }}</DivButton>
    </form>
    <p v-if="filterError" class="field-error" role="alert">{{ filterError }}</p>

    <LoadingState v-if="loading" label="正在读取真实组织聚合看板…" />
    <section v-else-if="error" class="panel">
      <ErrorNotice :error="error" retry-label="重新读取看板" @retry="load" />
    </section>

    <template v-else-if="dashboard">
      <section v-if="dashboard.privacy.suppressed" class="panel dashboard-privacy" role="status" aria-live="polite">
        <div class="dashboard-privacy__mark" aria-hidden="true">◌</div>
        <div>
          <p class="eyebrow">Privacy threshold</p>
          <h2>聚合结果已按隐私规则抑制</h2>
          <p>{{ dashboard.privacy.reason || `当前筛选样本少于 ${dashboard.privacy.minimumGroupSize} 名成员，服务端不会返回个人或小样本聚合。` }}</p>
          <p class="field-hint">页面不会把缺失值显示为 0，也不会通过筛选推断个人数据。</p>
        </div>
      </section>

      <section v-else-if="hasNoAggregate" class="panel dashboard-empty" role="status">
        <p class="eyebrow">No members in scope</p>
        <h2>当前筛选范围内没有成员</h2>
        <p>服务端确认该筛选范围没有成员。请调整日期、部门或学习小组；这不是系统故障，也不会把空范围显示成完成的 0 指标。</p>
      </section>

      <template v-else>
        <section class="dashboard-summary" aria-label="组织看板摘要">
          <div v-for="card in summaryCards" :key="card.label" class="dashboard-kpi dashboard-kpi--primary">
            <span>{{ card.label }}</span>
            <strong>{{ card.value }}</strong>
            <small>{{ card.hint }}</small>
          </div>
        </section>

        <section class="dashboard-section" aria-labelledby="dashboard-learning-title">
          <div class="dashboard-section__heading">
            <div><p class="eyebrow">Learning health</p><h2 id="dashboard-learning-title">学习完成</h2></div>
            <span class="dashboard-stamp">{{ dashboard.filters.dateFrom }} → {{ dashboard.filters.dateTo }}</span>
          </div>
          <div class="dashboard-kpi-grid">
            <article v-for="card in learningCards" :key="card.label" class="dashboard-kpi">
              <span>{{ card.label }}</span><strong>{{ card.value }}</strong><small>{{ card.hint }}</small>
            </article>
          </div>
        </section>

        <section class="dashboard-section" aria-labelledby="dashboard-practice-title">
          <div class="dashboard-section__heading">
            <div><p class="eyebrow">Practice & risk</p><h2 id="dashboard-practice-title">练习与风险</h2></div>
          </div>
          <div class="dashboard-kpi-grid">
            <article v-for="card in practiceCards" :key="card.label" class="dashboard-kpi">
              <span>{{ card.label }}</span><strong>{{ card.value }}</strong><small>{{ card.hint }}</small>
            </article>
          </div>
        </section>

        <div class="dashboard-two-column">
          <section class="panel dashboard-trend" aria-labelledby="dashboard-trend-title">
            <div class="dashboard-section__heading">
              <div><p class="eyebrow">Daily trend</p><h2 id="dashboard-trend-title">每日学习分钟</h2></div>
              <span class="field-hint">颜色与柱高均来自服务端趋势</span>
            </div>
            <p class="dashboard-trend__summary">{{ trendSummary }}</p>
            <div v-if="trendHasValues" class="dashboard-bars" role="img" :aria-label="trendSummary">
              <div v-for="point in dashboard.trend" :key="point.localDate" class="dashboard-bar">
                <strong>{{ formatDecimal(point.studyMinutes) }}</strong>
                <div class="dashboard-bar__track" aria-hidden="true"><span :style="{ height: trendHeight(point.studyMinutes) }"></span></div>
                <small>{{ formatDate(point.localDate) }}</small>
              </div>
            </div>
            <div v-else class="dashboard-inline-empty">当前窗口没有逐日学习分钟数据。</div>
            <details class="dashboard-trend__details">
              <summary>查看逐日文字数据</summary>
              <div class="dashboard-table-wrap">
                <table class="dashboard-table">
                  <caption>服务端逐日趋势文字摘要</caption>
                  <thead><tr><th>日期</th><th>学习分钟</th><th>活跃成员</th><th>练习提交</th><th>错题</th><th>AI 任务</th></tr></thead>
                  <tbody>
                    <tr v-for="point in dashboard.trend" :key="point.localDate">
                      <td>{{ point.localDate }}</td>
                      <td>{{ formatDecimal(point.studyMinutes) }}</td>
                      <td>{{ formatInteger(point.activeMembers) }}</td>
                      <td>{{ formatInteger(point.practiceSubmissions) }}</td>
                      <td>{{ formatInteger(point.mistakes) }}</td>
                      <td>{{ formatInteger(point.aiJobs) }}</td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </details>
          </section>

          <section class="panel dashboard-risk" aria-labelledby="dashboard-risk-title">
            <div class="dashboard-section__heading">
              <div><p class="eyebrow">Risk hints</p><h2 id="dashboard-risk-title">风险提示</h2></div>
            </div>
            <div role="list" class="dashboard-risk__list">
              <div role="listitem"><span>3 天未活跃成员</span><strong>{{ formatInteger(dashboard.riskHints.inactiveMembers3d) }}</strong></div>
              <div role="listitem"><span>高错题成员</span><strong>{{ formatInteger(dashboard.riskHints.highMistakeMembers) }}</strong></div>
              <div role="listitem"><span>AI 失败率提醒</span><strong>{{ dashboard.riskHints.aiFailureAlert === null ? '—' : (dashboard.riskHints.aiFailureAlert ? '需要关注' : '正常') }}</strong></div>
            </div>
            <p class="field-hint">风险提示是聚合口径，不包含成员姓名、正文或可反推个人的明细。</p>
          </section>
        </div>

        <div class="dashboard-two-column">
          <section class="panel" aria-labelledby="dashboard-ai-title">
            <div class="dashboard-section__heading">
              <div><p class="eyebrow">AI operations</p><h2 id="dashboard-ai-title">AI 使用</h2></div>
            </div>
            <div class="dashboard-kpi-grid dashboard-kpi-grid--compact">
              <article v-for="card in aiCards" :key="card.label" class="dashboard-kpi">
                <span>{{ card.label }}</span><strong>{{ card.value }}</strong><small>{{ card.hint }}</small>
              </article>
            </div>
            <div class="dashboard-table-wrap">
              <table class="dashboard-table">
                <caption>AI 额度聚合</caption>
                <thead><tr><th>额度</th><th>已消耗</th><th>预留</th><th>释放</th></tr></thead>
                <tbody>
                  <tr v-for="quota in dashboard.quotaUsage" :key="quota.quotaKind">
                    <td>{{ quotaLabel(quota.quotaKind) }} <code>{{ quota.quotaKind }}</code></td>
                    <td>{{ formatInteger(quota.consumed) }}</td>
                    <td>{{ formatInteger(quota.reserved) }}</td>
                    <td>{{ formatInteger(quota.released) }}</td>
                  </tr>
                  <tr v-if="dashboard.quotaUsage.length === 0"><td colspan="4">服务端未返回额度聚合。</td></tr>
                </tbody>
              </table>
            </div>
          </section>

          <section class="panel" aria-labelledby="dashboard-privacy-title">
            <div class="dashboard-section__heading">
              <div><p class="eyebrow">Data scope</p><h2 id="dashboard-privacy-title">数据口径</h2></div>
            </div>
            <dl class="dashboard-meta">
              <div><dt>统计范围</dt><dd>{{ dashboard.filters.dateFrom }} → {{ dashboard.filters.dateTo }}</dd></div>
              <div><dt>时区</dt><dd>{{ dashboard.filters.timezone }}</dd></div>
              <div><dt>部门</dt><dd>{{ dashboard.filters.department || '全部部门' }}</dd></div>
              <div><dt>学习小组</dt><dd>{{ dashboard.filters.learningGroup || '全部小组' }}</dd></div>
              <div><dt>最小样本</dt><dd>{{ dashboard.privacy.minimumGroupSize }} 名成员</dd></div>
              <div><dt>计算版本</dt><dd><code>{{ dashboard.calculationVersion }}</code></dd></div>
              <div><dt>更新时间</dt><dd>{{ formatGeneratedAt(dashboard.generatedAt, dashboard.filters.timezone) }}</dd></div>
              <div><dt>被抑制小组</dt><dd>{{ formatInteger(dashboard.suppressedGroupCount) }}</dd></div>
            </dl>
            <p class="field-hint">仅使用管理员聚合白名单；未读取成员答题、草稿、教练正文或私密词书。</p>
          </section>
        </div>

        <section class="panel dashboard-groups" aria-labelledby="dashboard-groups-title">
          <div class="dashboard-section__heading">
            <div><p class="eyebrow">Group aggregates</p><h2 id="dashboard-groups-title">学习小组聚合</h2></div>
            <span class="field-hint">第 {{ dashboard.groupPage }} 页 · 每组至少 {{ dashboard.privacy.minimumGroupSize }} 人</span>
          </div>
          <div class="dashboard-table-wrap">
            <table class="dashboard-table dashboard-table--groups">
              <caption>服务端分页的小组聚合指标</caption>
              <thead><tr><th>部门 / 小组</th><th>成员</th><th>活跃</th><th>学习分钟</th><th>任务完成率</th><th>练习正确率</th><th>错题</th><th>AI 失败率</th></tr></thead>
              <tbody>
                <tr v-for="group in dashboard.groups" :key="`${group.department ?? ''}:${group.learningGroup ?? ''}`">
                  <td><strong>{{ group.department || '未分组部门' }}</strong><small>{{ group.learningGroup || '未分组小组' }}</small></td>
                  <td>{{ formatInteger(group.memberCount) }}</td>
                  <td>{{ formatInteger(group.activeMembers) }}</td>
                  <td>{{ formatDecimal(group.studyMinutes) }}</td>
                  <td>{{ formatPercent(group.taskCompletionRate) }}</td>
                  <td>{{ formatPercent(group.practiceCorrectRate) }}</td>
                  <td>{{ formatInteger(group.mistakeFlags) }}</td>
                  <td>{{ formatPercent(group.aiFailureRate) }}</td>
                </tr>
                <tr v-if="dashboard.groups.length === 0"><td colspan="8">当前页没有可展示的小组聚合。</td></tr>
              </tbody>
            </table>
          </div>
          <div class="dashboard-pagination">
            <DivButton class="button-secondary button-small" type="button" :disabled="loading || dashboard.groupPage <= 1" @click="changePage(-1)">上一页</DivButton>
            <span>第 {{ dashboard.groupPage }} 页</span>
            <DivButton class="button-secondary button-small" type="button" :disabled="loading || !dashboard.groupHasMore" @click="changePage(1)">下一页</DivButton>
          </div>
        </section>
      </template>

      <footer class="dashboard-footnote">
        <span>数据来源：管理员聚合接口白名单</span>
        <span>计算版本：{{ dashboard.calculationVersion }}</span>
        <span>更新时间：{{ formatGeneratedAt(dashboard.generatedAt, dashboard.filters.timezone) }}</span>
      </footer>
    </template>
  </article>
</template>
