import { apiClient } from './client'
import { ContractError } from './errors'

export type WordbookVisibility = 'organization' | 'private'
export type WordbookStatus = 'importing' | 'ready' | 'failed' | 'deleting' | 'deleted'
export type WordbookField =
  | 'headword'
  | 'phonetic'
  | 'part_of_speech'
  | 'definition_en'
  | 'definition_zh'
  | 'example'
  | 'example_translation'
export type ExportFormat = 'csv' | 'txt' | 'pdf'
export type JobStatus = 'queued' | 'running' | 'succeeded' | 'failed' | 'cancelled'
export type JobKind = 'import' | 'export' | 'delete'
export type CleanupStatus = 'pending' | 'completed' | 'failed'
export type ImportPreviewStatus = 'previewed' | 'queued' | 'processing' | 'completed' | 'failed' | 'expired'
export type WordbookSort = 'created_at' | 'updated_at' | 'name'
export type SortDirection = 'asc' | 'desc'

export interface Wordbook {
  id: string
  visibility: WordbookVisibility
  status: WordbookStatus
  name: string
  version: string
  entry_count: number
  is_active: boolean
  is_builtin?: boolean
  created_at: string
  updated_at: string
  description: string | null
  owner_id: string | null
  created_by: string | null
}

export interface WordbookListQuery {
  offset?: number
  limit?: number
  sort?: WordbookSort
  direction?: SortDirection
}

export interface WordbookListPage {
  items: Wordbook[]
  total: number
  offset: number
  limit: number
}

export interface WordbookEntryExample {
  example_en: string
  example_zh: string | null
}

export interface WordbookEntryDefinition {
  part_of_speech: string | null
  definition_en: string | null
  definition_zh: string | null
  examples: WordbookEntryExample[]
}

export interface WordbookEntry {
  id: string
  headword: string
  normalized_headword: string
  phonetic: string | null
  definitions: WordbookEntryDefinition[]
}

export interface WordbookDetail {
  wordbook: Wordbook
  entries: WordbookEntry[]
  total_entries: number
  offset: number
  limit: number
}

export interface ImportPreviewIssue {
  line_number: number | null
  code: string | null
  message: string
}

export interface ImportPreviewDefinition {
  part_of_speech: string | null
  definition_en: string | null
  definition_zh: string | null
  example_en: string | null
  example_translation: string | null
}

export interface ImportPreviewSampleRow {
  line_number: number | null
  headword: string
  normalized_headword: string | null
  phonetic: string | null
  definitions: ImportPreviewDefinition[]
}

export interface WordbookImportPreview {
  preview_id: string
  preview_token: string
  preview_hash: string
  filename: string
  detected_format: 'csv' | 'json' | 'txt'
  encoding: string
  delimiter: string | null
  columns: string[]
  suggested_mapping: Partial<Record<WordbookField, string | null>>
  mapping: Partial<Record<WordbookField, string | null>>
  ignored_columns: string[]
  sample_rows: ImportPreviewSampleRow[]
  total_rows: number
  valid_rows: number
  warning_count: number
  error_count: number
  warnings: ImportPreviewIssue[]
  errors: ImportPreviewIssue[]
  expires_at: string
  status: ImportPreviewStatus
  requested_name: string
  requested_description: string | null
  requested_visibility: WordbookVisibility
}

export interface WordbookImportInput {
  visibility: WordbookVisibility
  name: string
  description: string
}

export interface WordbookPreviewRemapInput {
  preview_token: string
  mapping: Partial<Record<WordbookField, string | null>>
  ignored_columns?: string[]
}

export interface WordbookImportConfirmInput {
  preview_id: string
  preview_token: string
  preview_hash: string
  visibility?: WordbookVisibility
  name?: string
  description?: string | null
}

export interface ActivationResult {
  wordbook_id: string
  is_active: true
  activated_at: string
}

export interface ExportOptions {
  format: ExportFormat
  page_rows?: number
  columns?: number
}

export interface WordbookJob {
  job_id: string
  kind: JobKind
  status: JobStatus
  progress: number
  wordbook_id: string | null
  error_code: string | null
  error_message: string | null
  result: Record<string, unknown>
  download_url: string | null
  download_expires_at: string | null
  cleanup_status: CleanupStatus
  created_at: string
  started_at: string | null
  finished_at: string | null
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

function requiredRecord(value: unknown, context: string): Record<string, unknown> {
  if (!isRecord(value)) {
    throw new ContractError(`${context}不是对象。`)
  }
  return value
}

function requiredString(record: Record<string, unknown>, key: string, context: string): string {
  const value = record[key]
  if (typeof value !== 'string' || !value.trim()) {
    throw new ContractError(`${context}缺少合法的 ${key}。`)
  }
  return value
}

function stringAllowEmpty(record: Record<string, unknown>, key: string, context: string): string {
  const value = record[key]
  if (typeof value !== 'string') {
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

function requiredInteger(
  record: Record<string, unknown>,
  key: string,
  context: string,
  minimum = 0,
  maximum = Number.MAX_SAFE_INTEGER,
): number {
  const value = record[key]
  if (typeof value !== 'number' || !Number.isInteger(value) || value < minimum || value > maximum) {
    throw new ContractError(`${context}缺少合法的 ${key}。`)
  }
  return value
}

function optionalInteger(record: Record<string, unknown>, key: string): number | null {
  const value = record[key]
  if (value === null || value === undefined) {
    return null
  }
  if (typeof value !== 'number' || !Number.isInteger(value)) {
    throw new ContractError(`响应中的 ${key} 必须是整数或 null。`)
  }
  return value
}

function requiredEnum<T extends string>(
  record: Record<string, unknown>,
  key: string,
  allowed: readonly T[],
  context: string,
): T {
  const value = record[key]
  if (typeof value !== 'string' || !allowed.includes(value as T)) {
    throw new ContractError(`${context}的 ${key} 不在 OpenAPI 枚举内。`)
  }
  return value as T
}

function stringArray(record: Record<string, unknown>, key: string): string[] {
  const value = record[key]
  if (!Array.isArray(value) || !value.every((item) => typeof item === 'string')) {
    throw new ContractError(`响应中的 ${key} 必须是字符串数组。`)
  }
  return value as string[]
}

const WORDBOOK_FIELDS: WordbookField[] = [
  'headword',
  'phonetic',
  'part_of_speech',
  'definition_en',
  'definition_zh',
  'example',
  'example_translation',
]

function parseMapping(value: unknown): Partial<Record<WordbookField, string | null>> {
  if (!isRecord(value)) {
    throw new ContractError('导入预览中的 mapping 必须是对象。')
  }
  const mapping: Partial<Record<WordbookField, string | null>> = {}
  for (const field of WORDBOOK_FIELDS) {
    const source = value[field]
    if (source === undefined || source === null) {
      mapping[field] = null
    } else if (typeof source === 'string') {
      mapping[field] = source
    } else {
      throw new ContractError(`导入预览 mapping.${field} 必须是字符串或 null。`)
    }
  }
  return mapping
}

function parsePreviewIssue(value: unknown, index: number): ImportPreviewIssue {
  const item = requiredRecord(value, `预览问题第 ${index + 1} 项`)
  return {
    line_number: optionalInteger(item, 'line_number'),
    code: optionalString(item, 'code'),
    message: requiredString(item, 'message', `预览问题第 ${index + 1} 项`),
  }
}

function parsePreviewIssueArray(record: Record<string, unknown>, key: string): ImportPreviewIssue[] {
  const value = record[key]
  if (!Array.isArray(value)) {
    throw new ContractError(`导入预览中的 ${key} 必须是数组。`)
  }
  return value.map(parsePreviewIssue)
}

function parsePreviewDefinition(value: unknown, index: number): ImportPreviewDefinition {
  const item = requiredRecord(value, `预览样例释义第 ${index + 1} 项`)
  return {
    part_of_speech: optionalString(item, 'part_of_speech'),
    definition_en: optionalString(item, 'definition_en'),
    definition_zh: optionalString(item, 'definition_zh'),
    example_en: optionalString(item, 'example_en'),
    example_translation: optionalString(item, 'example_translation'),
  }
}

function parsePreviewSampleRow(value: unknown, index: number): ImportPreviewSampleRow {
  const row = requiredRecord(value, `预览样例第 ${index + 1} 行`)
  const definitions = row.definitions === undefined ? [] : row.definitions
  if (!Array.isArray(definitions)) {
    throw new ContractError(`预览样例第 ${index + 1} 行缺少 definitions 数组。`)
  }
  return {
    line_number: optionalInteger(row, 'line_number'),
    headword: requiredString(row, 'headword', `预览样例第 ${index + 1} 行`),
    normalized_headword: optionalString(row, 'normalized_headword'),
    phonetic: optionalString(row, 'phonetic'),
    definitions: definitions.map(parsePreviewDefinition),
  }
}

export function parseWordbook(payload: unknown, context = '词书响应'): Wordbook {
  const record = requiredRecord(payload, context)
  return {
    id: requiredString(record, 'id', context),
    visibility: requiredEnum(record, 'visibility', ['organization', 'private'] as const, context),
    status: requiredEnum(record, 'status', ['importing', 'ready', 'failed', 'deleting', 'deleted'] as const, context),
    name: requiredString(record, 'name', context),
    version: requiredString(record, 'version', context),
    entry_count: requiredInteger(record, 'entry_count', context),
    is_active: requiredBoolean(record, 'is_active', context),
    is_builtin:
      typeof record.is_builtin === 'boolean'
        ? record.is_builtin
        : record.visibility === 'organization',
    created_at: requiredString(record, 'created_at', context),
    updated_at: requiredString(record, 'updated_at', context),
    description: optionalString(record, 'description'),
    owner_id: optionalString(record, 'owner_id'),
    created_by: optionalString(record, 'created_by'),
  }
}

export function buildWordbookListQuery(query: WordbookListQuery = {}): string {
  const offset = query.offset ?? 0
  const limit = query.limit ?? 20
  if (!Number.isInteger(offset) || offset < 0) {
    throw new ContractError('词书列表 offset 必须是非负整数。')
  }
  if (!Number.isInteger(limit) || limit < 1 || limit > 100) {
    throw new ContractError('词书列表 limit 必须是 1 到 100 之间的整数。')
  }
  const params = new URLSearchParams({ offset: String(offset), limit: String(limit) })
  if (query.sort) {
    params.set('sort', query.sort)
  }
  if (query.direction) {
    params.set('direction', query.direction)
  }
  return `?${params.toString()}`
}

export function parseWordbookList(payload: unknown): WordbookListPage {
  const record = requiredRecord(payload, '词书列表响应')
  if (!Array.isArray(record.items)) {
    throw new ContractError('词书列表响应中的 items 必须是数组。')
  }
  return {
    items: record.items.map((item) => parseWordbook(item, '词书列表项')),
    total: requiredInteger(record, 'total', '词书列表响应'),
    offset: requiredInteger(record, 'offset', '词书列表响应'),
    limit: requiredInteger(record, 'limit', '词书列表响应', 1, 100),
  }
}

function parseEntryExample(value: unknown, index: number): WordbookEntryExample {
  const item = requiredRecord(value, `词条例句第 ${index + 1} 项`)
  return {
    example_en: requiredString(item, 'example_en', `词条例句第 ${index + 1} 项`),
    example_zh: optionalString(item, 'example_zh'),
  }
}

function parseEntryDefinition(value: unknown, index: number): WordbookEntryDefinition {
  const item = requiredRecord(value, `词条释义第 ${index + 1} 项`)
  const examples = item.examples === undefined ? [] : item.examples
  if (!Array.isArray(examples)) {
    throw new ContractError(`词条释义第 ${index + 1} 项的 examples 必须是数组。`)
  }
  return {
    part_of_speech: optionalString(item, 'part_of_speech'),
    definition_en: optionalString(item, 'definition_en'),
    definition_zh: optionalString(item, 'definition_zh'),
    examples: examples.map(parseEntryExample),
  }
}

function parseWordbookEntry(value: unknown, index: number): WordbookEntry {
  const item = requiredRecord(value, `词条第 ${index + 1} 项`)
  const definitions = item.definitions === undefined ? [] : item.definitions
  if (!Array.isArray(definitions)) {
    throw new ContractError(`词条第 ${index + 1} 项的 definitions 必须是数组。`)
  }
  return {
    id: requiredString(item, 'id', `词条第 ${index + 1} 项`),
    headword: requiredString(item, 'headword', `词条第 ${index + 1} 项`),
    normalized_headword: requiredString(item, 'normalized_headword', `词条第 ${index + 1} 项`),
    phonetic: optionalString(item, 'phonetic'),
    definitions: definitions.map(parseEntryDefinition),
  }
}

export function parseWordbookDetail(payload: unknown): WordbookDetail {
  const record = requiredRecord(payload, '词书详情响应')
  if (!Array.isArray(record.entries)) {
    throw new ContractError('词书详情响应中的 entries 必须是数组。')
  }
  return {
    wordbook: parseWordbook(record.wordbook, '词书详情中的词书'),
    entries: record.entries.map(parseWordbookEntry),
    total_entries: requiredInteger(record, 'total_entries', '词书详情响应'),
    offset: requiredInteger(record, 'offset', '词书详情响应'),
    limit: requiredInteger(record, 'limit', '词书详情响应', 1, 100),
  }
}

export function parseWordbookImportPreview(payload: unknown): WordbookImportPreview {
  const record = requiredRecord(payload, '导入预览响应')
  if (!Array.isArray(record.sample_rows)) {
    throw new ContractError('导入预览响应中的 sample_rows 必须是数组。')
  }
  return {
    preview_id: requiredString(record, 'preview_id', '导入预览响应'),
    preview_token: stringAllowEmpty(record, 'preview_token', '导入预览响应'),
    preview_hash: requiredString(record, 'preview_hash', '导入预览响应'),
    filename: requiredString(record, 'filename', '导入预览响应'),
    detected_format: requiredEnum(record, 'detected_format', ['csv', 'json', 'txt'] as const, '导入预览响应'),
    encoding: requiredString(record, 'encoding', '导入预览响应'),
    delimiter: optionalString(record, 'delimiter'),
    columns: stringArray(record, 'columns'),
    suggested_mapping: parseMapping(record.suggested_mapping),
    mapping: parseMapping(record.mapping),
    ignored_columns: stringArray(record, 'ignored_columns'),
    sample_rows: record.sample_rows.map(parsePreviewSampleRow),
    total_rows: requiredInteger(record, 'total_rows', '导入预览响应'),
    valid_rows: requiredInteger(record, 'valid_rows', '导入预览响应'),
    warning_count: requiredInteger(record, 'warning_count', '导入预览响应'),
    error_count: requiredInteger(record, 'error_count', '导入预览响应'),
    warnings: parsePreviewIssueArray(record, 'warnings'),
    errors: parsePreviewIssueArray(record, 'errors'),
    expires_at: requiredString(record, 'expires_at', '导入预览响应'),
    status: requiredEnum(record, 'status', ['previewed', 'queued', 'processing', 'completed', 'failed', 'expired'] as const, '导入预览响应'),
    requested_name: requiredString(record, 'requested_name', '导入预览响应'),
    requested_description: optionalString(record, 'requested_description'),
    requested_visibility: requiredEnum(record, 'requested_visibility', ['organization', 'private'] as const, '导入预览响应'),
  }
}

export async function listWordbooks(query: WordbookListQuery = {}): Promise<WordbookListPage> {
  const payload = await apiClient.get<unknown>(`/wordbooks${buildWordbookListQuery(query)}`)
  return parseWordbookList(payload)
}

export async function getWordbookDetail(wordbookId: string, offset = 0, limit = 50): Promise<WordbookDetail> {
  if (!Number.isInteger(offset) || offset < 0) {
    throw new ContractError('词书详情 offset 必须是非负整数。')
  }
  if (!Number.isInteger(limit) || limit < 1 || limit > 100) {
    throw new ContractError('词书详情 limit 必须是 1 到 100 之间的整数。')
  }
  const params = new URLSearchParams({ offset: String(offset), limit: String(limit) })
  const payload = await apiClient.get<unknown>(`/wordbooks/${encodeURIComponent(wordbookId)}?${params}`)
  return parseWordbookDetail(payload)
}

export async function previewWordbookImport(file: File, input: WordbookImportInput): Promise<WordbookImportPreview> {
  const form = new FormData()
  form.set('file', file)
  form.set('visibility', input.visibility)
  form.set('name', input.name.trim())
  if (input.description.trim()) {
    form.set('description', input.description.trim())
  }
  const payload = await apiClient.post<unknown>('/wordbooks/import/preview', form, { retryCount: 0 })
  return parseWordbookImportPreview(payload)
}

export async function remapWordbookPreview(
  previewId: string,
  input: WordbookPreviewRemapInput,
): Promise<WordbookImportPreview> {
  if (!input.preview_token.trim()) {
    throw new ContractError('修改字段映射前缺少有效预览令牌，请重新上传预览。')
  }
  const payload = await apiClient.patch<unknown>(
    `/wordbooks/import/previews/${encodeURIComponent(previewId)}`,
    {
      preview_token: input.preview_token,
      mapping: input.mapping,
      ...(input.ignored_columns === undefined ? {} : { ignored_columns: input.ignored_columns }),
    },
    { retryCount: 0 },
  )
  const parsed = parseWordbookImportPreview(payload)
  return {
    ...parsed,
    preview_token: parsed.preview_token || input.preview_token,
  }
}

function idempotencyHeaders(key: string): HeadersInit {
  return { 'Idempotency-Key': key }
}

export async function confirmWordbookImport(
  input: WordbookImportConfirmInput,
  idempotencyKey: string,
): Promise<WordbookJob> {
  const body: Record<string, unknown> = {
    preview_id: input.preview_id,
    preview_token: input.preview_token,
    preview_hash: input.preview_hash,
  }
  if (input.visibility !== undefined) {
    body.visibility = input.visibility
  }
  if (input.name !== undefined) {
    body.name = input.name
  }
  if (input.description !== undefined) {
    body.description = input.description
  }
  const payload = await apiClient.post<unknown>('/wordbooks/import', body, {
    retryCount: 0,
    headers: idempotencyHeaders(idempotencyKey),
  })
  return parseWordbookJob(payload)
}

export function parseWordbookJob(payload: unknown): WordbookJob {
  const record = requiredRecord(payload, '词书任务响应')
  const result = record.result
  if (result !== undefined && result !== null && !isRecord(result)) {
    throw new ContractError('词书任务响应中的 result 必须是对象。')
  }
  return {
    job_id: requiredString(record, 'job_id', '词书任务响应'),
    kind: requiredEnum(record, 'kind', ['import', 'export', 'delete'] as const, '词书任务响应'),
    status: requiredEnum(record, 'status', ['queued', 'running', 'succeeded', 'failed', 'cancelled'] as const, '词书任务响应'),
    progress: requiredInteger(record, 'progress', '词书任务响应', 0, 100),
    wordbook_id: optionalString(record, 'wordbook_id'),
    error_code: optionalString(record, 'error_code'),
    error_message: optionalString(record, 'error_message'),
    result: isRecord(result) ? result : {},
    download_url: optionalString(record, 'download_url'),
    download_expires_at: optionalString(record, 'download_expires_at'),
    cleanup_status: requiredEnum(record, 'cleanup_status', ['pending', 'completed', 'failed'] as const, '词书任务响应'),
    created_at: requiredString(record, 'created_at', '词书任务响应'),
    started_at: optionalString(record, 'started_at'),
    finished_at: optionalString(record, 'finished_at'),
  }
}

export async function getWordbookJob(jobId: string): Promise<WordbookJob> {
  const payload = await apiClient.get<unknown>(`/wordbooks/jobs/${encodeURIComponent(jobId)}`)
  return parseWordbookJob(payload)
}

export async function updateWordbook(
  wordbookId: string,
  patch: { name?: string; description?: string | null; is_builtin?: boolean },
): Promise<Wordbook> {
  const payload = await apiClient.patch(
    `/wordbooks/${encodeURIComponent(wordbookId)}`,
    patch,
  )
  return parseWordbook(payload)
}

export async function activateWordbook(wordbookId: string): Promise<ActivationResult> {
  const payload = await apiClient.post<unknown>(`/wordbooks/${encodeURIComponent(wordbookId)}/activate`, undefined, {
    retryCount: 0,
  })
  const record = requiredRecord(payload, '激活词书响应')
  const isActive = record.is_active
  if (isActive !== undefined && isActive !== true) {
    throw new ContractError('激活词书响应中的 is_active 必须为 true。')
  }
  return {
    wordbook_id: requiredString(record, 'wordbook_id', '激活词书响应'),
    is_active: true,
    activated_at: requiredString(record, 'activated_at', '激活词书响应'),
  }
}

export async function createWordbookExport(
  wordbookId: string,
  options: ExportOptions,
  idempotencyKey: string,
): Promise<WordbookJob> {
  const payload = await apiClient.post<unknown>(
    `/wordbooks/${encodeURIComponent(wordbookId)}/export`,
    options,
    { retryCount: 0, headers: idempotencyHeaders(idempotencyKey) },
  )
  return parseWordbookJob(payload)
}

export async function getExportJob(jobId: string): Promise<WordbookJob> {
  const payload = await apiClient.get<unknown>(`/exports/${encodeURIComponent(jobId)}`)
  return parseWordbookJob(payload)
}

export async function downloadWordbookExport(jobId: string): Promise<Blob> {
  return apiClient.get<Blob>(`/exports/${encodeURIComponent(jobId)}/download`, {
    retryCount: 0,
    responseType: 'blob',
  })
}

export function normalizeDownloadUrl(value: string | null): string | null {
  if (!value) {
    return null
  }
  try {
    const origin = globalThis.location?.origin ?? 'http://localhost'
    const parsed = new URL(value, origin)
    if (parsed.origin !== origin || !parsed.pathname.startsWith('/api/v1/')) {
      return null
    }
    return `${parsed.pathname}${parsed.search}`
  } catch {
    return null
  }
}

export async function deleteWordbook(
  wordbook: Wordbook,
  confirmationName: string,
  idempotencyKey: string,
): Promise<WordbookJob> {
  const payload = await apiClient.request<unknown>(
    `/wordbooks/${encodeURIComponent(wordbook.id)}`,
    {
      method: 'DELETE',
      body: {
        confirm_name: wordbook.visibility === 'organization' ? confirmationName.trim() : null,
      },
      retryCount: 0,
      headers: idempotencyHeaders(idempotencyKey),
    },
  )
  return parseWordbookJob(payload)
}

export function validateWordbookFile(file: File, maxBytes = 10 * 1024 * 1024): string | null {
  const extension = file.name.split('.').pop()?.toLowerCase()
  if (!extension || !['csv', 'json', 'txt'].includes(extension)) {
    return '仅支持 .csv、.json、.txt 文件。'
  }
  if (file.size > maxBytes) {
    return '文件不能超过 10 MiB。'
  }
  return null
}

export function validateRequiredMapping(mapping: Partial<Record<WordbookField, string | null>>): string | null {
  const missing: string[] = []
  if (!mapping.headword) {
    missing.push('headword（单词）')
  }
  if (!mapping.definition_en) {
    missing.push('definition_en（英文释义）')
  }
  if (!mapping.definition_zh) {
    missing.push('definition_zh（中文释义）')
  }
  if (missing.length) {
    return `请映射必填字段：${missing.join('、')}。`
  }

  const used = Object.values(mapping).filter((value): value is string => Boolean(value))
  const duplicate = used.find((value, index) => used.indexOf(value) !== index)
  if (duplicate) {
    return `源列「${duplicate}」不能同时映射到多个字段。`
  }
  return null
}

export function isPreviewExpired(expiresAt: string, now = Date.now()): boolean {
  const expiry = Date.parse(expiresAt)
  return Number.isNaN(expiry) ? true : expiry <= now
}

export function canActivateWordbook(wordbook: Wordbook): boolean {
  return wordbook.status === 'ready' && !wordbook.is_active
}

export function canManageWordbook(wordbook: Wordbook, userId: string | null, isAdmin: boolean): boolean {
  if (wordbook.visibility === 'organization') {
    return isAdmin
  }
  return Boolean(userId && wordbook.owner_id === userId)
}

export function canExportWordbook(wordbook: Wordbook, userId: string | null, isAdmin: boolean): boolean {
  return wordbook.status === 'ready' && canManageWordbook(wordbook, userId, isAdmin)
}

export function canDeleteWordbook(wordbook: Wordbook, userId: string | null, isAdmin: boolean): boolean {
  return (
    (wordbook.status === 'ready' || wordbook.status === 'failed')
    && canManageWordbook(wordbook, userId, isAdmin)
  )
}
