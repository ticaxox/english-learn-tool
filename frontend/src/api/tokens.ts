/** Personal access tokens used by external MCP clients. */
import { apiClient } from './client'
import { ContractError } from './errors'

export interface PersonalToken {
  id: string
  name: string
  prefix: string
  isDefault: boolean
  createdAt: string
  lastUsedAt: string | null
  revokedAt: string | null
}

export interface PersonalTokenCreated extends PersonalToken {
  token: string
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null
}

function parseToken(value: unknown): PersonalToken {
  if (!isRecord(value)) throw new ContractError('访问令牌不是对象。')
  const text = (key: string): string => {
    const field = value[key]
    if (typeof field !== 'string') throw new ContractError(`访问令牌缺少 ${key}。`)
    return field
  }
  const optional = (key: string): string | null => {
    const field = value[key]
    return typeof field === 'string' ? field : null
  }
  return {
    id: text('id'),
    name: text('name'),
    prefix: text('prefix'),
    isDefault: value.is_default === true,
    createdAt: text('created_at'),
    lastUsedAt: optional('last_used_at'),
    revokedAt: optional('revoked_at'),
  }
}

export async function listPersonalTokens(): Promise<PersonalToken[]> {
  const payload = await apiClient.get('/me/tokens')
  if (!isRecord(payload) || !Array.isArray(payload.items)) {
    throw new ContractError('访问令牌列表缺少 items。')
  }
  return payload.items.map(parseToken)
}

export async function createPersonalToken(name: string): Promise<PersonalTokenCreated> {
  const payload = await apiClient.post('/me/tokens', { name })
  const parsed = parseToken(payload)
  if (!isRecord(payload) || typeof payload.token !== 'string') {
    throw new ContractError('新建访问令牌缺少 token。')
  }
  return { ...parsed, token: payload.token }
}

export async function revokePersonalToken(id: string): Promise<void> {
  await apiClient.delete(`/me/tokens/${encodeURIComponent(id)}`)
}

export async function refreshPersonalToken(id: string): Promise<PersonalTokenCreated> {
  const payload = await apiClient.post(`/me/tokens/${encodeURIComponent(id)}/refresh`)
  const parsed = parseToken(payload)
  if (!isRecord(payload) || typeof payload.token !== 'string') {
    throw new ContractError('刷新访问令牌缺少 token。')
  }
  return { ...parsed, token: payload.token }
}
