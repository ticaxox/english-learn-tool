import { apiClient } from './client'
import { ContractError } from './errors'
import type { UserRole } from './contracts'

export type AdminUserRole = UserRole
export type AdminUserStatus = 'active' | 'disabled'

export interface AdminUser {
  id: string
  username: string
  display_name: string
  role: AdminUserRole
  status: AdminUserStatus
  must_change_password: boolean
  department: string | null
  learning_group: string | null
  last_login_at: string | null
  created_at: string
  updated_at: string
}

export interface AdminUserAggregates {
  active_sessions: number
  audit_events_30d: number
  learning_metrics_available: boolean
  study_minutes: number | null
  completed_tasks: number | null
  practice_submissions: number | null
  ai_usage_count: number | null
  error_rate: number | null
}

export interface AdminUserDetail {
  account: AdminUser
  aggregates: AdminUserAggregates
}

export interface AdminUserListQuery {
  search?: string
  role?: AdminUserRole | ''
  status?: AdminUserStatus | ''
  cursor?: string | null
  limit?: number
}

export interface AdminUserListPage {
  items: AdminUser[]
  next_cursor: string | null
  has_more: boolean
}

export interface CreateAdminUserInput {
  username: string
  display_name: string
  role: AdminUserRole
  department?: string | null
  learning_group?: string | null
  password?: string
}

export interface CreateAdminUserResult {
  user: AdminUser
  temporary_password: string | null
}

export interface UpdateAdminUserInput {
  display_name?: string
  role?: AdminUserRole
  status?: AdminUserStatus
  department?: string | null
  learning_group?: string | null
}

export interface ResetPasswordResult {
  user_id: string
  temporary_password: string
  must_change_password: true
}

export interface ImportPreviewRow {
  line_number: number
  username: string
  display_name: string
  department: string | null
  learning_group: string | null
  status: 'valid' | 'conflict' | 'error'
  errors: string[]
}

export interface ImportPreview {
  preview_id: string
  preview_hash: string
  expires_at: string
  total_rows: number
  valid_rows: number
  invalid_rows: number
  rows: ImportPreviewRow[]
}

export interface ImportCreatedUser {
  id: string
  username: string
  display_name: string
  temporary_password?: string | null
}

export interface ImportConfirmResult {
  import_id: string
  status: 'imported' | 'failed'
  created_count: number
  created_users: ImportCreatedUser[]
}

export interface ImportStatusResult {
  import_id: string
  status: 'previewed' | 'imported' | 'failed' | 'expired'
  created_count: number
  created_users: Array<Pick<ImportCreatedUser, 'id' | 'username' | 'display_name'>>
  expires_at: string
  used_at: string | null
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

function optionalNullableString(record: Record<string, unknown>, key: string): string | null {
  const value = record[key]
  if (value === null || value === undefined) {
    return null
  }
  if (typeof value !== 'string') {
    throw new ContractError(`成员响应中的 ${key} 必须是字符串或 null。`)
  }
  return value
}

function parseRole(value: unknown, context: string): AdminUserRole {
  if (value !== 'admin' && value !== 'member') {
    throw new ContractError(`${context}的角色必须是 admin 或 member。`)
  }
  return value
}

function parseStatus(value: unknown, context: string): AdminUserStatus {
  if (value !== 'active' && value !== 'disabled') {
    throw new ContractError(`${context}的状态必须是 active 或 disabled。`)
  }
  return value
}

function requiredInteger(record: Record<string, unknown>, key: string, context: string): number {
  const value = record[key]
  if (typeof value !== 'number' || !Number.isInteger(value) || value < 0) {
    throw new ContractError(`${context}缺少合法的 ${key}。`)
  }
  return value
}

function optionalNumber(record: Record<string, unknown>, key: string, context: string): number | null {
  const value = record[key]
  if (value === null || value === undefined) {
    return null
  }
  if (typeof value !== 'number' || !Number.isFinite(value)) {
    throw new ContractError(`${context}的 ${key} 必须是有限数字或 null。`)
  }
  return value
}

export function parseAdminUser(payload: unknown, context = '成员响应'): AdminUser {
  if (!isRecord(payload)) {
    throw new ContractError(`${context}不是对象。`)
  }
  if (typeof payload.must_change_password !== 'boolean') {
    throw new ContractError(`${context}缺少 must_change_password。`)
  }

  return {
    id: requiredString(payload, 'id', context),
    username: requiredString(payload, 'username', context),
    display_name: requiredString(payload, 'display_name', context),
    role: parseRole(payload.role, context),
    status: parseStatus(payload.status, context),
    must_change_password: payload.must_change_password,
    department: optionalNullableString(payload, 'department'),
    learning_group: optionalNullableString(payload, 'learning_group'),
    last_login_at: optionalNullableString(payload, 'last_login_at'),
    created_at: requiredString(payload, 'created_at', context),
    updated_at: requiredString(payload, 'updated_at', context),
  }
}

export function parseAdminUserList(payload: unknown): AdminUserListPage {
  if (!isRecord(payload) || !Array.isArray(payload.items)) {
    throw new ContractError('成员列表响应必须包含 items 数组。')
  }

  const items = payload.items.map((item, index) => parseAdminUser(item, `成员列表第 ${index + 1} 项`))
  if (payload.next_cursor !== null && typeof payload.next_cursor !== 'string') {
    throw new ContractError('成员列表响应的 next_cursor 必须是字符串或 null。')
  }
  if (typeof payload.has_more !== 'boolean') {
    throw new ContractError('成员列表响应缺少 has_more。')
  }

  return {
    items,
    next_cursor: payload.next_cursor,
    has_more: payload.has_more,
  }
}

export function buildAdminUserQuery(query: AdminUserListQuery): string {
  const search = new URLSearchParams()
  if (query.search?.trim()) {
    search.set('search', query.search.trim())
  }
  if (query.role) {
    search.set('role', query.role)
  }
  if (query.status) {
    search.set('status', query.status)
  }
  if (query.cursor) {
    search.set('cursor', query.cursor)
  }
  if (query.limit) {
    search.set('limit', String(query.limit))
  }
  const serialized = search.toString()
  return serialized ? `?${serialized}` : ''
}

export function parseAdminUserDetail(payload: unknown): AdminUserDetail {
  if (!isRecord(payload)) {
    throw new ContractError('成员详情响应不是对象。')
  }
  if (!isRecord(payload.aggregates)) {
    throw new ContractError('成员详情响应必须包含 aggregates 对象。')
  }
  if (typeof payload.aggregates.learning_metrics_available !== 'boolean') {
    throw new ContractError('成员详情的 aggregates 缺少 learning_metrics_available。')
  }

  return {
    account: parseAdminUser(payload.account, '成员详情中的账号'),
    aggregates: {
      active_sessions: requiredInteger(payload.aggregates, 'active_sessions', '成员详情 aggregates'),
      audit_events_30d: requiredInteger(payload.aggregates, 'audit_events_30d', '成员详情 aggregates'),
      learning_metrics_available: payload.aggregates.learning_metrics_available,
      study_minutes: optionalNumber(payload.aggregates, 'study_minutes', '成员详情 aggregates'),
      completed_tasks: optionalNumber(payload.aggregates, 'completed_tasks', '成员详情 aggregates'),
      practice_submissions: optionalNumber(
        payload.aggregates,
        'practice_submissions',
        '成员详情 aggregates',
      ),
      ai_usage_count: optionalNumber(payload.aggregates, 'ai_usage_count', '成员详情 aggregates'),
      error_rate: optionalNumber(payload.aggregates, 'error_rate', '成员详情 aggregates'),
    },
  }
}

export async function listAdminUsers(query: AdminUserListQuery = {}): Promise<AdminUserListPage> {
  const payload = await apiClient.get<unknown>(`/admin/users${buildAdminUserQuery(query)}`)
  return parseAdminUserList(payload)
}

export async function getAdminUserDetail(id: string): Promise<AdminUserDetail> {
  const payload = await apiClient.get<unknown>(`/admin/users/${encodeURIComponent(id)}`)
  return parseAdminUserDetail(payload)
}

export async function createAdminUser(input: CreateAdminUserInput): Promise<CreateAdminUserResult> {
  const payload = await apiClient.post<unknown>('/admin/users', input)
  if (!isRecord(payload)) {
    throw new ContractError('创建成员响应不是对象。')
  }
  if (typeof payload.temporary_password !== 'string' && payload.temporary_password !== null) {
    throw new ContractError('创建成员响应的 temporary_password 必须是字符串或 null。')
  }

  return {
    user: parseAdminUser(payload.user, '创建成员响应'),
    temporary_password: payload.temporary_password,
  }
}

export async function updateAdminUser(id: string, input: UpdateAdminUserInput): Promise<AdminUser> {
  const payload = await apiClient.patch<unknown>(`/admin/users/${encodeURIComponent(id)}`, input)
  return parseAdminUser(payload, '更新成员响应')
}

export async function deleteAdminUser(id: string): Promise<void> {
  await apiClient.delete<void>(`/admin/users/${encodeURIComponent(id)}`)
}

export async function resetAdminUserPassword(id: string): Promise<ResetPasswordResult> {
  const payload = await apiClient.post<unknown>(
    `/admin/users/${encodeURIComponent(id)}/reset-password`,
    undefined,
  )
  if (!isRecord(payload)) {
    throw new ContractError('重置密码响应不是对象。')
  }
  if (payload.must_change_password !== true) {
    throw new ContractError('重置密码响应必须声明 must_change_password=true。')
  }

  return {
    user_id: requiredString(payload, 'user_id', '重置密码响应'),
    temporary_password: requiredString(payload, 'temporary_password', '重置密码响应'),
    must_change_password: true,
  }
}

function parseStringList(value: unknown, context: string): string[] {
  if (!Array.isArray(value) || value.some((item) => typeof item !== 'string')) {
    throw new ContractError(`${context}必须是字符串数组。`)
  }
  return value
}

function parseIntField(record: Record<string, unknown>, key: string, context: string): number {
  const value = record[key]
  if (typeof value !== 'number' || !Number.isInteger(value) || value < 0) {
    throw new ContractError(`${context}缺少合法的 ${key}。`)
  }
  return value
}

function parseImportRow(payload: unknown, index: number): ImportPreviewRow {
  if (!isRecord(payload)) {
    throw new ContractError(`导入预览第 ${index + 1} 行不是对象。`)
  }
  if (payload.status !== 'valid' && payload.status !== 'conflict' && payload.status !== 'error') {
    throw new ContractError(`导入预览第 ${index + 1} 行的 status 不正确。`)
  }

  return {
    line_number: parseIntField(payload, 'line_number', `导入预览第 ${index + 1} 行`),
    username: optionalNullableString(payload, 'username') ?? '',
    display_name: optionalNullableString(payload, 'display_name') ?? '',
    department: optionalNullableString(payload, 'department'),
    learning_group: optionalNullableString(payload, 'learning_group'),
    status: payload.status,
    errors: parseStringList(payload.errors, `导入预览第 ${index + 1} 行 errors`),
  }
}

export function parseImportPreview(payload: unknown): ImportPreview {
  if (!isRecord(payload)) {
    throw new ContractError('导入预览响应不是对象。')
  }
  if (!Array.isArray(payload.rows)) {
    throw new ContractError('导入预览响应必须包含 rows 数组。')
  }

  return {
    preview_id: requiredString(payload, 'preview_id', '导入预览响应'),
    preview_hash: requiredString(payload, 'preview_hash', '导入预览响应'),
    expires_at: requiredString(payload, 'expires_at', '导入预览响应'),
    total_rows: parseIntField(payload, 'total_rows', '导入预览响应'),
    valid_rows: parseIntField(payload, 'valid_rows', '导入预览响应'),
    invalid_rows: parseIntField(payload, 'invalid_rows', '导入预览响应'),
    rows: payload.rows.map(parseImportRow),
  }
}

export async function previewAdminUserImport(file: File): Promise<ImportPreview> {
  const formData = new FormData()
  formData.set('file', file, file.name)
  const payload = await apiClient.post<unknown>('/admin/users/import/preview', formData, {
    retryCount: 0,
  })
  return parseImportPreview(payload)
}

function parseCreatedUsers(value: unknown, includeTemporaryPassword: boolean): ImportCreatedUser[] {
  if (!Array.isArray(value)) {
    throw new ContractError('导入响应中的 created_users 必须是数组。')
  }
  return value.map((item, index) => {
    if (!isRecord(item)) {
      throw new ContractError(`导入响应第 ${index + 1} 名成员不是对象。`)
    }
    const temp = item.temporary_password
    if (temp !== undefined && temp !== null && typeof temp !== 'string') {
      throw new ContractError('导入成员的 temporary_password 必须是字符串或 null。')
    }
    return {
      id: requiredString(item, 'id', '导入成员'),
      username: requiredString(item, 'username', '导入成员'),
      display_name: requiredString(item, 'display_name', '导入成员'),
      ...(includeTemporaryPassword ? { temporary_password: typeof temp === 'string' ? temp : null } : {}),
    }
  })
}

export function redactImportSecrets(result: ImportConfirmResult): ImportConfirmResult {
  return {
    ...result,
    created_users: result.created_users.map(({ temporary_password: _temporaryPassword, ...user }) => user),
  }
}

export function parseImportConfirmResult(payload: unknown): ImportConfirmResult {
  if (!isRecord(payload)) {
    throw new ContractError('导入确认响应不是对象。')
  }
  if (payload.status !== 'imported' && payload.status !== 'failed') {
    throw new ContractError('导入确认响应的 status 必须是 imported 或 failed。')
  }

  return {
    import_id: requiredString(payload, 'import_id', '导入确认响应'),
    status: payload.status,
    created_count: parseIntField(payload, 'created_count', '导入确认响应'),
    created_users: parseCreatedUsers(payload.created_users, true),
  }
}

export async function confirmAdminUserImport(
  previewId: string,
  previewHash: string,
): Promise<ImportConfirmResult> {
  const payload = await apiClient.post<unknown>(
    '/admin/users/import',
    { preview_id: previewId, preview_hash: previewHash },
    { retryCount: 0 },
  )
  return parseImportConfirmResult(payload)
}

export async function getAdminUserImportStatus(importId: string): Promise<ImportStatusResult> {
  const payload = await apiClient.get<unknown>(`/admin/users/import/${encodeURIComponent(importId)}`)
  if (!isRecord(payload)) {
    throw new ContractError('导入状态响应不是对象。')
  }
  if (!['previewed', 'imported', 'failed', 'expired'].includes(String(payload.status))) {
    throw new ContractError('导入状态响应的 status 不正确。')
  }

  return {
    import_id: requiredString(payload, 'import_id', '导入状态响应'),
    status: payload.status as ImportStatusResult['status'],
    created_count: parseIntField(payload, 'created_count', '导入状态响应'),
    created_users: parseCreatedUsers(payload.created_users, false),
    expires_at: requiredString(payload, 'expires_at', '导入状态响应'),
    used_at: optionalNullableString(payload, 'used_at'),
  }
}