/**
 * T-FE-009 daily challenge client.
 *
 * Frozen contract: c1d951489fc784a8e8fb648a134de6f10f572025
 * OpenAPI raw: d488dae1…f3c8af
 * OpenAPI semantic: 3ca7d2f9…c5135
 *
 * Maps, node status, BOSS results, and history are server-owned. The browser
 * never fabricates completion or calculates learning progress.
 */
import { apiClient } from './client'
import { ContractError } from './errors'

export type ChallengePlanStatus = 'generating' | 'ready' | 'failed' | 'completed' | 'expired'
export type ChallengeNodeStatus = 'locked' | 'unlocked' | 'in_progress' | 'completed' | 'failed'
export type ChallengeNodeType = 'REVIEW' | 'NEW_WORDS' | 'WORD_DRILL' | 'AI_PRACTICE' | 'BOSS' | 'OPTIONAL_SIDE'
export type ChallengeResourceType = 'memory' | 'practice'
export type ChallengeBossStatus = 'completed' | 'scoring' | 'failed'

export interface ChallengeNode {
  id: string
  clientKey: string
  nodeType: ChallengeNodeType
  orderIndex: number
  title: string
  description: string
  estimatedMinutes: number
  wordEntryIds: string[]
  practiceSpec: Record<string, unknown>
  optional: boolean
  status: ChallengeNodeStatus
  resourceType: ChallengeResourceType | null
  resourceId: string | null
  startedAt: string | null
  completedAt: string | null
  errorCode: string | null
  errorMessage: string | null
}

export interface ChallengePlan {
  id: string
  localDate: string
  status: ChallengePlanStatus
  title: string | null
  summary: string | null
  targetMinutes: number
  dailyPlanId: string
  aiJobId: string | null
  generatedAt: string | null
  lockedAt: string | null
  challengeCompletedAt: string | null
  expiresAt: string
  errorCode: string | null
  errorMessage: string | null
  mainCompleted: number
  mainTotal: number
  mapDsl: string
  nodes: ChallengeNode[]
}

export interface ChallengeGenerateResult {
  challengeId: string
  status: ChallengePlanStatus
  jobId: string | null
  statusUrl: string | null
  replayed: boolean
}

export interface ChallengeJob {
  jobId: string
  challengeId: string | null
  status: string
  errorCode: string | null
  errorMessage: string | null
  retryable: boolean
}

export interface ChallengeNodeDetail {
  challengeId: string
  node: ChallengeNode
  allowedActions: Array<'start' | 'resume' | 'view_result'>
}

export interface ChallengeStartResult {
  challengeId: string
  nodeId: string
  status: ChallengeNodeStatus
  resourceType: ChallengeResourceType | null
  resourceId: string | null
  jobId: string | null
  message: string
}

export interface ChallengeBossAnswer {
  questionId: string
  answer: string
}

export interface ChallengeBossResult {
  challengeId: string
  nodeId: string
  status: ChallengeBossStatus
  score: number | null
  completed: boolean
  submissionId: string | null
  result: Record<string, unknown> | null
  errorCode: string | null
  errorMessage: string | null
  message: string
}

export interface ChallengeHistoryItem {
  id: string
  localDate: string
  status: ChallengePlanStatus
  title: string | null
  summary: string | null
  targetMinutes: number
  mainCompleted: number
  mainTotal: number
  challengeCompletedAt: string | null
}

export interface ChallengeHistoryPage {
  items: ChallengeHistoryItem[]
  nextCursor: string | null
  hasMore: boolean
}

const PLAN_STATUSES = new Set<ChallengePlanStatus>(['generating', 'ready', 'failed', 'completed', 'expired'])
const NODE_STATUSES = new Set<ChallengeNodeStatus>(['locked', 'unlocked', 'in_progress', 'completed', 'failed'])
const NODE_TYPES = new Set<ChallengeNodeType>(['REVIEW', 'NEW_WORDS', 'WORD_DRILL', 'AI_PRACTICE', 'BOSS', 'OPTIONAL_SIDE'])
const RESOURCE_TYPES = new Set<ChallengeResourceType>(['memory', 'practice'])
const BOSS_STATUSES = new Set<ChallengeBossStatus>(['completed', 'scoring', 'failed'])

export const CHALLENGE_NODE_LABELS: Record<ChallengeNodeType, string> = {
  REVIEW: '复习',
  NEW_WORDS: '新词',
  WORD_DRILL: '词形训练',
  AI_PRACTICE: 'AI 练习',
  BOSS: '终点挑战',
  OPTIONAL_SIDE: '可选支线',
}

export const CHALLENGE_STATUS_LABELS: Record<ChallengeNodeStatus, string> = {
  locked: '未解锁',
  unlocked: '可开始',
  in_progress: '进行中',
  completed: '已完成',
  failed: '失败',
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function requiredString(value: unknown, field: string): string {
  if (typeof value !== 'string') throw new ContractError(`闯关接口响应缺少字符串字段 ${field}。`)
  return value
}

function optionalString(value: unknown, field: string): string | null {
  if (value === null || value === undefined) return null
  if (typeof value !== 'string') throw new ContractError(`闯关接口响应字段 ${field} 必须是字符串或 null。`)
  return value
}

function requiredNumber(value: unknown, field: string): number {
  if (typeof value !== 'number' || !Number.isFinite(value)) {
    throw new ContractError(`闯关接口响应字段 ${field} 必须是数字。`)
  }
  return value
}

function defaultedNumber(value: unknown, field: string, fallback: number): number {
  if (value === undefined) return fallback
  return requiredNumber(value, field)
}

function requiredBoolean(value: unknown, field: string): boolean {
  if (typeof value !== 'boolean') throw new ContractError(`闯关接口响应字段 ${field} 必须是布尔值。`)
  return value
}

function defaultedBoolean(value: unknown, field: string, fallback: boolean): boolean {
  if (value === undefined) return fallback
  return requiredBoolean(value, field)
}

function stringArray(value: unknown, field: string): string[] {
  if (value === undefined) return []
  if (!Array.isArray(value) || value.some((item) => typeof item !== 'string')) {
    throw new ContractError(`闯关接口响应字段 ${field} 必须是字符串数组。`)
  }
  return value as string[]
}

function objectValue(value: unknown, field: string): Record<string, unknown> {
  if (value === undefined) return {}
  if (!isRecord(value)) throw new ContractError(`闯关接口响应字段 ${field} 必须是对象。`)
  return value
}

function enumValue<T extends string>(value: unknown, allowed: Set<T>, field: string): T {
  if (typeof value !== 'string' || !allowed.has(value as T)) {
    throw new ContractError(`闯关接口返回了未声明的 ${field}。`)
  }
  return value as T
}

export function parseChallengeNode(value: unknown): ChallengeNode {
  if (!isRecord(value)) throw new ContractError('闯关节点不是对象。')
  return {
    id: requiredString(value.id, 'node.id'),
    clientKey: requiredString(value.client_key, 'node.client_key'),
    nodeType: enumValue(value.node_type, NODE_TYPES, 'node.node_type'),
    orderIndex: requiredNumber(value.order_index, 'node.order_index'),
    title: requiredString(value.title, 'node.title'),
    description: requiredString(value.description, 'node.description'),
    estimatedMinutes: requiredNumber(value.estimated_minutes, 'node.estimated_minutes'),
    wordEntryIds: stringArray(value.word_entry_ids, 'node.word_entry_ids'),
    practiceSpec: objectValue(value.practice_spec, 'node.practice_spec'),
    optional: defaultedBoolean(value.optional, 'node.optional', false),
    status: enumValue(value.status, NODE_STATUSES, 'node.status'),
    resourceType: value.resource_type === null || value.resource_type === undefined
      ? null
      : enumValue(value.resource_type, RESOURCE_TYPES, 'node.resource_type'),
    resourceId: optionalString(value.resource_id, 'node.resource_id'),
    startedAt: optionalString(value.started_at, 'node.started_at'),
    completedAt: optionalString(value.completed_at, 'node.completed_at'),
    errorCode: optionalString(value.error_code, 'node.error_code'),
    errorMessage: optionalString(value.error_message, 'node.error_message'),
  }
}

export function parseChallengePlan(value: unknown): ChallengePlan {
  if (!isRecord(value) || !Array.isArray(value.nodes)) throw new ContractError('闯关地图缺少 nodes 数组。')
  return {
    id: requiredString(value.id, 'challenge.id'),
    localDate: requiredString(value.local_date, 'challenge.local_date'),
    status: enumValue(value.status, PLAN_STATUSES, 'challenge.status'),
    title: optionalString(value.title, 'challenge.title'),
    summary: optionalString(value.summary, 'challenge.summary'),
    targetMinutes: requiredNumber(value.target_minutes, 'challenge.target_minutes'),
    dailyPlanId: requiredString(value.daily_plan_id, 'challenge.daily_plan_id'),
    aiJobId: optionalString(value.ai_job_id, 'challenge.ai_job_id'),
    generatedAt: optionalString(value.generated_at, 'challenge.generated_at'),
    lockedAt: optionalString(value.locked_at, 'challenge.locked_at'),
    challengeCompletedAt: optionalString(value.challenge_completed_at, 'challenge.challenge_completed_at'),
    expiresAt: requiredString(value.expires_at, 'challenge.expires_at'),
    errorCode: optionalString(value.error_code, 'challenge.error_code'),
    errorMessage: optionalString(value.error_message, 'challenge.error_message'),
    mainCompleted: defaultedNumber(value.main_completed, 'challenge.main_completed', 0),
    mainTotal: defaultedNumber(value.main_total, 'challenge.main_total', 0),
    mapDsl: optionalString(value.map_dsl, 'challenge.map_dsl') ?? '',
    nodes: value.nodes.map(parseChallengeNode),
  }
}

export function parseChallengeGenerate(value: unknown): ChallengeGenerateResult {
  if (!isRecord(value)) throw new ContractError('闯关生成响应不是对象。')
  return {
    challengeId: requiredString(value.challenge_id, 'generate.challenge_id'),
    status: enumValue(value.status, PLAN_STATUSES, 'generate.status'),
    jobId: optionalString(value.job_id, 'generate.job_id'),
    statusUrl: optionalString(value.status_url, 'generate.status_url'),
    replayed: defaultedBoolean(value.replayed, 'generate.replayed', false),
  }
}

export function parseChallengeJob(value: unknown): ChallengeJob {
  if (!isRecord(value)) throw new ContractError('闯关任务响应不是对象。')
  return {
    jobId: requiredString(value.job_id, 'job.job_id'),
    challengeId: optionalString(value.challenge_id, 'job.challenge_id'),
    status: requiredString(value.status, 'job.status'),
    errorCode: optionalString(value.error_code, 'job.error_code'),
    errorMessage: optionalString(value.error_message, 'job.error_message'),
    retryable: defaultedBoolean(value.retryable, 'job.retryable', false),
  }
}

export function parseChallengeNodeDetail(value: unknown): ChallengeNodeDetail {
  if (!isRecord(value) || !Array.isArray(value.allowed_actions)) {
    throw new ContractError('闯关节点详情缺少 allowed_actions。')
  }
  const allowed = value.allowed_actions.filter((item): item is 'start' | 'resume' | 'view_result' =>
    item === 'start' || item === 'resume' || item === 'view_result',
  )
  if (allowed.length !== value.allowed_actions.length) {
    throw new ContractError('闯关节点详情包含未知 allowed_action。')
  }
  return {
    challengeId: requiredString(value.challenge_id, 'detail.challenge_id'),
    node: parseChallengeNode(value.node),
    allowedActions: allowed,
  }
}

export function parseChallengeStart(value: unknown): ChallengeStartResult {
  if (!isRecord(value)) throw new ContractError('闯关开始响应不是对象。')
  return {
    challengeId: requiredString(value.challenge_id, 'start.challenge_id'),
    nodeId: requiredString(value.node_id, 'start.node_id'),
    status: enumValue(value.status, NODE_STATUSES, 'start.status'),
    resourceType: value.resource_type === null || value.resource_type === undefined
      ? null
      : enumValue(value.resource_type, RESOURCE_TYPES, 'start.resource_type'),
    resourceId: optionalString(value.resource_id, 'start.resource_id'),
    jobId: optionalString(value.job_id, 'start.job_id'),
    message: requiredString(value.message, 'start.message'),
  }
}

export function parseChallengeBossResult(value: unknown): ChallengeBossResult {
  if (!isRecord(value)) throw new ContractError('BOSS 提交响应不是对象。')
  const score = value.score
  if (score !== null && score !== undefined && typeof score !== 'number') {
    throw new ContractError('BOSS 提交响应 score 必须是数字或 null。')
  }
  const result = value.result === null || value.result === undefined ? null : objectValue(value.result, 'boss.result')
  return {
    challengeId: requiredString(value.challenge_id, 'boss.challenge_id'),
    nodeId: requiredString(value.node_id, 'boss.node_id'),
    status: enumValue(value.status, BOSS_STATUSES, 'boss.status'),
    score: score ?? null,
    completed: defaultedBoolean(value.completed, 'boss.completed', false),
    submissionId: optionalString(value.submission_id, 'boss.submission_id'),
    result,
    errorCode: optionalString(value.error_code, 'boss.error_code'),
    errorMessage: optionalString(value.error_message, 'boss.error_message'),
    message: requiredString(value.message, 'boss.message'),
  }
}

export function parseChallengeHistoryItem(value: unknown): ChallengeHistoryItem {
  if (!isRecord(value)) throw new ContractError('闯关历史项不是对象。')
  return {
    id: requiredString(value.id, 'history.id'),
    localDate: requiredString(value.local_date, 'history.local_date'),
    status: enumValue(value.status, PLAN_STATUSES, 'history.status'),
    title: optionalString(value.title, 'history.title'),
    summary: optionalString(value.summary, 'history.summary'),
    targetMinutes: requiredNumber(value.target_minutes, 'history.target_minutes'),
    mainCompleted: requiredNumber(value.main_completed, 'history.main_completed'),
    mainTotal: requiredNumber(value.main_total, 'history.main_total'),
    challengeCompletedAt: optionalString(value.challenge_completed_at, 'history.challenge_completed_at'),
  }
}

export function parseChallengeHistoryPage(value: unknown): ChallengeHistoryPage {
  if (!isRecord(value) || !Array.isArray(value.items)) throw new ContractError('闯关历史缺少 items。')
  return {
    items: value.items.map(parseChallengeHistoryItem),
    nextCursor: optionalString(value.next_cursor, 'history.next_cursor'),
    hasMore: defaultedBoolean(value.has_more, 'history.has_more', false),
  }
}

export function serializeChallengeBossAnswers(answers: ChallengeBossAnswer[]): Array<Record<string, string>> {
  return answers.map((answer) => ({ question_id: answer.questionId, answer: answer.answer }))
}

export async function getTodayChallenge(options: { signal?: AbortSignal } = {}): Promise<ChallengePlan> {
  const payload = await apiClient.get('/challenges/today', options)
  return parseChallengePlan(payload)
}

export async function generateTodayChallenge(options: { signal?: AbortSignal } = {}): Promise<ChallengeGenerateResult> {
  const payload = await apiClient.post('/challenges/today/generate', undefined, {
    ...options,
    retryCount: 0,
  })
  return parseChallengeGenerate(payload)
}

/** Throw today's unfinished map away and build it again. */
export async function regenerateTodayChallenge(options: { signal?: AbortSignal } = {}): Promise<ChallengeGenerateResult> {
  const payload = await apiClient.post('/challenges/today/regenerate', undefined, {
    ...options,
    retryCount: 0,
  })
  return parseChallengeGenerate(payload)
}

export async function getChallengeJob(
  jobId: string,
  options: { signal?: AbortSignal } = {},
): Promise<ChallengeJob> {
  const payload = await apiClient.get(`/challenges/jobs/${encodeURIComponent(jobId)}`, options)
  return parseChallengeJob(payload)
}

export async function getChallenge(
  challengeId: string,
  options: { signal?: AbortSignal } = {},
): Promise<ChallengePlan> {
  const payload = await apiClient.get(`/challenges/${encodeURIComponent(challengeId)}`, options)
  return parseChallengePlan(payload)
}

export async function getChallengeNodeDetail(
  challengeId: string,
  nodeId: string,
  options: { signal?: AbortSignal } = {},
): Promise<ChallengeNodeDetail> {
  const payload = await apiClient.get(
    `/challenges/${encodeURIComponent(challengeId)}/nodes/${encodeURIComponent(nodeId)}`,
    options,
  )
  return parseChallengeNodeDetail(payload)
}

export async function startChallengeNode(
  challengeId: string,
  nodeId: string,
  options: { signal?: AbortSignal } = {},
): Promise<ChallengeStartResult> {
  const payload = await apiClient.post(
    `/challenges/${encodeURIComponent(challengeId)}/nodes/${encodeURIComponent(nodeId)}/start`,
    undefined,
    { ...options, retryCount: 0 },
  )
  return parseChallengeStart(payload)
}

export async function submitChallengeBoss(
  challengeId: string,
  nodeId: string,
  answers: ChallengeBossAnswer[],
  idempotencyKey: string,
  options: { signal?: AbortSignal } = {},
): Promise<ChallengeBossResult> {
  const payload = await apiClient.post(
    `/challenges/${encodeURIComponent(challengeId)}/nodes/${encodeURIComponent(nodeId)}/boss-submit`,
    { answers: serializeChallengeBossAnswers(answers) },
    {
      ...options,
      retryCount: 0,
      headers: { 'Idempotency-Key': idempotencyKey },
    },
  )
  return parseChallengeBossResult(payload)
}

export async function getChallengeHistory(
  limit = 20,
  offset = 0,
  options: { signal?: AbortSignal } = {},
): Promise<ChallengeHistoryPage> {
  const params = new URLSearchParams({ limit: String(limit), offset: String(offset) })
  const payload = await apiClient.get(`/challenges/history?${params.toString()}`, options)
  return parseChallengeHistoryPage(payload)
}
