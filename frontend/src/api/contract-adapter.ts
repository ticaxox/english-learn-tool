/**
 * THE single calibration point for T-FE-004.
 *
 * T-BE-004 has no frozen OpenAPI yet. Rather than guessing backend field names
 * and silently rendering wrong data, this module keeps every backend identifier
 * in one declarative table (`CONTRACT`) and refuses to parse anything while that
 * table is uncalibrated.
 *
 * When A01 publishes `contract_sha` + `openapi_sha256`, the only edits needed
 * are `FROZEN_CONTRACT`, `CONTRACT` and the parser bodies. Views, components and
 * composables never touch a backend field name.
 */
import { ContractError } from './errors'
import type {
  LearningProfileUpdate,
  MemoryModule,
  StudyEventInput,
} from '../types/learning'
import {
  type AiPracticeState,
  type LearningProfile,
  type LearningStats,
  type LearnedWordState,
  type MasteryOutcome,
  type MemoryConfig,
  type MemoryModulePreference,
  type MistakePriorityUpdate,
  type PagedMistakes,
  type SessionSummary,
  type SpellingBlankType,
  type StudyFeedback,
  type StudyQuestion,
  type TodayPlan,
  type TodayStatus,
  EXAM_TARGETS,
  MEMORY_MODULES,
} from '../types/learning'

/** Raised while the contract is not frozen. Never a reason to show mock data. */
export class ContractPendingError extends ContractError {
  readonly endpoint: string

  constructor(endpoint: string) {
    super(
      `接口契约尚未冻结（${endpoint}）。A01 发布 T-BE-004 的 contract_sha 与 openapi_sha256 后，` +
        '本页才会读取真实数据；在此之前不会显示任何推测性内容。',
    )
    this.name = 'ContractPendingError'
    this.endpoint = endpoint
    // `ContractError` pins the prototype to itself for instanceof across the
    // transpiled ES5 boundary; re-pin it here or this subclass loses its own
    // identity (catching `ContractPendingError` would silently never match).
    Object.setPrototypeOf(this, ContractPendingError.prototype)
  }
}

export interface FrozenContract {
  /** Git SHA of the backend implementation that published the OpenAPI. */
  contractSha: string
  /** SHA-256 of the published `backend/openapi.json`. */
  openapiSha256: string
}

/**
 * Set this to the frozen coordinates A01 hands over. Deliberately not wired to
 * an env var or build flag: a stale build must never look calibrated.
 */
export const FROZEN_CONTRACT: FrozenContract | null = null

export function isContractFrozen(): boolean {
  return FROZEN_CONTRACT !== null
}

export function contractCoordinateLabel(): string {
  if (!FROZEN_CONTRACT) {
    return '未冻结：等待 A01 发布 T-BE-004 contract_sha / openapi_sha256'
  }
  return `contract_sha ${FROZEN_CONTRACT.contractSha.slice(0, 12)} · openapi ${FROZEN_CONTRACT.openapiSha256.slice(0, 12)}`
}

/**
 * Declarative backend field map. `null` means "not calibrated yet".
 *
 * Deliberately one object: calibration becomes a single-diff change, and a
 * reviewer can confirm at a glance that no backend name lives elsewhere.
 */
const CONTRACT: Record<string, string> | null = null

function requireCalibrated(endpoint: string): void {
  if (!isContractFrozen() || CONTRACT === null) {
    throw new ContractPendingError(endpoint)
  }
}

// ---------------------------------------------------------------------------
// Structural helpers. Shared so the calibrated implementation reuses these
// instead of ad-hoc casts, and so tests can assert the boundary behaviour.
// ---------------------------------------------------------------------------

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function fail(endpoint: string, detail: string): never {
  throw new ContractError(`${endpoint} 的响应与冻结契约不一致：${detail}`)
}

function requireRecord(value: unknown, endpoint: string, where: string): Record<string, unknown> {
  if (!isRecord(value)) {
    fail(endpoint, `${where} 应为对象，实际为 ${Array.isArray(value) ? 'array' : typeof value}。`)
  }
  return value
}

function requireString(value: unknown, endpoint: string, where: string): string {
  if (typeof value !== 'string' || value.length === 0) {
    fail(endpoint, `${where} 应为非空字符串。`)
  }
  return value
}

function optionalString(value: unknown, endpoint: string, where: string): string | null {
  if (value === null || value === undefined) {
    return null
  }
  if (typeof value !== 'string') {
    fail(endpoint, `${where} 应为字符串或 null。`)
  }
  return value
}

function requireInt(value: unknown, endpoint: string, where: string): number {
  if (typeof value !== 'number' || !Number.isInteger(value)) {
    fail(endpoint, `${where} 应为整数。`)
  }
  return value
}

function optionalInt(value: unknown, endpoint: string, where: string): number | null {
  if (value === null || value === undefined) {
    return null
  }
  return requireInt(value, endpoint, where)
}

function requireBoolean(value: unknown, endpoint: string, where: string): boolean {
  if (typeof value !== 'boolean') {
    fail(endpoint, `${where} 应为布尔值。`)
  }
  return value
}

function requireEnum<T extends string>(
  value: unknown,
  allowed: readonly T[],
  endpoint: string,
  where: string,
): T {
  if (typeof value !== 'string' || !allowed.includes(value as T)) {
    fail(endpoint, `${where} 必须是 ${allowed.join(' / ')} 之一，实际为 ${JSON.stringify(value)}。`)
  }
  return value as T
}

function requireArray(value: unknown, endpoint: string, where: string): unknown[] {
  if (!Array.isArray(value)) {
    fail(endpoint, `${where} 应为数组。`)
  }
  return value
}

const TODAY_STATUSES: readonly TodayStatus[] = [
  'not_started',
  'in_progress',
  'completed',
  'extra_available',
]

const AI_STATES: readonly AiPracticeState[] = [
  'not_available',
  'not_configured',
  'available',
  'unknown',
]

const BLANK_TYPES: readonly SpellingBlankType[] = ['full', 'partial', 'first_letter']

export const contractHelpers = {
  isRecord,
  requireRecord,
  requireString,
  optionalString,
  requireInt,
  optionalInt,
  requireBoolean,
  requireEnum,
  requireArray,
  TODAY_STATUSES,
  AI_STATES,
  BLANK_TYPES,
  EXAM_TARGETS,
  MEMORY_MODULES,
} as const

// ---------------------------------------------------------------------------
// Profile
// ---------------------------------------------------------------------------

export function parseLearningProfile(payload: unknown): LearningProfile {
  requireCalibrated('/users/me/profile')
  void requireRecord(payload, '/users/me/profile', '响应体')
  return fail('/users/me/profile', '适配层尚未按冻结 OpenAPI 校准。')
}

export function serializeProfileUpdate(update: LearningProfileUpdate): unknown {
  requireCalibrated('PATCH /users/me/profile')
  void update
  return fail('PATCH /users/me/profile', '适配层尚未按冻结 OpenAPI 校准。')
}

// ---------------------------------------------------------------------------
// Today plan / stats / heartbeat
// ---------------------------------------------------------------------------

export function parseTodayPlan(payload: unknown): TodayPlan {
  requireCalibrated('/learning/today')
  void requireRecord(payload, '/learning/today', '响应体')
  return fail('/learning/today', '适配层尚未按冻结 OpenAPI 校准。')
}

export function parseLearningStats(payload: unknown): LearningStats {
  requireCalibrated('/learning/stats')
  void requireRecord(payload, '/learning/stats', '响应体')
  return fail('/learning/stats', '适配层尚未按冻结 OpenAPI 校准。')
}

export function serializeHeartbeat(input: { windowSeconds: number }): unknown {
  requireCalibrated('POST /learning/heartbeat')
  void input
  return fail('POST /learning/heartbeat', '适配层尚未按冻结 OpenAPI 校准。')
}

// ---------------------------------------------------------------------------
// Memory config / sessions / events
// ---------------------------------------------------------------------------

export function parseMemoryConfig(payload: unknown): MemoryConfig {
  requireCalibrated('/memory/config')
  void requireRecord(payload, '/memory/config', '响应体')
  return fail('/memory/config', '适配层尚未按冻结 OpenAPI 校准。')
}

export function serializeMemoryConfig(config: MemoryConfig): unknown {
  requireCalibrated('PUT /memory/config')
  void config
  return fail('PUT /memory/config', '适配层尚未按冻结 OpenAPI 校准。')
}

export function serializeSessionStart(module: MemoryModule): unknown {
  requireCalibrated('POST /memory/sessions')
  void module
  return fail('POST /memory/sessions', '适配层尚未按冻结 OpenAPI 校准。')
}

export function parseSessionSummary(payload: unknown): SessionSummary {
  requireCalibrated('POST /memory/sessions')
  void requireRecord(payload, 'POST /memory/sessions', '响应体')
  return fail('POST /memory/sessions', '适配层尚未按冻结 OpenAPI 校准。')
}

export function parseStudyQuestion(payload: unknown, module: MemoryModule): StudyQuestion {
  const endpoint = `GET /memory/sessions/{id} (${module})`
  requireCalibrated(endpoint)
  void requireRecord(payload, endpoint, '响应体')
  return fail(endpoint, '适配层尚未按冻结 OpenAPI 校准。')
}

export function serializeStudyEvent(event: StudyEventInput): unknown {
  requireCalibrated('POST /memory/sessions/{id}/events')
  void event
  return fail('POST /memory/sessions/{id}/events', '适配层尚未按冻结 OpenAPI 校准。')
}

export function parseStudyFeedback(payload: unknown): StudyFeedback {
  requireCalibrated('POST /memory/sessions/{id}/events')
  void requireRecord(payload, 'POST /memory/sessions/{id}/events', '响应体')
  return fail('POST /memory/sessions/{id}/events', '适配层尚未按冻结 OpenAPI 校准。')
}

// ---------------------------------------------------------------------------
// Mastered / restore / mistakes
// ---------------------------------------------------------------------------

export function parseMasteryOutcome(payload: unknown): MasteryOutcome {
  requireCalibrated('PATCH /memory/words/{state_id}/master')
  void requireRecord(payload, 'PATCH /memory/words/{state_id}/master', '响应体')
  return fail('PATCH /memory/words/{state_id}/master', '适配层尚未按冻结 OpenAPI 校准。')
}

export function parseLearnedWordState(payload: unknown): LearnedWordState {
  requireCalibrated('PATCH /memory/words/{state_id}/restore')
  void requireRecord(payload, 'PATCH /memory/words/{state_id}/restore', '响应体')
  return fail('PATCH /memory/words/{state_id}/restore', '适配层尚未按冻结 OpenAPI 校准。')
}

export function parseMistakes(payload: unknown): PagedMistakes {
  requireCalibrated('/memory/mistakes')
  void requireRecord(payload, '/memory/mistakes', '响应体')
  return fail('/memory/mistakes', '适配层尚未按冻结 OpenAPI 校准。')
}

// ---------------------------------------------------------------------------
// Mistake priority
// ---------------------------------------------------------------------------

/**
 * Marks a mistake for priority review.
 *
 * The UI intent is only "this entry is (or is no longer) a priority". Queue
 * ordering, the next due date and any mastery effect remain server decisions,
 * so none of them is expressible from here — and the backend field name for the
 * flag stays unknown until calibration.
 */
export function serializeMistakePriority(update: MistakePriorityUpdate): unknown {
  requireCalibrated('PATCH /memory/mistakes/{entry_id}/priority')
  void update
  return fail('PATCH /memory/mistakes/{entry_id}/priority', '适配层尚未按冻结 OpenAPI 校准。')
}

export type { MemoryModulePreference }
