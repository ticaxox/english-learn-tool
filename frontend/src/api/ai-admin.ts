/**
 * T-FE-005 administrator AI contract client.
 *
 * Frozen coordinates:
 *   contract_sha  6c72f1913d7c0fbf2e6d1e7face6cbf871115306
 *   openapi raw   7a0463b5124f2351dfa6acab7cb878bccbaf944610bfe7f3be68bbea89d8a7b4
 *   semantic      8497bc98e2daadcf30a32a9d89ededd9fe2a0db0026a062c3f3f7d1b1b8cd21c
 *
 * This module owns every backend field name for the admin AI surfaces. API keys
 * are only accepted as in-memory function arguments and are never stored by the
 * browser application.
 */
import { apiClient } from './client'
import { ContractError } from './errors'

export type ProviderTestStatus = 'untested' | 'succeeded' | 'failed'
export type PromptKey =
  | 'practice_generation'
  | 'subjective_grading'
  | 'coach_reply'
  | 'challenge_plan'
  | 'json_repair'
export type QuotaKind = 'coach_messages' | 'question_generation' | 'subjective_grading'
export type AiTaskType = PromptKey
export type AiJobStatus = 'queued' | 'running' | 'succeeded' | 'failed' | 'cancelled' | 'stale'

export interface AiProvider {
  id: string
  name: string
  baseUrl: string
  apiKeyMasked: string
  modelId: string
  priority: number
  isDefault: boolean
  timeoutSeconds: number
  enabled: boolean
  customHeaders: Record<string, string>
  lastTestStatus: ProviderTestStatus
  lastTestErrorCode: string | null
  lastTestAt: string | null
  lastTestLatencyMs: number | null
  createdAt: string
  updatedAt: string
}

export interface ProviderCreateInput {
  name: string
  baseUrl: string
  apiKey: string
  modelId: string
  priority: number
  isDefault: boolean
  timeoutSeconds: number
  enabled: boolean
  customHeaders: Record<string, string>
}

export interface ProviderPatchInput {
  name?: string
  baseUrl?: string
  apiKey?: string | null
  modelId?: string
  priority?: number
  isDefault?: boolean
  timeoutSeconds?: number
  enabled?: boolean
  customHeaders?: Record<string, string>
}

export interface ProviderTestResult {
  success: boolean
  status: ProviderTestStatus
  latencyMs: number | null
  errorCode: string | null
  errorMessage: string | null
  models: string[]
}

export interface ProviderModelsResult {
  success: boolean
  models: string[]
  errorCode: string | null
  errorMessage: string | null
}

export interface PromptSummary {
  key: PromptKey
  name: string
  summary: string
  updatedAt: string
}

export interface PromptDetail extends PromptSummary {
  template: string
}

export interface PromptUpdateInput {
  name: string
  summary: string
  template: string
}

export interface ProviderAggregate {
  providerId: string | null
  providerName: string
  jobs: number
  succeeded: number
  failed: number
}

export interface QuotaAggregate {
  quotaKind: QuotaKind
  limitPerUser: number
  usersWithUsage: number
  consumed: number
  reserved: number
  released: number
}

export interface TaskAggregate {
  taskType: AiTaskType
  status: AiJobStatus
  count: number
}

export interface AiUsage {
  dateFrom: string
  dateTo: string
  totalJobs: number
  activeJobs: number
  providers: ProviderAggregate[]
  quotas: QuotaAggregate[]
  tasks: TaskAggregate[]
}

const PROMPT_KEYS: readonly PromptKey[] = [
  'practice_generation',
  'subjective_grading',
  'coach_reply',
  'challenge_plan',
  'json_repair',
]
const QUOTA_KINDS: readonly QuotaKind[] = ['coach_messages', 'question_generation', 'subjective_grading']
const JOB_STATUSES: readonly AiJobStatus[] = ['queued', 'running', 'succeeded', 'failed', 'cancelled', 'stale']
const TEST_STATUSES: readonly ProviderTestStatus[] = ['untested', 'succeeded', 'failed']

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function fail(context: string, detail: string): never {
  throw new ContractError(`${context}：${detail}`)
}

function record(value: unknown, context: string): Record<string, unknown> {
  if (!isRecord(value)) fail(context, '响应应为对象')
  return value
}

function stringValue(value: unknown, context: string, field: string): string {
  if (typeof value !== 'string' || !value.trim()) fail(context, `${field} 应为非空字符串`)
  return value
}

function nullableString(value: unknown, context: string, field: string): string | null {
  if (value === null || value === undefined) return null
  if (typeof value !== 'string') fail(context, `${field} 应为字符串或 null`)
  return value
}

function integerValue(value: unknown, context: string, field: string, min = 0): number {
  if (typeof value !== 'number' || !Number.isInteger(value) || value < min) {
    fail(context, `${field} 应为不小于 ${min} 的整数`)
  }
  return value
}

function nullableInteger(value: unknown, context: string, field: string): number | null {
  if (value === null || value === undefined) return null
  return integerValue(value, context, field)
}

function booleanValue(value: unknown, context: string, field: string): boolean {
  if (typeof value !== 'boolean') fail(context, `${field} 应为布尔值`)
  return value
}

function stringArray(value: unknown, context: string, field: string): string[] {
  if (!Array.isArray(value)) fail(context, `${field} 应为字符串数组`)
  return value.map((item, index) => stringValue(item, context, `${field}[${index}]`))
}

function stringRecord(value: unknown, context: string, field: string): Record<string, string> {
  if (!isRecord(value)) fail(context, `${field} 应为对象`)
  const result: Record<string, string> = {}
  for (const [key, item] of Object.entries(value)) {
    if (typeof item !== 'string') fail(context, `${field}.${key} 应为字符串`)
    result[key] = item
  }
  return result
}

function enumValue<T extends string>(value: unknown, allowed: readonly T[], context: string, field: string): T {
  if (typeof value !== 'string' || !allowed.includes(value as T)) {
    fail(context, `${field} 必须是 ${allowed.join(' / ')} 之一`)
  }
  return value as T
}

function parseProvider(value: unknown, index = 0): AiProvider {
  const context = `AI 提供商响应 items[${index}]`
  const body = record(value, context)
  return {
    id: stringValue(body.id, context, 'id'),
    name: stringValue(body.name, context, 'name'),
    baseUrl: stringValue(body.base_url, context, 'base_url'),
    apiKeyMasked: stringValue(body.api_key_masked, context, 'api_key_masked'),
    modelId: stringValue(body.model_id, context, 'model_id'),
    priority: integerValue(body.priority, context, 'priority'),
    isDefault: booleanValue(body.is_default, context, 'is_default'),
    timeoutSeconds: integerValue(body.timeout_seconds, context, 'timeout_seconds', 1),
    enabled: booleanValue(body.enabled, context, 'enabled'),
    customHeaders: stringRecord(body.custom_headers, context, 'custom_headers'),
    lastTestStatus: enumValue(body.last_test_status, TEST_STATUSES, context, 'last_test_status'),
    lastTestErrorCode: nullableString(body.last_test_error_code, context, 'last_test_error_code'),
    lastTestAt: nullableString(body.last_test_at, context, 'last_test_at'),
    lastTestLatencyMs: nullableInteger(body.last_test_latency_ms, context, 'last_test_latency_ms'),
    createdAt: stringValue(body.created_at, context, 'created_at'),
    updatedAt: stringValue(body.updated_at, context, 'updated_at'),
  }
}

export function parseProviderList(payload: unknown): AiProvider[] {
  const body = record(payload, 'AI 提供商列表响应')
  if (!Array.isArray(body.items)) fail('AI 提供商列表响应', 'items 应为数组')
  return body.items.map((item, index) => parseProvider(item, index))
}

export function parseProviderTest(payload: unknown): ProviderTestResult {
  const context = 'AI 提供商连接检查响应'
  const body = record(payload, context)
  return {
    success: booleanValue(body.success, context, 'success'),
    status: enumValue(body.status, TEST_STATUSES, context, 'status'),
    latencyMs: nullableInteger(body.latency_ms, context, 'latency_ms'),
    errorCode: nullableString(body.error_code, context, 'error_code'),
    errorMessage: nullableString(body.error_message, context, 'error_message'),
    models: body.models === undefined ? [] : stringArray(body.models, context, 'models'),
  }
}

export function parseProviderModels(payload: unknown): ProviderModelsResult {
  const context = 'AI 提供商模型列表响应'
  const body = record(payload, context)
  return {
    success: booleanValue(body.success, context, 'success'),
    models: body.models === undefined ? [] : stringArray(body.models, context, 'models'),
    errorCode: nullableString(body.error_code, context, 'error_code'),
    errorMessage: nullableString(body.error_message, context, 'error_message'),
  }
}

function parsePromptSummary(value: unknown, index = 0): PromptSummary {
  const context = `AI 提示词列表 items[${index}]`
  const body = record(value, context)
  return {
    key: enumValue(body.key, PROMPT_KEYS, context, 'key'),
    name: stringValue(body.name, context, 'name'),
    summary: stringValue(body.summary, context, 'summary'),
    updatedAt: stringValue(body.updated_at, context, 'updated_at'),
  }
}

export function parsePromptList(payload: unknown): PromptSummary[] {
  const body = record(payload, 'AI 提示词列表响应')
  if (!Array.isArray(body.items)) fail('AI 提示词列表响应', 'items 应为数组')
  return body.items.map((item, index) => parsePromptSummary(item, index))
}

export function parsePromptDetail(payload: unknown): PromptDetail {
  const summary = parsePromptSummary(payload)
  const body = record(payload, 'AI 提示词详情响应')
  return {
    ...summary,
    template: stringValue(body.template, 'AI 提示词详情响应', 'template'),
  }
}

export function parseAiUsage(payload: unknown): AiUsage {
  const context = 'AI 用量响应'
  const body = record(payload, context)
  const providers = body.providers
  const quotas = body.quotas
  const tasks = body.tasks
  if (!Array.isArray(providers) || !Array.isArray(quotas) || !Array.isArray(tasks)) {
    fail(context, 'providers / quotas / tasks 应为数组')
  }
  return {
    dateFrom: stringValue(body.date_from, context, 'date_from'),
    dateTo: stringValue(body.date_to, context, 'date_to'),
    totalJobs: integerValue(body.total_jobs, context, 'total_jobs'),
    activeJobs: integerValue(body.active_jobs, context, 'active_jobs'),
    providers: providers.map((value, index) => {
      const item = record(value, `${context}.providers[${index}]`)
      return {
        providerId: nullableString(item.provider_id, context, `providers[${index}].provider_id`),
        providerName: stringValue(item.provider_name, context, `providers[${index}].provider_name`),
        jobs: integerValue(item.jobs, context, `providers[${index}].jobs`),
        succeeded: integerValue(item.succeeded, context, `providers[${index}].succeeded`),
        failed: integerValue(item.failed, context, `providers[${index}].failed`),
      }
    }),
    quotas: quotas.map((value, index) => {
      const item = record(value, `${context}.quotas[${index}]`)
      return {
        quotaKind: enumValue(item.quota_kind, QUOTA_KINDS, context, `quotas[${index}].quota_kind`),
        limitPerUser: integerValue(item.limit_per_user, context, `quotas[${index}].limit_per_user`),
        usersWithUsage: integerValue(item.users_with_usage, context, `quotas[${index}].users_with_usage`),
        consumed: integerValue(item.consumed, context, `quotas[${index}].consumed`),
        reserved: integerValue(item.reserved, context, `quotas[${index}].reserved`),
        released: integerValue(item.released, context, `quotas[${index}].released`),
      }
    }),
    tasks: tasks.map((value, index) => {
      const item = record(value, `${context}.tasks[${index}]`)
      return {
        taskType: enumValue(item.task_type, PROMPT_KEYS, context, `tasks[${index}].task_type`),
        status: enumValue(item.status, JOB_STATUSES, context, `tasks[${index}].status`),
        count: integerValue(item.count, context, `tasks[${index}].count`),
      }
    }),
  }
}

function serializeProviderCreate(input: ProviderCreateInput): Record<string, unknown> {
  return {
    name: input.name,
    base_url: input.baseUrl,
    api_key: input.apiKey,
    model_id: input.modelId,
    priority: input.priority,
    is_default: input.isDefault,
    timeout_seconds: input.timeoutSeconds,
    enabled: input.enabled,
    custom_headers: input.customHeaders,
  }
}

function serializeProviderPatch(input: ProviderPatchInput): Record<string, unknown> {
  const payload: Record<string, unknown> = {}
  if (input.name !== undefined) payload.name = input.name
  if (input.baseUrl !== undefined) payload.base_url = input.baseUrl
  if (input.apiKey !== undefined) payload.api_key = input.apiKey
  if (input.modelId !== undefined) payload.model_id = input.modelId
  if (input.priority !== undefined) payload.priority = input.priority
  if (input.isDefault !== undefined) payload.is_default = input.isDefault
  if (input.timeoutSeconds !== undefined) payload.timeout_seconds = input.timeoutSeconds
  if (input.enabled !== undefined) payload.enabled = input.enabled
  if (input.customHeaders !== undefined) payload.custom_headers = input.customHeaders
  return payload
}

export async function listProviders(): Promise<AiProvider[]> {
  return parseProviderList(await apiClient.get('/admin/ai/providers'))
}

export async function createProvider(input: ProviderCreateInput): Promise<AiProvider> {
  const payload = await apiClient.post('/admin/ai/providers', serializeProviderCreate(input), { retryCount: 0 })
  return parseProvider(payload)
}

export async function updateProvider(providerId: string, input: ProviderPatchInput): Promise<AiProvider> {
  const payload = await apiClient.patch(
    `/admin/ai/providers/${encodeURIComponent(providerId)}`,
    serializeProviderPatch(input),
    { retryCount: 0 },
  )
  return parseProvider(payload)
}

export async function deleteProvider(providerId: string): Promise<void> {
  await apiClient.delete<void>(`/admin/ai/providers/${encodeURIComponent(providerId)}`, { retryCount: 0 })
}

export async function testProvider(providerId: string): Promise<ProviderTestResult> {
  const payload = await apiClient.post(`/admin/ai/providers/${encodeURIComponent(providerId)}/test`, undefined, {
    retryCount: 0,
  })
  return parseProviderTest(payload)
}

export async function fetchProviderModels(providerId: string): Promise<ProviderModelsResult> {
  const payload = await apiClient.post(`/admin/ai/providers/${encodeURIComponent(providerId)}/models`, undefined, {
    retryCount: 0,
  })
  return parseProviderModels(payload)
}

export async function listPrompts(): Promise<PromptSummary[]> {
  return parsePromptList(await apiClient.get('/admin/ai/prompts'))
}

export async function getPrompt(promptKey: PromptKey): Promise<PromptDetail> {
  return parsePromptDetail(await apiClient.get(`/admin/ai/prompts/${encodeURIComponent(promptKey)}`))
}

export async function updatePrompt(promptKey: PromptKey, input: PromptUpdateInput): Promise<PromptDetail> {
  const payload = await apiClient.put(`/admin/ai/prompts/${encodeURIComponent(promptKey)}`, input, {
    retryCount: 0,
  })
  return parsePromptDetail(payload)
}

export async function fetchAiUsage(dateFrom?: string, dateTo?: string): Promise<AiUsage> {
  const params = new URLSearchParams()
  if (dateFrom) params.set('date_from', dateFrom)
  if (dateTo) params.set('date_to', dateTo)
  const suffix = params.size > 0 ? `?${params.toString()}` : ''
  return parseAiUsage(await apiClient.get(`/admin/ai/usage${suffix}`))
}

export const PROMPT_LABELS: Record<PromptKey, string> = {
  practice_generation: '练习生成',
  subjective_grading: '主观题评分',
  coach_reply: 'AI 教练回复',
  challenge_plan: '每日闯关规划',
  json_repair: 'JSON 修复',
}

export const QUOTA_LABELS: Record<QuotaKind, string> = {
  coach_messages: '教练消息',
  question_generation: '题目生成',
  subjective_grading: '主观题评分',
}

export const TASK_STATUS_LABELS: Record<AiJobStatus, string> = {
  queued: '排队中',
  running: '运行中',
  succeeded: '成功',
  failed: '失败',
  cancelled: '已取消',
  stale: '已过期',
}