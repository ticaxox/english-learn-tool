import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { ApiClient } from '../api/client'
import { ApiError } from '../api/errors'

describe('ApiClient', () => {
  let client: ApiClient

  beforeEach(() => {
    client = new ApiClient('/api/v1')
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('parses structured errors and exposes the request id', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        new Response(
          JSON.stringify({
            code: 'FORBIDDEN',
            message: '没有权限。',
            details: { scope: 'admin' },
            request_id: 'body-request-id',
          }),
          {
            status: 403,
            headers: {
              'Content-Type': 'application/json',
              'X-Request-ID': 'header-request-id',
            },
          },
        ),
      ),
    )

    await expect(client.get('/admin/dashboard', { retryCount: 0 })).rejects.toMatchObject({
      name: 'ApiError',
      status: 403,
      code: 'FORBIDDEN',
      message: '没有权限。',
      requestId: 'header-request-id',
    } satisfies Partial<ApiError>)
  })

  it('reports a real network failure without switching to mock data', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('Failed to fetch')))

    await expect(client.get('/learning/today', { retryCount: 0 })).rejects.toMatchObject({
      code: 'NETWORK_ERROR',
      status: 0,
      retryable: true,
    } satisfies Partial<ApiError>)
  })

  it('refreshes once, keeps credentials in memory, and retries with the new token', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ code: 'AUTH_EXPIRED', message: '登录已过期。' }), {
          status: 401,
          headers: { 'Content-Type': 'application/json' },
        }),
      )
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ items: [] }), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        }),
      )

    vi.stubGlobal('fetch', fetchMock)
    client.setAccessToken('old-token')
    client.setRefreshHandler(async () => {
      client.setAccessToken('new-token')
    })

    await expect(client.get('/wordbooks', { retryCount: 0 })).resolves.toEqual({ items: [] })
    expect(fetchMock).toHaveBeenCalledTimes(2)

    const secondCall = fetchMock.mock.calls[1] as [string, RequestInit]
    const headers = new Headers(secondCall[1].headers)
    expect(headers.get('Authorization')).toBe('Bearer new-token')
    expect(secondCall[1].credentials).toBe('include')
  })

  it('expires the session when token refresh is rejected', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ code: 'AUTH_EXPIRED', message: '登录已过期。' }), {
        status: 401,
        headers: { 'Content-Type': 'application/json' },
      }),
    )
    const onSessionExpired = vi.fn()
    const refreshHandler = vi.fn().mockRejectedValue(
      new ApiError(401, 'AUTH_EXPIRED', '刷新令牌无效。', null, 'refresh-request-id'),
    )

    vi.stubGlobal('fetch', fetchMock)
    client.setAccessToken('expired-token')
    client.setRefreshHandler(refreshHandler)
    client.setSessionExpiredHandler(onSessionExpired)

    await expect(client.get('/wordbooks', { retryCount: 0 })).rejects.toMatchObject({
      code: 'AUTH_EXPIRED',
      status: 401,
    } satisfies Partial<ApiError>)
    expect(fetchMock).toHaveBeenCalledTimes(1)
    expect(refreshHandler).toHaveBeenCalledOnce()
    expect(onSessionExpired).toHaveBeenCalledOnce()
  })
  it('restores the double-submit CSRF header from the readable cookie after reload', async () => {
    document.cookie = 'csrf_token=restored-csrf; path=/'
    const fetchMock = vi.fn().mockResolvedValue(new Response(null, { status: 204 }))
    vi.stubGlobal('fetch', fetchMock)

    await client.post('/admin/users/example-id/reset-password')

    const call = fetchMock.mock.calls[0] as [string, RequestInit]
    expect(new Headers(call[1].headers).get('X-CSRF-Token')).toBe('restored-csrf')
    document.cookie = 'csrf_token=; max-age=0; path=/'
  })
})
