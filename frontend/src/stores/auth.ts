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

export const useAuthStore = defineStore('auth', () => {
  const user = ref<CurrentUser | null>(null)
  const status = ref<AuthStatus>('idle')
  const initialized = ref(false)
  const lastError = ref<unknown>(null)

  let restoreInFlight: Promise<void> | null = null

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
    const payload = await apiClient.post<unknown>(
      '/auth/refresh',
      undefined,
      { skipAuthRefresh: true, retryCount: 0 },
    )
    applyTokenResponse(payload)
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

  async function changePassword(payload: ChangePasswordPayload): Promise<void> {
    lastError.value = null
    await apiClient.post<void>('/auth/change-password', payload)
    await loadCurrentUser()
  }

  async function logout(): Promise<void> {
    try {
      await apiClient.post<void>(
        '/auth/logout',
        undefined,
        { skipAuthRefresh: true, retryCount: 0 },
      )
    } finally {
      markSessionExpired()
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
    refreshAccessToken,
    markSessionExpired,
    clearSession,
  }
})