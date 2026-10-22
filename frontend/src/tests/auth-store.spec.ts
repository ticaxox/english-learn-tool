import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { apiClient } from '../api/client'
import { PasswordChangedLoginRequiredError, useAuthStore } from '../stores/auth'

describe('auth store', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    apiClient.clearCredentials()
    localStorage.clear()
    sessionStorage.clear()
    document.cookie = 'csrf_token=; max-age=0; path=/'
    vi.unstubAllGlobals()
  })

  it('uses the real login and /auth/me requests without browser storage', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ access_token: 'memory-only-token', csrf_token: 'csrf-1' }), {
          status: 200,
          headers: {
            'Content-Type': 'application/json',
            'X-Request-ID': 'login-request',
          },
        }),
      )
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            id: '9ad81de0-83b0-44ba-a67c-ad817f73eb7d',
            username: 'leader',
            display_name: '学习负责人',
            role: 'admin',
            must_change_password: false,
          }),
          {
            status: 200,
            headers: {
              'Content-Type': 'application/json',
              'X-Request-ID': 'me-request',
            },
          },
        ),
      )

    vi.stubGlobal('fetch', fetchMock)
    const auth = useAuthStore()

    const user = await auth.login({ username: 'leader', password: 'Strong-pass-123' })

    expect(user.role).toBe('admin')
    expect(auth.isAuthenticated).toBe(true)
    expect(apiClient.getAccessToken()).toBe('memory-only-token')
    expect(localStorage.length).toBe(0)
    expect(sessionStorage.length).toBe(0)

    const loginCall = fetchMock.mock.calls[0] as [string, RequestInit]
    const meCall = fetchMock.mock.calls[1] as [string, RequestInit]
    expect(loginCall[0]).toBe('/api/v1/auth/login')
    expect(meCall[0]).toBe('/api/v1/auth/me')
    expect((loginCall[1].headers as Headers).get('Authorization')).toBeNull()
    expect((meCall[1].headers as Headers).get('Authorization')).toBe('Bearer memory-only-token')
  })

  it('clears the in-memory session when refresh is rejected', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify({ code: 'AUTH_EXPIRED', message: '刷新令牌无效。' }), {
          status: 401,
          headers: { 'Content-Type': 'application/json' },
        }),
      ),
    )
    apiClient.setAccessToken('stale-token')
    const auth = useAuthStore()

    await auth.restoreSession()

    expect(auth.status).toBe('anonymous')
    expect(auth.initialized).toBe(true)
    expect(auth.lastError).toBeNull()
    expect(apiClient.getAccessToken()).toBeNull()
  })

  it('changes the password, re-authenticates, and reloads the real current user', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(new Response(null, { status: 204 }))
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            access_token: 'reauth-memory-token',
            csrf_token: 'reauth-csrf-token',
            expires_in: 900,
          }),
          { status: 200, headers: { 'Content-Type': 'application/json' } },
        ),
      )
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            id: '9ad81de0-83b0-44ba-a67c-ad817f73eb7d',
            username: 'member_user',
            display_name: '成员',
            role: 'member',
            status: 'active',
            must_change_password: false,
          }),
          {
            status: 200,
            headers: {
              'Content-Type': 'application/json',
              'X-Request-ID': 'me-after-password-change',
            },
          },
        ),
      )

    vi.stubGlobal('fetch', fetchMock)
    apiClient.setAccessToken('revoked-memory-token')
    apiClient.setCsrfToken('old-csrf-token')
    const auth = useAuthStore()
    auth.user = {
      id: '9ad81de0-83b0-44ba-a67c-ad817f73eb7d',
      username: 'member_user',
      display_name: '成员',
      role: 'member',
      must_change_password: true,
    }
    auth.status = 'authenticated'
    auth.initialized = true

    await auth.changePassword({
      old_password: 'Temporary-pass-123',
      new_password: 'Permanent-pass-456',
    })

    expect(auth.user?.must_change_password).toBe(false)
    expect(auth.mustChangePassword).toBe(false)
    expect(apiClient.getAccessToken()).toBe('reauth-memory-token')
    expect(fetchMock).toHaveBeenCalledTimes(3)

    const changePasswordCall = fetchMock.mock.calls[0] as [string, RequestInit]
    const reloginCall = fetchMock.mock.calls[1] as [string, RequestInit]
    const meCall = fetchMock.mock.calls[2] as [string, RequestInit]
    expect(changePasswordCall[0]).toBe('/api/v1/auth/change-password')
    expect(JSON.parse(String(changePasswordCall[1].body))).toEqual({
      old_password: 'Temporary-pass-123',
      new_password: 'Permanent-pass-456',
    })
    expect(reloginCall[0]).toBe('/api/v1/auth/login')
    expect(JSON.parse(String(reloginCall[1].body))).toEqual({
      username: 'member_user',
      password: 'Permanent-pass-456',
    })
    expect(meCall[0]).toBe('/api/v1/auth/me')
    expect(new Headers(meCall[1].headers).get('Authorization')).toBe('Bearer reauth-memory-token')
    expect(localStorage.length).toBe(0)
    expect(sessionStorage.length).toBe(0)
  })

  it('requires manual login when re-authentication after a password change fails', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(new Response(null, { status: 204 }))
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({ code: 'AUTH_INVALID_CREDENTIALS', message: '用户名或密码错误。' }),
          { status: 401, headers: { 'Content-Type': 'application/json' } },
        ),
      )
    vi.stubGlobal('fetch', fetchMock)
    const auth = useAuthStore()
    auth.user = {
      id: '9ad81de0-83b0-44ba-a67c-ad817f73eb7d',
      username: 'member_user',
      display_name: '成员',
      role: 'member',
      must_change_password: true,
    }
    auth.status = 'authenticated'
    auth.initialized = true

    await expect(
      auth.changePassword({
        old_password: 'Temporary-pass-123',
        new_password: 'Permanent-pass-456',
      }),
    ).rejects.toBeInstanceOf(PasswordChangedLoginRequiredError)

    expect(auth.user).toBeNull()
    expect(apiClient.getAccessToken()).toBeNull()
    expect(auth.lastError).toBeInstanceOf(PasswordChangedLoginRequiredError)
  })
  it('restores the session with the readable CSRF cookie after a page reload', async () => {
    document.cookie = 'csrf_token=csrf-from-cookie; path=/'
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            access_token: 'restored-memory-token',
            csrf_token: 'csrf-rotated',
            expires_in: 900,
          }),
          { status: 200, headers: { 'Content-Type': 'application/json' } },
        ),
      )
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            id: '9ad81de0-83b0-44ba-a67c-ad817f73eb7d',
            username: 'member_user',
            display_name: '成员',
            role: 'member',
            status: 'active',
            must_change_password: false,
          }),
          { status: 200, headers: { 'Content-Type': 'application/json' } },
        ),
      )
    vi.stubGlobal('fetch', fetchMock)
    const auth = useAuthStore()

    await auth.restoreSession()

    expect(auth.isAuthenticated).toBe(true)
    const refreshCall = fetchMock.mock.calls[0] as [string, RequestInit]
    expect(refreshCall[0]).toBe('/api/v1/auth/refresh')
    expect(new Headers(refreshCall[1].headers).get('X-CSRF-Token')).toBe('csrf-from-cookie')
    expect(refreshCall[1].credentials).toBe('include')
    expect(localStorage.length).toBe(0)
    expect(sessionStorage.length).toBe(0)
  })
  it('refreshes an expired access token once before completing real logout', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({ code: 'AUTH_INVALID_TOKEN', message: 'The access token is invalid.' }),
          { status: 401, headers: { 'Content-Type': 'application/json' } },
        ),
      )
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            access_token: 'refreshed-logout-token',
            csrf_token: 'refreshed-logout-csrf',
            expires_in: 900,
          }),
          { status: 200, headers: { 'Content-Type': 'application/json' } },
        ),
      )
      .mockResolvedValueOnce(new Response(null, { status: 204 }))
    vi.stubGlobal('fetch', fetchMock)
    apiClient.setAccessToken('expired-logout-token')
    apiClient.setCsrfToken('old-logout-csrf')
    const auth = useAuthStore()
    apiClient.setRefreshHandler(async () => auth.refreshAccessToken())
    auth.user = {
      id: '9ad81de0-83b0-44ba-a67c-ad817f73eb7d',
      username: 'member_user',
      display_name: '成员',
      role: 'member',
      must_change_password: false,
    }
    auth.status = 'authenticated'
    auth.initialized = true

    await auth.logout()

    expect(fetchMock).toHaveBeenCalledTimes(3)
    const refreshCall = fetchMock.mock.calls[1] as [string, RequestInit]
    const retriedLogoutCall = fetchMock.mock.calls[2] as [string, RequestInit]
    expect(refreshCall[0]).toBe('/api/v1/auth/refresh')
    expect(new Headers(refreshCall[1].headers).get('X-CSRF-Token')).toBe('old-logout-csrf')
    expect(retriedLogoutCall[0]).toBe('/api/v1/auth/logout')
    expect(new Headers(retriedLogoutCall[1].headers).get('Authorization')).toBe(
      'Bearer refreshed-logout-token',
    )
    expect(new Headers(retriedLogoutCall[1].headers).get('X-CSRF-Token')).toBe(
      'refreshed-logout-csrf',
    )
    expect(auth.status).toBe('anonymous')
    expect(auth.user).toBeNull()
    expect(apiClient.getAccessToken()).toBeNull()
  })

  it('clears in-memory credentials and keeps a visible server logout error', async () => {
    const logoutFailure = new Response(
      JSON.stringify({ code: 'AUTH_CSRF_FAILED', message: 'CSRF validation failed.' }),
      { status: 403, headers: { 'Content-Type': 'application/json' } },
    )
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(logoutFailure))
    apiClient.setAccessToken('memory-token')
    const auth = useAuthStore()
    auth.user = {
      id: '9ad81de0-83b0-44ba-a67c-ad817f73eb7d',
      username: 'member_user',
      display_name: '成员',
      role: 'member',
      must_change_password: false,
    }
    auth.status = 'authenticated'
    auth.initialized = true

    await expect(auth.logout()).rejects.toMatchObject({
      status: 403,
      code: 'AUTH_CSRF_FAILED',
    })

    expect(auth.user).toBeNull()
    expect(auth.status).toBe('anonymous')
    expect(auth.lastError).toMatchObject({ status: 403, code: 'AUTH_CSRF_FAILED' })
    expect(apiClient.getAccessToken()).toBeNull()
  })})
