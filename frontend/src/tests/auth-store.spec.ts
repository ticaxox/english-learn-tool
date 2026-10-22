import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { apiClient } from '../api/client'
import { useAuthStore } from '../stores/auth'

describe('auth store', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    apiClient.clearCredentials()
    localStorage.clear()
    sessionStorage.clear()
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

  it('changes the password through the real API and refreshes the current user', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(new Response(null, { status: 204 }))
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            id: '9ad81de0-83b0-44ba-a67c-ad817f73eb7d',
            username: 'member_user',
            display_name: '成员',
            role: 'member',
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
    apiClient.setAccessToken('memory-only-token')
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
    expect(apiClient.getAccessToken()).toBe('memory-only-token')

    const changePasswordCall = fetchMock.mock.calls[0] as [string, RequestInit]
    expect(changePasswordCall[0]).toBe('/api/v1/auth/change-password')
    expect(changePasswordCall[1].method).toBe('POST')
    expect(JSON.parse(String(changePasswordCall[1].body))).toEqual({
      old_password: 'Temporary-pass-123',
      new_password: 'Permanent-pass-456',
    })
  })
})

