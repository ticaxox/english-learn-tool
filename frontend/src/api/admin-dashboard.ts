/**
 * T-FE-010 organization dashboard client.
 *
 * Frozen contract: 46fe1bdfe67a64f5027ccd56b2ba8b9ea120238f
 * OpenAPI: 84 paths / 153 schemas
 *
 * Only `/admin/dashboard` is called. The response is aggregate-only; this
 * module never requests member answers, drafts, coach messages, or private
 * wordbook content.
 */
import { apiClient } from './client'
import { ContractError } from './errors'

export type DashboardNumber = number | null
export type DashboardQuotaKind = 'coach_messages' | 'question_generation' | 'subjective_grading'

export interface AdminDashboardFilters {
  dateFrom: string
  dateTo: string
  department: string | null
  learningGroup: string | null
  timezone: string
}

export interface AdminDashboardPrivacy {
  suppressed: boolean
  minimumGroupSize: number
  reason: string | null
}

export interface AdminDashboardMetrics {
  totalMembers: number
  activeMembers: DashboardNumber
  activeMemberRate: DashboardNumber
  studyMinutes: DashboardNumber
  plansTotal: DashboardNumber
  plansCompleted: DashboardNumber
  taskCompletionRate: DashboardNumber
  newWordsCompleted: DashboardNumber
  dueWordsCompleted: DashboardNumber
  practiceSubmissions: DashboardNumber
  practiceCorrectRate: DashboardNumber
  mistakeFlags: DashboardNumber
  highPriorityMistakes: DashboardNumber
  memoryEvents: DashboardNumber
  averageCurrentStreakDays: DashboardNumber
  membersWithStreak7d: DashboardNumber
  aiJobs: DashboardNumber
  aiFailed: DashboardNumber
  aiFailureRate: DashboardNumber
  challengesCompleted: DashboardNumber
}

export interface AdminDashboardTrendPoint {
  localDate: string
  activeMembers: DashboardNumber
  studyMinutes: DashboardNumber
  plansCompleted: DashboardNumber
  practiceSubmissions: DashboardNumber
  practiceCorrectRate: DashboardNumber
  mistakes: DashboardNumber
  memoryEvents: DashboardNumber
  aiJobs: DashboardNumber
  aiFailed: DashboardNumber
  challengesCompleted: DashboardNumber
}

export interface AdminDashboardGroupRow {
  department: string | null
  learningGroup: string | null
  memberCount: number
  activeMembers: DashboardNumber
  studyMinutes: DashboardNumber
  taskCompletionRate: DashboardNumber
  practiceCorrectRate: DashboardNumber
  mistakeFlags: DashboardNumber
  aiFailureRate: DashboardNumber
}

export interface AdminDashboardRiskHints {
  inactiveMembers3d: DashboardNumber
  highMistakeMembers: DashboardNumber
  aiFailureAlert: boolean | null
}

export interface AdminDashboardQuotaUsage {
  quotaKind: DashboardQuotaKind
  consumed: number
  reserved: number
  released: number
}

export interface AdminDashboardResponse {
  generatedAt: string
  calculationVersion: string
  filters: AdminDashboardFilters
  privacy: AdminDashboardPrivacy
  metrics: AdminDashboardMetrics
  trend: AdminDashboardTrendPoint[]
  groups: AdminDashboardGroupRow[]
  groupPage: number
  groupPageSize: number
  groupHasMore: boolean
  suppressedGroupCount: number
  quotaUsage: AdminDashboardQuotaUsage[]
  riskHints: AdminDashboardRiskHints
}

export interface AdminDashboardQuery {
  dateFrom?: string
  dateTo?: string
  department?: string
  learningGroup?: string
  page?: number
  pageSize?: number
}

const QUOTA_KINDS = new Set<DashboardQuotaKind>([
  'coach_messages',
  'question_generation',
  'subjective_grading',
])

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function requiredRecord(value: unknown, field: string): Record<string, unknown> {
  if (!isRecord(value)) throw new ContractError(`看板响应字段 ${field} 必须是对象。`)
  return value
}

function requiredString(value: unknown, field: string): string {
  if (typeof value !== 'string') throw new ContractError(`看板响应字段 ${field} 必须是字符串。`)
  return value
}

function optionalString(value: unknown, field: string): string | null {
  if (value === null || value === undefined) return null
  if (typeof value !== 'string') throw new ContractError(`看板响应字段 ${field} 必须是字符串或 null。`)
  return value
}

function requiredNumber(value: unknown, field: string): number {
  if (typeof value !== 'number' || !Number.isFinite(value)) {
    throw new ContractError(`看板响应字段 ${field} 必须是数字。`)
  }
  return value
}

function nullableNumber(value: unknown, field: string): number | null {
  if (value === null || value === undefined) return null
  return requiredNumber(value, field)
}

function requiredBoolean(value: unknown, field: string): boolean {
  if (typeof value !== 'boolean') throw new ContractError(`看板响应字段 ${field} 必须是布尔值。`)
  return value
}

function nullableBoolean(value: unknown, field: string): boolean | null {
  if (value === null || value === undefined) return null
  return requiredBoolean(value, field)
}

function arrayValue(value: unknown, field: string): unknown[] {
  if (value === undefined) return []
  if (!Array.isArray(value)) throw new ContractError(`看板响应字段 ${field} 必须是数组。`)
  return value
}

function requiredDateString(value: unknown, field: string): string {
  const text = requiredString(value, field)
  if (!/^\d{4}-\d{2}-\d{2}$/.test(text)) {
    throw new ContractError(`看板响应字段 ${field} 必须是 YYYY-MM-DD。`)
  }
  return text
}

function parseFilters(value: unknown): AdminDashboardFilters {
  const record = requiredRecord(value, 'filters')
  return {
    dateFrom: requiredDateString(record.date_from, 'filters.date_from'),
    dateTo: requiredDateString(record.date_to, 'filters.date_to'),
    department: optionalString(record.department, 'filters.department'),
    learningGroup: optionalString(record.learning_group, 'filters.learning_group'),
    timezone: requiredString(record.timezone, 'filters.timezone'),
  }
}

function parsePrivacy(value: unknown): AdminDashboardPrivacy {
  const record = requiredRecord(value, 'privacy')
  return {
    suppressed: requiredBoolean(record.suppressed, 'privacy.suppressed'),
    minimumGroupSize: record.minimum_group_size === undefined
      ? 3
      : requiredNumber(record.minimum_group_size, 'privacy.minimum_group_size'),
    reason: optionalString(record.reason, 'privacy.reason'),
  }
}

function parseMetrics(value: unknown): AdminDashboardMetrics {
  const record = requiredRecord(value, 'metrics')
  return {
    totalMembers: requiredNumber(record.total_members, 'metrics.total_members'),
    activeMembers: nullableNumber(record.active_members, 'metrics.active_members'),
    activeMemberRate: nullableNumber(record.active_member_rate, 'metrics.active_member_rate'),
    studyMinutes: nullableNumber(record.study_minutes, 'metrics.study_minutes'),
    plansTotal: nullableNumber(record.plans_total, 'metrics.plans_total'),
    plansCompleted: nullableNumber(record.plans_completed, 'metrics.plans_completed'),
    taskCompletionRate: nullableNumber(record.task_completion_rate, 'metrics.task_completion_rate'),
    newWordsCompleted: nullableNumber(record.new_words_completed, 'metrics.new_words_completed'),
    dueWordsCompleted: nullableNumber(record.due_words_completed, 'metrics.due_words_completed'),
    practiceSubmissions: nullableNumber(record.practice_submissions, 'metrics.practice_submissions'),
    practiceCorrectRate: nullableNumber(record.practice_correct_rate, 'metrics.practice_correct_rate'),
    mistakeFlags: nullableNumber(record.mistake_flags, 'metrics.mistake_flags'),
    highPriorityMistakes: nullableNumber(record.high_priority_mistakes, 'metrics.high_priority_mistakes'),
    memoryEvents: nullableNumber(record.memory_events, 'metrics.memory_events'),
    averageCurrentStreakDays: nullableNumber(record.average_current_streak_days, 'metrics.average_current_streak_days'),
    membersWithStreak7d: nullableNumber(record.members_with_streak_7d, 'metrics.members_with_streak_7d'),
    aiJobs: nullableNumber(record.ai_jobs, 'metrics.ai_jobs'),
    aiFailed: nullableNumber(record.ai_failed, 'metrics.ai_failed'),
    aiFailureRate: nullableNumber(record.ai_failure_rate, 'metrics.ai_failure_rate'),
    challengesCompleted: nullableNumber(record.challenges_completed, 'metrics.challenges_completed'),
  }
}

function parseTrendPoint(value: unknown): AdminDashboardTrendPoint {
  const record = requiredRecord(value, 'trend[]')
  return {
    localDate: requiredDateString(record.local_date, 'trend.local_date'),
    activeMembers: nullableNumber(record.active_members, 'trend.active_members'),
    studyMinutes: nullableNumber(record.study_minutes, 'trend.study_minutes'),
    plansCompleted: nullableNumber(record.plans_completed, 'trend.plans_completed'),
    practiceSubmissions: nullableNumber(record.practice_submissions, 'trend.practice_submissions'),
    practiceCorrectRate: nullableNumber(record.practice_correct_rate, 'trend.practice_correct_rate'),
    mistakes: nullableNumber(record.mistakes, 'trend.mistakes'),
    memoryEvents: nullableNumber(record.memory_events, 'trend.memory_events'),
    aiJobs: nullableNumber(record.ai_jobs, 'trend.ai_jobs'),
    aiFailed: nullableNumber(record.ai_failed, 'trend.ai_failed'),
    challengesCompleted: nullableNumber(record.challenges_completed, 'trend.challenges_completed'),
  }
}

function parseGroupRow(value: unknown): AdminDashboardGroupRow {
  const record = requiredRecord(value, 'groups[]')
  return {
    department: optionalString(record.department, 'groups.department'),
    learningGroup: optionalString(record.learning_group, 'groups.learning_group'),
    memberCount: requiredNumber(record.member_count, 'groups.member_count'),
    activeMembers: nullableNumber(record.active_members, 'groups.active_members'),
    studyMinutes: nullableNumber(record.study_minutes, 'groups.study_minutes'),
    taskCompletionRate: nullableNumber(record.task_completion_rate, 'groups.task_completion_rate'),
    practiceCorrectRate: nullableNumber(record.practice_correct_rate, 'groups.practice_correct_rate'),
    mistakeFlags: nullableNumber(record.mistake_flags, 'groups.mistake_flags'),
    aiFailureRate: nullableNumber(record.ai_failure_rate, 'groups.ai_failure_rate'),
  }
}

function parseRiskHints(value: unknown): AdminDashboardRiskHints {
  if (value === undefined) return { inactiveMembers3d: null, highMistakeMembers: null, aiFailureAlert: null }
  const record = requiredRecord(value, 'risk_hints')
  return {
    inactiveMembers3d: nullableNumber(record.inactive_members_3d, 'risk_hints.inactive_members_3d'),
    highMistakeMembers: nullableNumber(record.high_mistake_members, 'risk_hints.high_mistake_members'),
    aiFailureAlert: nullableBoolean(record.ai_failure_alert, 'risk_hints.ai_failure_alert'),
  }
}

function parseQuotaUsage(value: unknown): AdminDashboardQuotaUsage {
  const record = requiredRecord(value, 'quota_usage[]')
  const kind = requiredString(record.quota_kind, 'quota_usage.quota_kind')
  if (!QUOTA_KINDS.has(kind as DashboardQuotaKind)) {
    throw new ContractError(`看板响应返回了未声明的 quota_kind：${kind}。`)
  }
  return {
    quotaKind: kind as DashboardQuotaKind,
    consumed: requiredNumber(record.consumed, 'quota_usage.consumed'),
    reserved: requiredNumber(record.reserved, 'quota_usage.reserved'),
    released: requiredNumber(record.released, 'quota_usage.released'),
  }
}

export function parseAdminDashboard(value: unknown): AdminDashboardResponse {
  const record = requiredRecord(value, 'response')
  return {
    generatedAt: requiredString(record.generated_at, 'generated_at'),
    calculationVersion: requiredString(record.calculation_version, 'calculation_version'),
    filters: parseFilters(record.filters),
    privacy: parsePrivacy(record.privacy),
    metrics: parseMetrics(record.metrics),
    trend: arrayValue(record.trend, 'trend').map(parseTrendPoint),
    groups: arrayValue(record.groups, 'groups').map(parseGroupRow),
    groupPage: record.group_page === undefined ? 1 : requiredNumber(record.group_page, 'group_page'),
    groupPageSize: record.group_page_size === undefined ? 10 : requiredNumber(record.group_page_size, 'group_page_size'),
    groupHasMore: record.group_has_more === undefined ? false : requiredBoolean(record.group_has_more, 'group_has_more'),
    suppressedGroupCount: record.suppressed_group_count === undefined
      ? 0
      : requiredNumber(record.suppressed_group_count, 'suppressed_group_count'),
    quotaUsage: arrayValue(record.quota_usage, 'quota_usage').map(parseQuotaUsage),
    riskHints: parseRiskHints(record.risk_hints),
  }
}

export async function fetchAdminDashboard(
  query: AdminDashboardQuery = {},
  options: { signal?: AbortSignal } = {},
): Promise<AdminDashboardResponse> {
  const params = new URLSearchParams()
  if (query.dateFrom) params.set('date_from', query.dateFrom)
  if (query.dateTo) params.set('date_to', query.dateTo)
  if (query.department?.trim()) params.set('department', query.department.trim())
  if (query.learningGroup?.trim()) params.set('learning_group', query.learningGroup.trim())
  if (query.page !== undefined) params.set('page', String(query.page))
  if (query.pageSize !== undefined) params.set('page_size', String(query.pageSize))
  const suffix = params.size > 0 ? `?${params.toString()}` : ''
  const payload = await apiClient.get(`/admin/dashboard${suffix}`, options)
  return parseAdminDashboard(payload)
}
