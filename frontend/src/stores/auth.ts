import { computed, ref } from 'vue'
import { defineStore } from 'pinia'
import { apiClient } from '../api/client'
import {
  parseAuthTokenResponse,
  parseCurrentUser,
  type AuthTokenResponse,
  type CurrentUser,
} from '../api/contracts'
import { isApiError } from '../api/errors'

export type AuthStatus = 'idle' | 'loading' | 'authenticated' | 'anonymous' | 'error'

export interface LoginCredentials {
  username: string
  password: string
}

export interface ChangePasswordPayload {
  old_password: string
  new_password: string
}

export interface ChangeUsernamePayload {
  username: string
}

export class PasswordChangedLoginRequiredError extends Error {
  readonly cause: unknown

  constructor(cause: unknown) {
    super('密码已更新，但自动重新登录失败。请使用新密码重新登录。')
    this.name = 'PasswordChangedLoginRequiredError'
    this.cause = cause
  }
}

export const useAuthStore = defineStore('auth', () => {
  const user = ref<CurrentUser | null>(null)
  const status = ref<AuthStatus>('idle')
  const initialized = ref(false)
  const lastError = ref<unknown>(null)

  let restoreInFlight: Promise<void> | null = null
  let refreshInFlight: Promise<void> | null = null

  const isAuthenticated = computed(() => user.value !== null)
  const isAdmin = computed(() => user.value?.role === 'admin')
  const mustChangePassword = computed(() => user.value?.must_change_password === true)
  const displayName = computed(() => user.value?.display_name ?? user.value?.username ?? '')

  function applyTokenResponse(payload: unknown): void {
    const tokenResponse: AuthTokenResponse = parseAuthTokenResponse(payload)
    apiClient.setAccessToken(tokenResponse.access_token)
    if (tokenResponse.csrf_token) {
      apiClient.setCsrfToken(tokenResponse.csrf_token)
    }
  }

  async function loadCurrentUser(): Promise<CurrentUser> {
    const payload = await apiClient.get<unknown>('/auth/me')
    const currentUser = parseCurrentUser(payload)
    user.value = currentUser
    return currentUser
  }

  async function login(credentials: LoginCredentials): Promise<CurrentUser> {
    status.value = 'loading'
    lastError.value = null

    try {
      const payload = await apiClient.post<unknown>(
        '/auth/login',
        credentials,
        { skipAuthRefresh: true, retryCount: 0 },
      )
      applyTokenResponse(payload)
      const currentUser = await loadCurrentUser()
      status.value = 'authenticated'
      initialized.value = true
      return currentUser
    } catch (error) {
      user.value = null
      apiClient.clearCredentials()
      status.value = isApiError(error) && error.status === 401 ? 'anonymous' : 'error'
      lastError.value = error
      throw error
    }
  }

  async function refreshAccessToken(): Promise<void> {
    // Startup restore and a 401-triggered refresh can overlap; one rotation only.
    if (!refreshInFlight) {
      refreshInFlight = (async () => {
        const rotate = async (): Promise<void> => {
          const payload = await apiClient.post<unknown>(
            '/auth/refresh',
            undefined,
            { skipAuthRefresh: true, retryCount: 0 },
          )
          applyTokenResponse(payload)
        }
        // Tabs share one refresh cookie; serialise rotation across them so a
        // stale in-flight request cannot trip refresh-token reuse detection.
        if (typeof navigator !== 'undefined' && 'locks' in navigator) {
          await navigator.locks.request('crumbtrail.auth.refresh', rotate)
        } else {
          await rotate()
        }
      })().finally(() => {
        refreshInFlight = null
      })
    }
    await refreshInFlight
  }

  async function restoreSession(): Promise<void> {
    if (initialized.value) {
      return
    }

    if (restoreInFlight) {
      return restoreInFlight
    }

    restoreInFlight = (async () => {
      status.value = 'loading'
      lastError.value = null

      try {
        await refreshAccessToken()
        await loadCurrentUser()
        status.value = 'authenticated'
      } catch (error) {
        user.value = null
        apiClient.clearCredentials()

        if (isApiError(error) && error.status === 401) {
          status.value = 'anonymous'
        } else {
          status.value = 'error'
          lastError.value = error
        }
      } finally {
        initialized.value = true
        restoreInFlight = null
      }
    })()

    return restoreInFlight
  }

  async function ensureInitialized(): Promise<void> {
    if (!initialized.value) {
      await restoreSession()
    }
  }

  async function retryInitialization(): Promise<void> {
    initialized.value = false
    await restoreSession()
  }

  async function changeUsername(payload: ChangeUsernamePayload): Promise<void> {
    lastError.value = null
    try {
      const result = await apiClient.patch<unknown>('/auth/me', payload)
      user.value = parseCurrentUser(result)
    } catch (error) {
      lastError.value = error
      throw error
    }
  }

  async function changePassword(payload: ChangePasswordPayload): Promise<void> {
    const currentUsername = user.value?.username
    if (!currentUsername) {
      throw new Error('当前账号信息缺失，无法安全修改密码。')
    }

    lastError.value = null
    await apiClient.post<void>('/auth/change-password', payload)

    // The backend revokes every refresh session and clears both cookies after a password change.
    // Re-authenticate with the new password so /auth/me and page reloads use a fresh real session.
    apiClient.clearCredentials()
    user.value = null
    status.value = 'anonymous'
    initialized.value = true

    try {
      await login({ username: currentUsername, password: payload.new_password })
    } catch (error) {
      const reauthError = new PasswordChangedLoginRequiredError(error)
      lastError.value = reauthError
      throw reauthError
    }
  }

  async function logout(): Promise<void> {
    let logoutError: unknown = null
    try {
      await apiClient.post<void>(
        '/auth/logout',
        undefined,
        { retryCount: 0 },
      )
    } catch (error) {
      logoutError = error
    } finally {
      markSessionExpired()
    }

    if (logoutError) {
      lastError.value = logoutError
      throw logoutError
    }
  }

  function markSessionExpired(): void {
    user.value = null
    status.value = 'anonymous'
    lastError.value = null
    initialized.value = true
    apiClient.clearCredentials()
  }

  function clearSession(): void {
    markSessionExpired()
  }

  return {
    user,
    status,
    initialized,
    lastError,
    isAuthenticated,
    isAdmin,
    mustChangePassword,
    displayName,
    login,
    logout,
    restoreSession,
    ensureInitialized,
    retryInitialization,
    changePassword,
    changeUsername,
    refreshAccessToken,
    markSessionExpired,
    clearSession,
  }
})