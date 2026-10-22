import { apiClient } from './client'
import { ContractError } from './errors'

export type WordbookVisibility = 'organization' | 'private'
export type WordbookStatus = 'importing' | 'ready' | 'failed' | 'deleting'
export type WordbookField =
  | 'headword'
  | 'definition'
  | 'phonetic'
  | 'part_of_speech'
  | 'example'
  | 'example_translation'
export type DuplicateStrategy = 'merge' | 'reject'
export type ExportFormat = 'csv' | 'txt' | 'pdf'
export type TaskStatus = 'queued' | 'running' | 'succeeded' | 'failed' | 'expired'

export interface WordbookPermissions {
  can_activate: boolean
  can_export: boolean
  can_delete: boolean
}

export interface Wordbook {
  id: string
  name: string
  description: string | null
  visibility: WordbookVisibility
  status: WordbookStatus
  entry_count: number
  is_active: boolean
  owner_id: string | null
  owner_display_name: string | null
  created_at: string
  updated_at: string
  import_progress: number | null
  import_error: string | null
  permissions: WordbookPermissions
}

export interface WordbookListQuery {
  search?: string
  visibility?: WordbookVisibility | ''
  cursor?: string | null
  limit?: number
}

export interface WordbookListPage {
  items: Wordbook[]
  next_cursor: string | null
  has_more: boolean
}

export interface WordbookEntryExample {
  sentence: string
  translation: string | null
}

export interface WordbookEntry {
  id: string
  headword: string
  phonetic: string | null
  part_of_speech: string | null
  definitions: string[]
  examples: WordbookEntryExample[]
}

export interface WordbookEntryPage {
  items: WordbookEntry[]
  next_cursor: string | null
  has_more: boolean
}

export interface WordbookDetail {
  wordbook: Wordbook
  entries: WordbookEntryPage
}

export interface ImportPreviewError {
  row_number: number | null
  column: string | null
  message: string
}

export interface WordbookImportPreview {
  preview_token: string
  expires_at: string
  detected_format: string
  encoding: string | null
  delimiter: string | null
  columns: string[]
  suggested_mapping: Partial<Record<WordbookField, string | null>>
  sample_rows: Array<Record<string, string | null>>
  total_rows: number
  importable_rows: number
  warning_count: number
  error_count: number
  errors: ImportPreviewError[]
}

export interface WordbookImportInput {
  visibility: WordbookVisibility
  name: string
  description: string
}

export interface ConfirmWordbookImportInput extends WordbookImportInput {
  preview_token: string
  mapping: Partial<Record<WordbookField, string | null>>
  ignored_columns: string[]
  duplicate_strategy: DuplicateStrategy
}

export interface ImportConfirmation {
  job_id: string
  wordbook_id: string
  status: string
}

export interface ActivationResult {
  active_wordbook_id: string
  wordbook: Wordbook | null
}

export interface ExportOptions {
  format: ExportFormat
  pdf_rows_per_page?: number
  pdf_words_per_line?: number
}

export interface ExportJob {
  job_id: string
  status: TaskStatus
  progress: number
  error_code: string | null
  error_message: string | null
  download_url: string | null
  expires_at: string | null
}

export interface ExportCreation {
  job_id: string
  status: TaskStatus
}

export interface DeletionReceipt {
  job_id: string | null
  status: 'deleting' | 'completed'
}

export class WordbookTaskError extends Error {
  readonly code: string

  constructor(code: string, message: string) {
    super(message)
    this.name = 'WordbookTaskError'
    this.code = code
    Object.setPrototypeOf(this, WordbookTaskError.prototype)
  }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function requiredString(record: Record<string, unknown>, key: string, context: string): string {
  const value = record[key]
  if (typeof value !== 'string' || !value.trim()) {
    throw new ContractError(`${context}缺少合法的 ${key}。`)
  }
  return value
}

function optionalString(record: Record<string, unknown>, key: string): string | null {
  const value = record[key]
  if (value === null || value === undefined) {
    return null
  }
  if (typeof value !== 'string') {
    throw new ContractError(`响应中的 ${key} 必须是字符串或 null。`)
  }
  return value
}

function requiredBoolean(record: Record<string, unknown>, key: string, context: string): boolean {
  const value = record[key]
  if (typeof value !== 'boolean') {
    throw new ContractError(`${context}缺少合法的 ${key}。`)
  }
  return value
}

function optionalBoolean(record: Record<string, unknown>, key: string): boolean {
  const value = record[key]
  return typeof value === 'boolean' ? value : false
}

function requiredInteger(record: Record<string, unknown>, key: string, context: string): number {
  const value = record[key]
  if (typeof value !== 'number' || !Number.isInteger(value) || value < 0) {
    throw new ContractError(`${context}缺少合法的 ${key}。`)
  }
  return value
}

function optionalPercentage(record: Record<string, unknown>, key: string): number | null {
  const value = record[key]
  if (value === null || value === undefined) {
    return null
  }
  if (typeof value !== 'number' || !Number.isFinite(value) || value < 0 || value > 100) {
    throw new ContractError(`响应中的 ${key} 必须是 0 到 100 的数字或 null。`)
  }
  return value
}

function parseVisibility(value: unknown, context: string): WordbookVisibility {
  if (value !== 'organization' && value !== 'private') {
    throw new ContractError(`${context}的 visibility 必须是 organization 或 private。`)
  }
  return value
}

function parseWordbookStatus(value: unknown, context: string): WordbookStatus {
  if (!['importing', 'ready', 'failed', 'deleting'].includes(String(value))) {
    throw new ContractError(`${context}的 status 必须是 importing、ready、failed 或 deleting。`)
  }
  return value as WordbookStatus
}

function parsePermissions(value: unknown): WordbookPermissions {
  if (!isRecord(value)) {
    return { can_activate: false, can_export: false, can_delete: false }
  }
  return {
    can_activate: optionalBoolean(value, 'can_activate'),
    can_export: optionalBoolean(value, 'can_export'),
    can_delete: optionalBoolean(value, 'can_delete'),
  }
}

export function parseWordbook(payload: unknown, context = '词书响应'): Wordbook {
  if (!isRecord(payload)) {
    throw new ContractError(`${context}不是对象。`)
  }

  return {
    id: requiredString(payload, 'id', context),
    name: requiredString(payload, 'name', context),
    description: optionalString(payload, 'description'),
    visibility: parseVisibility(payload.visibility, context),
    status: parseWordbookStatus(payload.status, context),
    entry_count: requiredInteger(payload, 'entry_count', context),
    is_active: requiredBoolean(payload, 'is_active', context),
    owner_id: optionalString(payload, 'owner_id'),
    owner_display_name: optionalString(payload, 'owner_display_name'),
    created_at: requiredString(payload, 'created_at', context),
    updated_at: requiredString(payload, 'updated_at', context),
    import_progress: optionalPercentage(payload, 'import_progress'),
    import_error: optionalString(payload, 'import_error'),
    permissions: parsePermissions(payload.permissions),
  }
}

export function buildWordbookListQuery(query: WordbookListQuery): string {
  const params = new URLSearchParams()
  const search = query.search?.trim()
  if (search) {
    params.set('search', search)
  }
  if (query.visibility) {
    params.set('visibility', query.visibility)
  }
  if (query.cursor) {
    params.set('cursor', query.cursor)
  }
  if (query.limit !== undefined) {
    params.set('limit', String(query.limit))
  }
  const serialized = params.toString()
  return serialized ? `?${serialized}` : ''
}

export function parseWordbookList(payload: unknown): WordbookListPage {
  if (!isRecord(payload) || !Array.isArray(payload.items)) {
    throw new ContractError('词书列表响应必须包含 items 数组。')
  }
  const nextCursor = optionalString(payload, 'next_cursor')
  const hasMore = requiredBoolean(payload, 'has_more', '词书列表响应')
  return {
    items: payload.items.map((item, index) => parseWordbook(item, `词书列表第 ${index + 1} 项`)),
    next_cursor: nextCursor,
    has_more: hasMore,
  }
}

function parseEntryExample(payload: unknown, index: number): WordbookEntryExample {
  if (!isRecord(payload)) {
    throw new ContractError(`词条例句第 ${index + 1} 项不是对象。`)
  }
  return {
    sentence: requiredString(payload, 'sentence', '词条例句'),
    translation: optionalString(payload, 'translation'),
  }
}

function parseEntry(payload: unknown, index: number): WordbookEntry {
  if (!isRecord(payload)) {
    throw new ContractError(`词条第 ${index + 1} 项不是对象。`)
  }
  if (!Array.isArray(payload.definitions) || payload.definitions.length === 0) {
    throw new ContractError(`词条第 ${index + 1} 项必须包含非空 definitions 数组。`)
  }
  if (!payload.definitions.every((item) => typeof item === 'string')) {
    throw new ContractError(`词条第 ${index + 1} 项的 definitions 必须全部是字符串。`)
  }
  const examples = payload.examples === undefined || payload.examples === null ? [] : payload.examples
  if (!Array.isArray(examples)) {
    throw new ContractError(`词条第 ${index + 1} 项的 examples 必须是数组。`)
  }

  return {
    id: requiredString(payload, 'id', `词条第 ${index + 1} 项`),
    headword: requiredString(payload, 'headword', `词条第 ${index + 1} 项`),
    phonetic: optionalString(payload, 'phonetic'),
    part_of_speech: optionalString(payload, 'part_of_speech'),
    definitions: payload.definitions as string[],
    examples: examples.map(parseEntryExample),
  }
}

function parseEntryPage(payload: unknown): WordbookEntryPage {
  if (Array.isArray(payload)) {
    return { items: payload.map(parseEntry), next_cursor: null, has_more: false }
  }
  if (!isRecord(payload) || !Array.isArray(payload.items)) {
    throw new ContractError('词书详情响应必须包含 entries.items 数组。')
  }
  return {
    items: payload.items.map(parseEntry),
    next_cursor: optionalString(payload, 'next_cursor'),
    has_more: requiredBoolean(payload, 'has_more', '词条分页响应'),
  }
}

export function parseWordbookDetail(payload: unknown): WordbookDetail {
  if (!isRecord(payload)) {
    throw new ContractError('词书详情响应不是对象。')
  }
  const wordbookPayload = isRecord(payload.wordbook) ? payload.wordbook : payload
  const entriesPayload = payload.entries ?? payload.entry_page
  return {
    wordbook: parseWordbook(wordbookPayload, '词书详情'),
    entries: parseEntryPage(entriesPayload),
  }
}

export async function listWordbooks(query: WordbookListQuery = {}): Promise<WordbookListPage> {
  const payload = await apiClient.get<unknown>(`/wordbooks${buildWordbookListQuery(query)}`)
  return parseWordbookList(payload)
}

export async function getWordbookDetail(
  wordbookId: string,
  cursor: string | null = null,
  limit = 20,
): Promise<WordbookDetail> {
  const params = new URLSearchParams({ limit: String(limit) })
  if (cursor) {
    params.set('cursor', cursor)
  }
  const payload = await apiClient.get<unknown>(
    `/wordbooks/${encodeURIComponent(wordbookId)}?${params.toString()}`,
  )
  return parseWordbookDetail(payload)
}

function parseStringList(value: unknown, context: string): string[] {
  if (value === null || value === undefined) {
    return []
  }
  if (!Array.isArray(value) || !value.every((item) => typeof item === 'string')) {
    throw new ContractError(`${context}必须是字符串数组。`)
  }
  return value as string[]
}

function parseSampleRows(value: unknown): Array<Record<string, string | null>> {
  if (value === null || value === undefined) {
    return []
  }
  if (!Array.isArray(value)) {
    throw new ContractError('导入预览的 sample_rows 必须是数组。')
  }
  return value.map((item, index) => {
    if (!isRecord(item)) {
      throw new ContractError(`导入预览样例第 ${index + 1} 行不是对象。`)
    }
    const row: Record<string, string | null> = {}
    for (const [key, raw] of Object.entries(item)) {
      if (raw === null || raw === undefined) {
        row[key] = null
      } else if (typeof raw === 'string' || typeof raw === 'number' || typeof raw === 'boolean') {
        row[key] = String(raw)
      } else {
        throw new ContractError(`导入预览样例第 ${index + 1} 行的 ${key} 不是标量值。`)
      }
    }
    return row
  })
}

function parseMapping(value: unknown): Partial<Record<WordbookField, string | null>> {
  if (!isRecord(value)) {
    throw new ContractError('导入预览必须包含 suggested_mapping 对象。')
  }
  const mapping: Partial<Record<WordbookField, string | null>> = {}
  for (const field of ['headword', 'definition', 'phonetic', 'part_of_speech', 'example', 'example_translation'] as const) {
    const candidate = value[field]
    if (candidate === null || candidate === undefined) {
      mapping[field] = null
    } else if (typeof candidate === 'string') {
      mapping[field] = candidate
    } else {
      throw new ContractError(`导入映射中的 ${field} 必须是列名或 null。`)
    }
  }
  return mapping
}

function parsePreviewError(payload: unknown, index: number): ImportPreviewError {
  if (!isRecord(payload)) {
    throw new ContractError(`导入错误第 ${index + 1} 项不是对象。`)
  }
  const rowNumber = payload.row_number
  if (rowNumber !== null && rowNumber !== undefined && (typeof rowNumber !== 'number' || !Number.isInteger(rowNumber))) {
    throw new ContractError(`导入错误第 ${index + 1} 项的 row_number 必须是整数或 null。`)
  }
  return {
    row_number: typeof rowNumber === 'number' ? rowNumber : null,
    column: optionalString(payload, 'column'),
    message: requiredString(payload, 'message', `导入错误第 ${index + 1} 项`),
  }
}

export function parseWordbookImportPreview(payload: unknown): WordbookImportPreview {
  if (!isRecord(payload)) {
    throw new ContractError('导入预览响应不是对象。')
  }
  const errors = payload.errors === undefined ? [] : payload.errors
  if (!Array.isArray(errors)) {
    throw new ContractError('导入预览响应中的 errors 必须是数组。')
  }

  return {
    preview_token: requiredString(payload, 'preview_token', '导入预览响应'),
    expires_at: requiredString(payload, 'expires_at', '导入预览响应'),
    detected_format: requiredString(payload, 'detected_format', '导入预览响应'),
    encoding: optionalString(payload, 'encoding'),
    delimiter: optionalString(payload, 'delimiter'),
    columns: parseStringList(payload.columns, '导入预览响应中的 columns'),
    suggested_mapping: parseMapping(payload.suggested_mapping),
    sample_rows: parseSampleRows(payload.sample_rows),
    total_rows: requiredInteger(payload, 'total_rows', '导入预览响应'),
    importable_rows: requiredInteger(payload, 'importable_rows', '导入预览响应'),
    warning_count: requiredInteger(payload, 'warning_count', '导入预览响应'),
    error_count: requiredInteger(payload, 'error_count', '导入预览响应'),
    errors: errors.slice(0, 100).map(parsePreviewError),
  }
}

export async function previewWordbookImport(
  file: File,
  input: WordbookImportInput,
): Promise<WordbookImportPreview> {
  const formData = new FormData()
  formData.set('file', file, file.name)
  formData.set('name', input.name.trim())
  formData.set('description', input.description.trim())
  formData.set('visibility', input.visibility)
  const payload = await apiClient.post<unknown>('/wordbooks/import/preview', formData, {
    retryCount: 0,
  })
  return parseWordbookImportPreview(payload)
}

export function parseImportConfirmation(payload: unknown): ImportConfirmation {
  if (!isRecord(payload)) {
    throw new ContractError('导入确认响应不是对象。')
  }
  return {
    job_id: requiredString(payload, 'job_id', '导入确认响应'),
    wordbook_id: requiredString(payload, 'wordbook_id', '导入确认响应'),
    status: requiredString(payload, 'status', '导入确认响应'),
  }
}

export function validateRequiredMapping(
  mapping: Partial<Record<WordbookField, string | null>>,
): string | null {
  if (!mapping.headword) {
    return '请选择 headword（单词）对应的源列。'
  }
  if (!mapping.definition) {
    return '请选择 definition（释义）对应的源列。'
  }
  const selected = Object.values(mapping).filter((value): value is string => Boolean(value))
  if (new Set(selected).size !== selected.length) {
    return '同一个源列不能映射到多个目标字段。'
  }
  return null
}

export function isPreviewExpired(expiresAt: string, now = Date.now()): boolean {
  const expires = Date.parse(expiresAt)
  return Number.isNaN(expires) || expires <= now
}

function idempotencyHeaders(key?: string): HeadersInit {
  const normalized = key?.trim() || globalThis.crypto?.randomUUID?.() || `${Date.now()}-${Math.random()}`
  return { 'Idempotency-Key': normalized }
}

export async function confirmWordbookImport(
  input: ConfirmWordbookImportInput,
  idempotencyKey?: string,
): Promise<ImportConfirmation> {
  const payload = await apiClient.post<unknown>(
    '/wordbooks/import',
    input,
    { retryCount: 0, headers: idempotencyHeaders(idempotencyKey) },
  )
  return parseImportConfirmation(payload)
}

export async function activateWordbook(
  wordbookId: string,
  idempotencyKey?: string,
): Promise<ActivationResult> {
  const payload = await apiClient.post<unknown>(
    `/wordbooks/${encodeURIComponent(wordbookId)}/activate`,
    undefined,
    { retryCount: 0, headers: idempotencyHeaders(idempotencyKey) },
  )
  if (!isRecord(payload)) {
    throw new ContractError('激活词书响应不是对象。')
  }
  if (isRecord(payload.wordbook)) {
    const wordbook = parseWordbook(payload.wordbook, '激活词书响应')
    return { active_wordbook_id: wordbook.id, wordbook }
  }
  return {
    active_wordbook_id: requiredString(payload, 'active_wordbook_id', '激活词书响应'),
    wordbook: null,
  }
}

export async function createWordbookExport(
  wordbookId: string,
  options: ExportOptions,
  idempotencyKey?: string,
): Promise<ExportCreation> {
  const payload = await apiClient.post<unknown>(
    `/wordbooks/${encodeURIComponent(wordbookId)}/export`,
    options,
    { retryCount: 0, headers: idempotencyHeaders(idempotencyKey) },
  )
  if (!isRecord(payload)) {
    throw new ContractError('导出任务响应不是对象。')
  }
  return {
    job_id: requiredString(payload, 'job_id', '导出任务响应'),
    status: parseTaskStatus(payload.status, '导出任务响应'),
  }
}

function parseTaskStatus(value: unknown, context: string): TaskStatus {
  const normalized = value === 'completed' ? 'succeeded' : value
  if (!['queued', 'running', 'succeeded', 'failed', 'expired'].includes(String(normalized))) {
    throw new ContractError(`${context}的 status 不正确。`)
  }
  return normalized as TaskStatus
}

export function parseExportJob(payload: unknown): ExportJob {
  if (!isRecord(payload)) {
    throw new ContractError('导出任务状态响应不是对象。')
  }
  const progress = payload.progress
  if (progress !== undefined && (typeof progress !== 'number' || !Number.isFinite(progress) || progress < 0 || progress > 100)) {
    throw new ContractError('导出任务状态响应中的 progress 必须在 0 到 100 之间。')
  }
  const downloadUrl = optionalString(payload, 'download_url')
  return {
    job_id: requiredString(payload, 'job_id', '导出任务状态响应'),
    status: parseTaskStatus(payload.status, '导出任务状态响应'),
    progress: typeof progress === 'number' ? progress : 0,
    error_code: optionalString(payload, 'error_code'),
    error_message: optionalString(payload, 'error_message'),
    download_url: downloadUrl,
    expires_at: optionalString(payload, 'expires_at'),
  }
}

export async function getExportJob(jobId: string): Promise<ExportJob> {
  const payload = await apiClient.get<unknown>(`/exports/${encodeURIComponent(jobId)}`)
  return parseExportJob(payload)
}

export function normalizeDownloadUrl(value: string | null): string | null {
  if (!value) {
    return null
  }
  if (value.startsWith('/api/')) {
    return value
  }
  try {
    const parsed = new URL(value, window.location.origin)
    return ['http:', 'https:'].includes(parsed.protocol) ? parsed.toString() : null
  } catch {
    return null
  }
}

export function parseDeletionReceipt(payload: unknown): DeletionReceipt {
  if (payload === null || payload === undefined) {
    return { job_id: null, status: 'completed' }
  }
  if (!isRecord(payload)) {
    throw new ContractError('删除词书响应不是对象。')
  }
  const rawStatus = String(payload.status ?? 'deleting')
  if (['completed', 'deleted', 'succeeded'].includes(rawStatus)) {
    return { job_id: optionalString(payload, 'job_id'), status: 'completed' }
  }
  if (['queued', 'running', 'deleting'].includes(rawStatus)) {
    return { job_id: optionalString(payload, 'job_id'), status: 'deleting' }
  }
  throw new ContractError('删除词书响应的 status 不正确。')
}

export async function deleteWordbook(
  wordbook: Wordbook,
  confirmationName: string,
  idempotencyKey?: string,
): Promise<DeletionReceipt> {
  const payload = await apiClient.request<unknown>(
    `/wordbooks/${encodeURIComponent(wordbook.id)}`,
    {
      method: 'DELETE',
      body: {
        confirmation_name: wordbook.visibility === 'organization' ? confirmationName.trim() : undefined,
      },
      retryCount: 0,
      headers: idempotencyHeaders(idempotencyKey),
    },
  )
  return parseDeletionReceipt(payload)
}

export function validateWordbookFile(file: File, maxBytes = 10 * 1024 * 1024): string | null {
  const extension = file.name.split('.').pop()?.toLowerCase()
  if (!extension || !['csv', 'json', 'txt'].includes(extension)) {
    return '仅支持 .csv、.json、.txt 文件。'
  }
  if (file.size > maxBytes) {
    return '文件不能超过 10 MiB；最终大小限制以服务端校验为准。'
  }
  return null
}

export function canActivateWordbook(wordbook: Wordbook): boolean {
  return wordbook.status === 'ready' && !wordbook.is_active && wordbook.permissions.can_activate
}