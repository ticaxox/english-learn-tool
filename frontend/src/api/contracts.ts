import { ContractError } from './errors'

export type UserRole = 'admin' | 'member'

export interface AuthTokenResponse {
  access_token: string
  csrf_token?: string
  token_type?: string
  expires_in?: number
}

export interface CurrentUser {
  id: string
  username: string
  display_name: string
  role: UserRole
  must_change_password: boolean
  status?: string
  department?: string | null
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

export function parseAuthTokenResponse(payload: unknown): AuthTokenResponse {
  if (!isRecord(payload) || typeof payload.access_token !== 'string' || !payload.access_token.trim()) {
    throw new ContractError('认证接口未返回 access_token。请核对 OpenAPI 与后端认证响应。')
  }

  const csrfToken = payload.csrf_token
  if (csrfToken !== undefined && typeof csrfToken !== 'string') {
    throw new ContractError('认证接口返回的 csrf_token 类型不正确。')
  }

  return {
    access_token: payload.access_token,
    csrf_token: csrfToken,
    token_type: typeof payload.token_type === 'string' ? payload.token_type : undefined,
    expires_in: typeof payload.expires_in === 'number' ? payload.expires_in : undefined,
  }
}

export function parseCurrentUser(payload: unknown): CurrentUser {
  if (!isRecord(payload)) {
    throw new ContractError('当前用户接口未返回对象。')
  }

  const { id, username, display_name: displayName, role, must_change_password: mustChangePassword } = payload

  if (typeof id !== 'string' || !id) {
    throw new ContractError('当前用户响应缺少合法的 id。')
  }
  if (typeof username !== 'string' || !username) {
    throw new ContractError('当前用户响应缺少合法的 username。')
  }
  if (typeof displayName !== 'string' || !displayName) {
    throw new ContractError('当前用户响应缺少合法的 display_name。')
  }
  if (role !== 'admin' && role !== 'member') {
    throw new ContractError('当前用户响应的 role 必须是 admin 或 member。')
  }
  if (typeof mustChangePassword !== 'boolean') {
    throw new ContractError('当前用户响应缺少 must_change_password。')
  }

  return {
    id,
    username,
    display_name: displayName,
    role,
    must_change_password: mustChangePassword,
    status: typeof payload.status === 'string' ? payload.status : undefined,
    department: typeof payload.department === 'string' || payload.department === null ? payload.department : undefined,
  }
}