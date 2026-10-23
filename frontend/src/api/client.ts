import { ApiError, ContractError, isApiError } from './errors'
import { parseValidationIssues } from './validation-errors'

export type HttpMethod = 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE'

export interface RequestOptions {
  method?: HttpMethod
  body?: unknown
  headers?: HeadersInit
  signal?: AbortSignal
  retryCount?: number
  skipAuthRefresh?: boolean
  responseType?: 'json' | 'text' | 'blob'
}

const JSON_CONTENT_TYPE = 'application/json'

function delay(milliseconds: number): Promise<void> {
  return new Promise((resolve) => window.setTimeout(resolve, milliseconds))
}

function isAbortError(error: unknown): boolean {
  return error instanceof DOMException && error.name === 'AbortError'
}

function parseJsonSafely(text: string): unknown {
  if (!text) {
    return null
  }

  try {
    return JSON.parse(text) as unknown
  } catch {
    return null
  }
}

function readCookie(name: string): string | null {
  if (typeof document === 'undefined') {
    return null
  }

  const prefix = `${name}=`
  for (const part of document.cookie.split(';')) {
    const candidate = part.trim()
    if (candidate.startsWith(prefix)) {
      const value = candidate.slice(prefix.length)
      try {
        return decodeURIComponent(value)
      } catch {
        return value
      }
    }
  }
  return null
}

function getStringField(value: unknown, key: string): string | null {
  if (typeof value !== 'object' || value === null || !(key in value)) {
    return null
  }
  const candidate = (value as Record<string, unknown>)[key]
  return typeof candidate === 'string' ? candidate : null
}

export class ApiClient {
  private readonly baseUrl: string
  private accessToken: string | null = null
  private csrfToken: string | null = null
  private lastRequestId: string | null = null
  private refreshHandler: (() => Promise<void>) | null = null
  private sessionExpiredHandler: (() => void) | null = null
  private refreshInFlight: Promise<void> | null = null

  constructor(baseUrl: string) {
    this.baseUrl = baseUrl.replace(/\/+$/, '')
  }

  getBaseUrl(): string {
    return this.baseUrl
  }

  getAccessToken(): string | null {
    return this.accessToken
  }

  getLastRequestId(): string | null {
    return this.lastRequestId
  }

  setAccessToken(token: string | null): void {
    this.accessToken = token
  }

  setCsrfToken(token: string | null): void {
    this.csrfToken = token
  }

  setRefreshHandler(handler: (() => Promise<void>) | null): void {
    this.refreshHandler = handler
  }

  setSessionExpiredHandler(handler: (() => void) | null): void {
    this.sessionExpiredHandler = handler
  }

  clearCredentials(): void {
    this.accessToken = null
    this.csrfToken = null
    this.lastRequestId = null
  }

  async get<T>(path: string, options: Omit<RequestOptions, 'method' | 'body'> = {}): Promise<T> {
    return this.request<T>(path, { ...options, method: 'GET' })
  }

  async post<T>(path: string, body?: unknown, options: Omit<RequestOptions, 'method' | 'body'> = {}): Promise<T> {
    return this.request<T>(path, { ...options, method: 'POST', body })
  }

  async put<T>(path: string, body?: unknown, options: Omit<RequestOptions, 'method' | 'body'> = {}): Promise<T> {
    return this.request<T>(path, { ...options, method: 'PUT', body })
  }

  async patch<T>(path: string, body?: unknown, options: Omit<RequestOptions, 'method' | 'body'> = {}): Promise<T> {
    return this.request<T>(path, { ...options, method: 'PATCH', body })
  }

  async delete<T>(path: string, options: Omit<RequestOptions, 'method' | 'body'> = {}): Promise<T> {
    return this.request<T>(path, { ...options, method: 'DELETE' })
  }

  async request<T>(path: string, options: RequestOptions = {}): Promise<T> {
    const method = options.method ?? 'GET'
    const url = this.buildUrl(path)
    const retryCount = options.retryCount ?? (method === 'GET' ? 1 : 0)
    const requestHeaders = new Headers(options.headers)

    requestHeaders.set('Accept', options.responseType === 'blob' ? 'application/octet-stream' : JSON_CONTENT_TYPE)

    if (this.accessToken) {
      requestHeaders.set('Authorization', `Bearer ${this.accessToken}`)
    }

    const csrfToken = this.csrfToken ?? readCookie('csrf_token')
    if (csrfToken && method !== 'GET') {
      requestHeaders.set('X-CSRF-Token', csrfToken)
    }

    let requestBody: BodyInit | undefined
    if (options.body !== undefined) {
      if (
        options.body instanceof FormData ||
        options.body instanceof Blob ||
        options.body instanceof URLSearchParams ||
        typeof options.body === 'string'
      ) {
        requestBody = options.body
      } else {
        requestHeaders.set('Content-Type', JSON_CONTENT_TYPE)
        requestBody = JSON.stringify(options.body)
      }
    }

    const response = await this.fetchWithNetworkRetries(
      url,
      {
        method,
        headers: requestHeaders,
        credentials: 'include',
        body: requestBody,
        signal: options.signal,
      },
      retryCount,
    )

    this.captureCsrfToken(response)
    this.lastRequestId = response.headers.get('x-request-id')

    if (!response.ok) {
      const apiError = await this.createApiError(response, this.lastRequestId)

      if (apiError.status === 401 && !options.skipAuthRefresh && this.accessToken && this.refreshHandler) {
        try {
          await this.refreshAccessTokenOnce()
        } catch (refreshError) {
          if (isApiError(refreshError) && refreshError.status === 401) {
            this.sessionExpiredHandler?.()
            throw apiError
          }
          throw refreshError
        }

        return this.request<T>(path, {
          ...options,
          retryCount: 0,
          skipAuthRefresh: true,
        })
      }

      if (apiError.status === 401 && !path.endsWith('/auth/login') && !path.endsWith('/auth/refresh')) {
        this.sessionExpiredHandler?.()
      }

      throw apiError
    }

    const contentType = response.headers.get('content-type') ?? ''
    if (response.status === 204) {
      return undefined as T
    }
    if (options.responseType === 'blob') {
      return (await response.blob()) as T
    }
    if (contentType.includes(JSON_CONTENT_TYPE)) {
      return (await response.json()) as T
    }

    return (await response.text()) as T
  }

  private buildUrl(path: string): string {
    if (/^https?:\/\//i.test(path)) {
      throw new ContractError('API client 不接受绝对 URL；请只传入 /api/v1 下的相对路径。')
    }
    return `${this.baseUrl}/${path.replace(/^\/+/, '')}`
  }

  private async fetchWithNetworkRetries(url: string, init: RequestInit, retryCount: number): Promise<Response> {
    let lastError: unknown = null

    for (let attempt = 0; attempt <= retryCount; attempt += 1) {
      try {
        return await fetch(url, init)
      } catch (error) {
        if (isAbortError(error)) {
          throw error
        }
        lastError = error
        if (attempt < retryCount) {
          await delay(250 * (attempt + 1))
        }
      }
    }

    const suffix = lastError instanceof Error && lastError.message ? ` 详细原因：${lastError.message}` : ''
    throw new ApiError(
      0,
      'NETWORK_ERROR',
      `无法连接真实 API（${this.baseUrl}）。${suffix}`,
      null,
      null,
      true,
    )
  }

  private async refreshAccessTokenOnce(): Promise<void> {
    if (!this.refreshHandler) {
      throw new ContractError('尚未配置 Access Token 刷新处理器。')
    }

    if (!this.refreshInFlight) {
      this.refreshInFlight = this.refreshHandler().finally(() => {
        this.refreshInFlight = null
      })
    }

    await this.refreshInFlight
  }

  private captureCsrfToken(response: Response): void {
    const token = response.headers.get('x-csrf-token')
    if (token) {
      this.csrfToken = token
    }
  }

  private async createApiError(response: Response, headerRequestId: string | null): Promise<ApiError> {
    const text = await response.text()
    const payload = parseJsonSafely(text)
    const bodyRequestId = getStringField(payload, 'request_id')
    const requestId = headerRequestId ?? bodyRequestId
    const code = getStringField(payload, 'code') ?? `HTTP_${response.status}`
    const bodyMessage = getStringField(payload, 'message')
    const message =
      bodyMessage ??
      (response.statusText || `请求失败（HTTP ${response.status}）。`)
    const details =
      typeof payload === 'object' && payload !== null && 'details' in payload
        ? (payload as Record<string, unknown>).details
        : null
    const retryable = response.status === 429 || response.status >= 500

    // 422 uses the documented `HTTPValidationError` envelope instead of
    // `ErrorResponse`, so it carries no `code`. Keep those issues reachable for
    // the form instead of degrading the learner's only feedback to `HTTP_422`.
    const validationIssues = response.status === 422 ? parseValidationIssues(payload) : []
    if (validationIssues.length > 0) {
      return new ApiError(
        response.status,
        'VALIDATION_ERROR',
        bodyMessage ?? '提交的内容未通过服务端校验。',
        { issues: validationIssues },
        requestId,
        false,
      )
    }

    return new ApiError(response.status, code, message, details, requestId, retryable)
  }
}

export const apiClient = new ApiClient(import.meta.env.VITE_API_BASE_URL?.trim() || '/api/v1')
