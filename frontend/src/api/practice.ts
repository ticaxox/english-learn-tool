/**
 * T-FE-006 practice client.
 *
 * Final contract: d6dcdbf8be4468526a01e33ed1cc77fc116d7c19
 * raw 636592305ffc9eee418287c57dfe99898a101c4cb1c7c9bdc3e43598b63d73a7
 * semantic a4560add2686b806ee5a5fa766d74b44688b3b223b69a5b2ade227e9a136b32e
 *
 * Answer-bearing fields are accepted only in post-submit result responses. The
 * public session parser rejects any accidental pre-submit answer/explanation/
 * score fields instead of keeping them in a client view model.
 */
import { apiClient } from './client'
import { ContractError } from './errors'

export type PracticeType = 'fill_blank' | 'reading' | 'translation' | 'writing' | 'mixed'
export type PracticeSource = 'today_new' | 'today_review' | 'memory_mistakes' | 'whole_book' | 'difficulty'
export type PracticeDifficulty = 'CET4' | 'CET6' | 'POSTGRAD' | 'IELTS' | 'TOEFL'
export type PracticeSessionStatus = 'generating' | 'ready' | 'submitted' | 'failed' | 'cancelled'
export type PracticeSubmissionStatus = 'scoring' | 'completed' | 'failed'
export type PracticeQuotaKind = 'coach_messages' | 'question_generation' | 'subjective_grading'

export interface PracticeCreateInput {
  practiceType: PracticeType
  source: PracticeSource
  count: number
  difficulty: PracticeDifficulty | null
  wordbookId: string | null
}

export interface PracticeOption {
  id: string
  text: string
  textZh: string | null
}

export interface PracticeQuestion {
  id: string
  position: number
  questionType: PracticeType
  prompt: string | null
  sentence: string | null
  sentenceZh: string | null
  article: string | null
  articleZh: string | null
  options: PracticeOption[]
  sourceText: string | null
  sourceLanguage: 'en' | 'zh' | null
  targetLanguage: 'en' | 'zh' | null
  requirements: string[]
  targetEntryIds: string[]
}

export interface PracticeSession {
  id: string
  practiceType: PracticeType
  source: PracticeSource
  difficulty: PracticeDifficulty | null
  wordbookId: string | null
  status: PracticeSessionStatus
  questionCount: number
  generationNumber: number
  draftVersion: number
  draftAnswers: Record<string, string>
  questions: PracticeQuestion[]
  jobStatus: string | null
  errorCode: string | null
  errorMessage: string | null
  createdAt: string
  updatedAt: string
}

export interface PracticeDraftInput {
  version: number
  answers: Record<string, string>
}

export interface PracticeDraftResult {
  sessionId: string
  draftVersion: number
  answers: Record<string, string>
  savedAt: string
}

export interface PracticeAnswerInput {
  questionId: string
  answer: string
}

export interface PracticeGradingDimension {
  name: string
  score: number
  maxScore: number
}

export interface PracticeQuestionResult {
  questionId: string
  questionType: PracticeType
  userAnswer: string
  gradedCorrect: boolean | null
  isMistake: boolean
  score: number | null
  correctChoiceId: string | null
  correctOptionText: string | null
  explanation: string | null
  referenceContent: string | null
  dimensions: PracticeGradingDimension[]
  errors: string[]
  suggestions: string[]
}

export interface PracticeResult {
  sessionId: string
  submissionId: string
  status: PracticeSubmissionStatus
  score: number | null
  correctCount: number | null
  totalQuestions: number
  wrongCount: number | null
  questions: PracticeQuestionResult[]
  mistakes: PracticeQuestionResult[]
  errorCode: string | null
  errorMessage: string | null
  submittedAt: string | null
}

export interface PracticeSubmitResponse {
  sessionId: string
  submissionId: string
  status: PracticeSubmissionStatus
  result: PracticeResult | null
  errorCode: string | null
  errorMessage: string | null
}

export interface PracticeRecordSummary {
  id: string
  practiceType: PracticeType
  source: PracticeSource
  difficulty: PracticeDifficulty | null
  score: number | null
  correctCount: number | null
  totalQuestions: number
  wrongCount: number | null
  submittedAt: string | null
  status: PracticeSessionStatus
}

export interface PracticeRecordDetail extends PracticeRecordSummary {
  result: PracticeResult | null
}

export interface PracticeRecordPage {
  items: PracticeRecordSummary[]
  total: number
  offset: number
  limit: number
}

export interface PracticeDeleteResult {
  deletedCount: number
  deletedIds: string[]
}

export interface PracticeEvent {
  id: string
  sessionId: string | null
  eventType: string
  metadata: Record<string, unknown>
  createdAt: string
}

export interface PracticeEventPage {
  items: PracticeEvent[]
  total: number
  offset: number
  limit: number
}

export interface PracticeQuota {
  quotaKind: PracticeQuotaKind
  limit: number
  used: number
  reserved: number
  remaining: number
}

export interface PracticeUsage {
  localDate: string
  quotas: PracticeQuota[]
  concurrency: { limit: number; inUse: number }
}

export interface PracticeRecordQuery {
  practiceType?: PracticeType | ''
  source?: PracticeSource | ''
  onlyMistakes?: boolean
  offset?: number
  limit?: number
}

const PRACTICE_TYPES: readonly PracticeType[] = ['fill_blank', 'reading', 'translation', 'writing', 'mixed']
const PRACTICE_SOURCES: readonly PracticeSource[] = [
  'today_new',
  'today_review',
  'memory_mistakes',
  'whole_book',
  'difficulty',
]
const DIFFICULTIES: readonly PracticeDifficulty[] = ['CET4', 'CET6', 'POSTGRAD', 'IELTS', 'TOEFL']
const SESSION_STATUSES: readonly PracticeSessionStatus[] = ['generating', 'ready', 'submitted', 'failed', 'cancelled']
const SUBMISSION_STATUSES: readonly PracticeSubmissionStatus[] = ['scoring', 'completed', 'failed']
const QUOTA_KINDS: readonly PracticeQuotaKind[] = ['coach_messages', 'question_generation', 'subjective_grading']
const FORBIDDEN_PUBLIC_KEYS = new Set([
  'correct_option_id',
  'correct_option_text',
  'explanation',
  'reference_content',
  'is_correct',
  'is_mistake',
  'score',
  'dimensions',
  'errors',
  'suggestions',
])

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
  if (typeof value !== 'number' || !Number.isInteger(value) || value < min) fail(context, `${field} 应为不小于 ${min} 的整数`)
  return value
}
function nullableInteger(value: unknown, context: string, field: string): number | null {
  if (value === null || value === undefined) return null
  return integerValue(value, context, field)
}
function nullableNumber(value: unknown, context: string, field: string): number | null {
  if (value === null || value === undefined) return null
  if (typeof value !== 'number' || !Number.isFinite(value)) fail(context, `${field} 应为有限数字或 null`)
  return value
}
function booleanValue(value: unknown, context: string, field: string): boolean {
  if (typeof value !== 'boolean') fail(context, `${field} 应为布尔值`)
  return value
}
function enumValue<T extends string>(value: unknown, allowed: readonly T[], context: string, field: string): T {
  if (typeof value !== 'string' || !allowed.includes(value as T)) fail(context, `${field} 必须是 ${allowed.join(' / ')} 之一`)
  return value as T
}
function nullableEnum<T extends string>(value: unknown, allowed: readonly T[], context: string, field: string): T | null {
  if (value === null || value === undefined) return null
  return enumValue(value, allowed, context, field)
}
function stringArray(value: unknown, context: string, field: string): string[] {
  if (!Array.isArray(value)) fail(context, `${field} 应为字符串数组`)
  return value.map((item, index) => stringValue(item, context, `${field}[${index}]`))
}
function stringMap(value: unknown, context: string, field: string): Record<string, string> {
  if (!isRecord(value)) fail(context, `${field} 应为对象`)
  const result: Record<string, string> = {}
  for (const [key, item] of Object.entries(value)) {
    if (typeof item !== 'string') fail(context, `${field}.${key} 应为字符串`)
    result[key] = item
  }
  return result
}
function recordMap(value: unknown, context: string, field: string): Record<string, unknown> {
  if (!isRecord(value)) fail(context, `${field} 应为对象`)
  return { ...value }
}
function assertNoPrivateQuestionFields(value: unknown, context: string): void {
  if (Array.isArray(value)) {
    value.forEach((item, index) => assertNoPrivateQuestionFields(item, `${context}[${index}]`))
    return
  }
  if (!isRecord(value)) return
  for (const key of Object.keys(value)) {
    if (FORBIDDEN_PUBLIC_KEYS.has(key)) fail(context, `提交前响应包含禁止字段 ${key}`)
  }
  Object.values(value).forEach((item) => assertNoPrivateQuestionFields(item, context))
}

function parseOption(value: unknown, context: string): PracticeOption {
  const body = record(value, context)
  return {
    id: stringValue(body.id, context, 'id'),
    text: stringValue(body.text, context, 'text'),
    textZh: nullableString(body.text_zh, context, 'text_zh'),
  }
}

function parseQuestion(value: unknown, index: number): PracticeQuestion {
  const context = `练习题目[${index}]`
  const body = record(value, context)
  assertNoPrivateQuestionFields(body, context)
  if (!Array.isArray(body.options)) fail(context, 'options 应为数组')
  if (!Array.isArray(body.requirements)) fail(context, 'requirements 应为数组')
  if (!Array.isArray(body.target_entry_ids)) fail(context, 'target_entry_ids 应为数组')
  return {
    id: stringValue(body.id, context, 'id'),
    position: integerValue(body.position, context, 'position'),
    questionType: enumValue(body.question_type, PRACTICE_TYPES, context, 'question_type'),
    prompt: nullableString(body.prompt, context, 'prompt'),
    sentence: nullableString(body.sentence, context, 'sentence'),
    sentenceZh: nullableString(body.sentence_zh, context, 'sentence_zh'),
    article: nullableString(body.article, context, 'article'),
    articleZh: nullableString(body.article_zh, context, 'article_zh'),
    options: body.options.map((option, optionIndex) => parseOption(option, `${context}.options[${optionIndex}]`)),
    sourceText: nullableString(body.source_text, context, 'source_text'),
    sourceLanguage: nullableEnum(body.source_language, ['en', 'zh'] as const, context, 'source_language'),
    targetLanguage: nullableEnum(body.target_language, ['en', 'zh'] as const, context, 'target_language'),
    requirements: stringArray(body.requirements, context, 'requirements'),
    targetEntryIds: stringArray(body.target_entry_ids, context, 'target_entry_ids'),
  }
}

export function parsePracticeSession(payload: unknown): PracticeSession {
  const context = '练习会话响应'
  const body = record(payload, context)
  if (!Array.isArray(body.questions)) fail(context, 'questions 应为数组')
  return {
    id: stringValue(body.id, context, 'id'),
    practiceType: enumValue(body.practice_type, PRACTICE_TYPES, context, 'practice_type'),
    source: enumValue(body.source, PRACTICE_SOURCES, context, 'source'),
    difficulty: nullableEnum(body.difficulty, DIFFICULTIES, context, 'difficulty'),
    wordbookId: nullableString(body.wordbook_id, context, 'wordbook_id'),
    status: enumValue(body.status, SESSION_STATUSES, context, 'status'),
    questionCount: integerValue(body.question_count, context, 'question_count'),
    generationNumber: integerValue(body.generation_number, context, 'generation_number'),
    draftVersion: integerValue(body.draft_version, context, 'draft_version'),
    draftAnswers: stringMap(body.draft_answers ?? {}, context, 'draft_answers'),
    questions: body.questions.map((item, index) => parseQuestion(item, index)),
    jobStatus: nullableString(body.job_status, context, 'job_status'),
    errorCode: nullableString(body.error_code, context, 'error_code'),
    errorMessage: nullableString(body.error_message, context, 'error_message'),
    createdAt: stringValue(body.created_at, context, 'created_at'),
    updatedAt: stringValue(body.updated_at, context, 'updated_at'),
  }
}

export function parsePracticeDraft(payload: unknown): PracticeDraftResult {
  const context = '练习草稿响应'
  const body = record(payload, context)
  return {
    sessionId: stringValue(body.session_id, context, 'session_id'),
    draftVersion: integerValue(body.draft_version, context, 'draft_version'),
    answers: stringMap(body.answers, context, 'answers'),
    savedAt: stringValue(body.saved_at, context, 'saved_at'),
  }
}

function parseDimension(value: unknown, context: string): PracticeGradingDimension {
  const body = record(value, context)
  return {
    name: stringValue(body.name, context, 'name'),
    score: nullableNumber(body.score, context, 'score') ?? 0,
    maxScore: nullableNumber(body.max_score, context, 'max_score') ?? 0,
  }
}

function parseQuestionResult(value: unknown, context: string): PracticeQuestionResult {
  const body = record(value, context)
  if (!Array.isArray(body.dimensions) || !Array.isArray(body.errors) || !Array.isArray(body.suggestions)) {
    fail(context, 'dimensions / errors / suggestions 应为数组')
  }
  return {
    questionId: stringValue(body.question_id, context, 'question_id'),
    questionType: enumValue(body.question_type, PRACTICE_TYPES, context, 'question_type'),
    userAnswer: stringValue(body.user_answer, context, 'user_answer'),
    gradedCorrect: body.is_correct === null || body.is_correct === undefined ? null : booleanValue(body.is_correct, context, 'is_correct'),
    isMistake: body.is_mistake === undefined ? false : booleanValue(body.is_mistake, context, 'is_mistake'),
    score: nullableNumber(body.score, context, 'score'),
    correctChoiceId: nullableString(body.correct_option_id, context, 'correct_option_id'),
    correctOptionText: nullableString(body.correct_option_text, context, 'correct_option_text'),
    explanation: nullableString(body.explanation, context, 'explanation'),
    referenceContent: nullableString(body.reference_content, context, 'reference_content'),
    dimensions: body.dimensions.map((item, index) => parseDimension(item, `${context}.dimensions[${index}]`)),
    errors: stringArray(body.errors, context, 'errors'),
    suggestions: stringArray(body.suggestions, context, 'suggestions'),
  }
}

export function parsePracticeResult(payload: unknown): PracticeResult {
  const context = '练习结果响应'
  const body = record(payload, context)
  if (!Array.isArray(body.questions) || !Array.isArray(body.mistakes)) fail(context, 'questions / mistakes 应为数组')
  return {
    sessionId: stringValue(body.session_id, context, 'session_id'),
    submissionId: stringValue(body.submission_id, context, 'submission_id'),
    status: enumValue(body.status, SUBMISSION_STATUSES, context, 'status'),
    score: nullableNumber(body.score, context, 'score'),
    correctCount: nullableInteger(body.correct_count, context, 'correct_count'),
    totalQuestions: integerValue(body.total_questions, context, 'total_questions'),
    wrongCount: nullableInteger(body.wrong_count, context, 'wrong_count'),
    questions: body.questions.map((item, index) => parseQuestionResult(item, `${context}.questions[${index}]`)),
    mistakes: body.mistakes.map((item, index) => parseQuestionResult(item, `${context}.mistakes[${index}]`)),
    errorCode: nullableString(body.error_code, context, 'error_code'),
    errorMessage: nullableString(body.error_message, context, 'error_message'),
    submittedAt: nullableString(body.submitted_at, context, 'submitted_at'),
  }
}

export function parsePracticeSubmit(payload: unknown): PracticeSubmitResponse {
  const context = '练习提交响应'
  const body = record(payload, context)
  return {
    sessionId: stringValue(body.session_id, context, 'session_id'),
    submissionId: stringValue(body.submission_id, context, 'submission_id'),
    status: enumValue(body.status, SUBMISSION_STATUSES, context, 'status'),
    result: body.result === null || body.result === undefined ? null : parsePracticeResult(body.result),
    errorCode: nullableString(body.error_code, context, 'error_code'),
    errorMessage: nullableString(body.error_message, context, 'error_message'),
  }
}

function parseRecordSummary(value: unknown, context: string): PracticeRecordSummary {
  const body = record(value, context)
  return {
    id: stringValue(body.id, context, 'id'),
    practiceType: enumValue(body.practice_type, PRACTICE_TYPES, context, 'practice_type'),
    source: enumValue(body.source, PRACTICE_SOURCES, context, 'source'),
    difficulty: nullableEnum(body.difficulty, DIFFICULTIES, context, 'difficulty'),
    score: nullableNumber(body.score, context, 'score'),
    correctCount: nullableInteger(body.correct_count, context, 'correct_count'),
    totalQuestions: integerValue(body.total_questions, context, 'total_questions'),
    wrongCount: nullableInteger(body.wrong_count, context, 'wrong_count'),
    submittedAt: nullableString(body.submitted_at, context, 'submitted_at'),
    status: enumValue(body.status, SESSION_STATUSES, context, 'status'),
  }
}

export function parsePracticeRecordPage(payload: unknown): PracticeRecordPage {
  const context = '练习记录列表响应'
  const body = record(payload, context)
  if (!Array.isArray(body.items)) fail(context, 'items 应为数组')
  return {
    items: body.items.map((item, index) => parseRecordSummary(item, `${context}.items[${index}]`)),
    total: integerValue(body.total, context, 'total'),
    offset: integerValue(body.offset, context, 'offset'),
    limit: integerValue(body.limit, context, 'limit', 1),
  }
}

export function parsePracticeRecordDetail(payload: unknown): PracticeRecordDetail {
  const context = '练习记录详情响应'
  const body = record(payload, context)
  return {
    ...parseRecordSummary(body, context),
    result: body.result === null || body.result === undefined ? null : parsePracticeResult(body.result),
  }
}

export function parsePracticeDelete(payload: unknown): PracticeDeleteResult {
  const context = '练习记录删除响应'
  const body = record(payload, context)
  if (!Array.isArray(body.deleted_ids)) fail(context, 'deleted_ids 应为数组')
  return {
    deletedCount: integerValue(body.deleted_count, context, 'deleted_count'),
    deletedIds: stringArray(body.deleted_ids, context, 'deleted_ids'),
  }
}

export function parsePracticeEventPage(payload: unknown): PracticeEventPage {
  const context = '练习事件列表响应'
  const body = record(payload, context)
  if (!Array.isArray(body.items)) fail(context, 'items 应为数组')
  return {
    items: body.items.map((item, index) => {
      const event = record(item, `${context}.items[${index}]`)
      return {
        id: stringValue(event.id, context, `items[${index}].id`),
        sessionId: nullableString(event.session_id, context, `items[${index}].session_id`),
        eventType: stringValue(event.event_type, context, `items[${index}].event_type`),
        metadata: recordMap(event.metadata ?? {}, context, `items[${index}].metadata`),
        createdAt: stringValue(event.created_at, context, `items[${index}].created_at`),
      }
    }),
    total: integerValue(body.total, context, 'total'),
    offset: integerValue(body.offset, context, 'offset'),
    limit: integerValue(body.limit, context, 'limit', 1),
  }
}

export function parsePracticeUsage(payload: unknown): PracticeUsage {
  const context = '练习额度响应'
  const body = record(payload, context)
  if (!Array.isArray(body.quotas)) fail(context, 'quotas 应为数组')
  const concurrency = record(body.concurrency, `${context}.concurrency`)
  return {
    localDate: stringValue(body.local_date, context, 'local_date'),
    quotas: body.quotas.map((item, index) => {
      const quota = record(item, `${context}.quotas[${index}]`)
      return {
        quotaKind: enumValue(quota.quota_kind, QUOTA_KINDS, context, `quotas[${index}].quota_kind`),
        limit: integerValue(quota.limit, context, `quotas[${index}].limit`, -1),
        used: integerValue(quota.used, context, `quotas[${index}].used`),
        reserved: integerValue(quota.reserved, context, `quotas[${index}].reserved`),
        remaining: integerValue(quota.remaining, context, `quotas[${index}].remaining`, -1),
      }
    }),
    concurrency: {
      limit: integerValue(concurrency.limit, context, 'concurrency.limit'),
      inUse: integerValue(concurrency.in_use, context, 'concurrency.in_use'),
    },
  }
}

export function buildPracticeRecordQuery(query: PracticeRecordQuery): string {
  const params = new URLSearchParams()
  if (query.practiceType) params.set('practice_type', query.practiceType)
  if (query.source) params.set('source', query.source)
  if (query.onlyMistakes) params.set('only_mistakes', 'true')
  params.set('offset', String(query.offset ?? 0))
  params.set('limit', String(query.limit ?? 20))
  return `?${params.toString()}`
}

function serializeCreate(input: PracticeCreateInput): Record<string, unknown> {
  return {
    practice_type: input.practiceType,
    source: input.source,
    count: input.count,
    difficulty: input.difficulty,
    wordbook_id: input.wordbookId,
  }
}

export async function createPracticeSession(input: PracticeCreateInput, idempotencyKey: string): Promise<PracticeSession> {
  const payload = await apiClient.post('/practice/sessions', serializeCreate(input), {
    retryCount: 0,
    headers: { 'Idempotency-Key': idempotencyKey },
  })
  return parsePracticeSession(payload)
}

export async function getPracticeSession(sessionId: string): Promise<PracticeSession> {
  return parsePracticeSession(await apiClient.get(`/practice/sessions/${encodeURIComponent(sessionId)}`))
}

export async function startPracticeSession(sessionId: string): Promise<PracticeSession> {
  return parsePracticeSession(
    await apiClient.post(`/practice/sessions/${encodeURIComponent(sessionId)}/start`, undefined, { retryCount: 0 }),
  )
}

export async function savePracticeDraft(sessionId: string, input: PracticeDraftInput): Promise<PracticeDraftResult> {
  const payload = await apiClient.put(
    `/practice/sessions/${encodeURIComponent(sessionId)}/draft`,
    { version: input.version, answers: input.answers },
    { retryCount: 0 },
  )
  return parsePracticeDraft(payload)
}

export interface PracticeSessionSummary {
  id: string
  practiceType: PracticeType
  source: PracticeSource
  status: PracticeSessionStatus
  questionCount: number
  score: number | null
  createdAt: string
  submittedAt: string | null
  errorCode: string | null
  errorMessage: string | null
}

function parseSessionSummary(value: unknown, index: number): PracticeSessionSummary {
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    throw new Error(`练习会话第 ${index + 1} 条格式不正确。`)
  }
  const body = value as Record<string, unknown>
  const status = body.status
  if (!['generating', 'ready', 'submitted', 'failed', 'cancelled'].includes(String(status))) {
    throw new Error('练习会话状态无法识别。')
  }
  return {
    id: String(body.id),
    practiceType: String(body.practice_type) as PracticeType,
    source: String(body.source) as PracticeSource,
    status: status as PracticeSessionStatus,
    questionCount: Number(body.question_count),
    score: typeof body.score === 'number' ? body.score : null,
    createdAt: String(body.created_at),
    submittedAt: typeof body.submitted_at === 'string' ? body.submitted_at : null,
    errorCode: typeof body.error_code === 'string' ? body.error_code : null,
    errorMessage: typeof body.error_message === 'string' ? body.error_message : null,
  }
}

export async function listRecentPracticeSessions(limit = 20): Promise<PracticeSessionSummary[]> {
  const payload = await apiClient.get(`/practice/sessions?limit=${limit}`)
  const body = payload as Record<string, unknown>
  return Array.isArray(body.items)
    ? body.items.map((item, index) => parseSessionSummary(item, index))
    : []
}

export async function deletePracticeSession(id: string): Promise<void> {
  await apiClient.delete<void>(`/practice/sessions/${encodeURIComponent(id)}`, { retryCount: 0 })
}

export async function regeneratePracticeSession(sessionId: string, idempotencyKey: string): Promise<PracticeSession> {
  return parsePracticeSession(
    await apiClient.post(`/practice/sessions/${encodeURIComponent(sessionId)}/regenerate`, undefined, {
      retryCount: 0,
      headers: { 'Idempotency-Key': idempotencyKey },
    }),
  )
}

export async function submitPracticeSession(
  sessionId: string,
  answers: PracticeAnswerInput[],
  idempotencyKey: string,
): Promise<PracticeSubmitResponse> {
  const payload = await apiClient.post(
    `/practice/sessions/${encodeURIComponent(sessionId)}/submit`,
    { answers: answers.map((answer) => ({ question_id: answer.questionId, answer: answer.answer })) },
    { retryCount: 0, headers: { 'Idempotency-Key': idempotencyKey } },
  )
  return parsePracticeSubmit(payload)
}

export async function getPracticeResult(sessionId: string): Promise<PracticeResult> {
  return parsePracticeResult(await apiClient.get(`/practice/sessions/${encodeURIComponent(sessionId)}/result`))
}

export async function listPracticeRecords(query: PracticeRecordQuery = {}): Promise<PracticeRecordPage> {
  return parsePracticeRecordPage(await apiClient.get(`/practice/records${buildPracticeRecordQuery(query)}`))
}

export async function listPracticeMistakes(query: Omit<PracticeRecordQuery, 'source' | 'onlyMistakes'> = {}): Promise<PracticeRecordPage> {
  const params = new URLSearchParams()
  if (query.practiceType) params.set('practice_type', query.practiceType)
  params.set('offset', String(query.offset ?? 0))
  params.set('limit', String(query.limit ?? 20))
  return parsePracticeRecordPage(await apiClient.get(`/practice/mistakes?${params.toString()}`))
}

export async function getPracticeRecord(sessionId: string): Promise<PracticeRecordDetail> {
  return parsePracticeRecordDetail(await apiClient.get(`/practice/records/${encodeURIComponent(sessionId)}`))
}

export async function deletePracticeRecords(ids: string[], idempotencyKey: string): Promise<PracticeDeleteResult> {
  const payload = await apiClient.request('/practice/records/bulk', {
    method: 'DELETE',
    body: { ids },
    retryCount: 0,
    headers: { 'Idempotency-Key': idempotencyKey },
  })
  return parsePracticeDelete(payload)
}

export async function listPracticeEvents(offset = 0, limit = 50): Promise<PracticeEventPage> {
  return parsePracticeEventPage(await apiClient.get(`/practice/events?offset=${offset}&limit=${limit}`))
}

export async function fetchPracticeUsage(localDate?: string): Promise<PracticeUsage> {
  const suffix = localDate ? `?local_date=${encodeURIComponent(localDate)}` : ''
  return parsePracticeUsage(await apiClient.get(`/ai/usage/me${suffix}`))
}

export const PRACTICE_TYPE_LABELS: Record<PracticeType, string> = {
  fill_blank: '填空',
  reading: '阅读',
  translation: '翻译',
  writing: '作文',
  mixed: '随机',
}

export const PRACTICE_SOURCE_LABELS: Record<PracticeSource, string> = {
  today_new: '今日新词',
  today_review: '今日复习',
  memory_mistakes: '记忆错词',
  whole_book: '整本词书',
  difficulty: '按难度',
}

export const PRACTICE_STATUS_LABELS: Record<PracticeSessionStatus, string> = {
  generating: '生成中',
  ready: '可作答',
  submitted: '已提交',
  failed: '生成失败',
  cancelled: '已取消',
}

export const PRACTICE_SUBMISSION_LABELS: Record<PracticeSubmissionStatus, string> = {
  scoring: '评分中',
  completed: '已完成',
  failed: '评分失败',
}

export const PRACTICE_QUOTA_LABELS: Record<PracticeQuotaKind, string> = {
  coach_messages: '教练消息',
  question_generation: '题目生成',
  subjective_grading: '主观题评分',
}