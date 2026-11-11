import { beforeEach, describe, expect, it } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { createMemoryHistory } from 'vue-router'
import { apiClient } from '../api/client'
import { createAppRouter } from '../router'
import { useAuthStore } from '../stores/auth'
import type { CurrentUser } from '../api/contracts'

function user(role: CurrentUser['role'], mustChangePassword = false): CurrentUser {
  return {
    id: '9ad81de0-83b0-44ba-a67c-ad817f73eb7d',
    username: role === 'admin' ? 'admin_user' : 'member_user',
    display_name: role === 'admin' ? '管理员' : '成员',
    role,
    must_change_password: mustChangePassword,
  }
}

function authenticatedRouter(role: CurrentUser['role'] = 'member', mustChangePassword = false) {
  const pinia = createPinia()
  const auth = useAuthStore(pinia)
  auth.user = user(role, mustChangePassword)
  auth.status = 'authenticated'
  auth.initialized = true
  return { router: createAppRouter(pinia, createMemoryHistory()), auth }
}

describe('personal route guards', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    apiClient.clearCredentials()
  })

  it('redirects unauthenticated users to login', async () => {
    const pinia = createPinia()
    const auth = useAuthStore(pinia)
    auth.clearSession()
    const router = createAppRouter(pinia, createMemoryHistory())
    await router.push('/overview')

    expect(router.currentRoute.value.name).toBe('login')
    expect(router.currentRoute.value.query.redirect).toBe('/overview')
  })

  it('keeps the personal destinations available to member accounts', async () => {
    const { router } = authenticatedRouter('member')
    for (const [path, name] of [
      ['/overview', 'overview'],
      ['/challenges', 'challenges'],
      ['/wordbooks', 'settings-wordbooks'],
      ['/settings/learning', 'settings-learning'],
      ['/settings/ai', 'settings-ai'],
      ['/settings/security', 'settings-security'],
      ['/settings/wordbooks', 'settings-wordbooks'],
      ['/coach', 'coach'],
    ] as const) {
      await router.push(path)
      expect(router.currentRoute.value.name).toBe(name)
    }
  })

  it('keeps administration behind the guard and drops notification routes', async () => {
    const admin = authenticatedRouter('admin').router
    for (const [path, name] of [
      ['/admin/users', 'admin-users'],
      ['/admin/dashboard', 'admin-dashboard'],
      ['/admin/ai/providers', 'admin-ai-providers'],
      ['/admin/knowledge', 'admin-knowledge'],
    ] as const) {
      await admin.push(path)
      expect(admin.currentRoute.value.name).toBe(name)
    }

    const member = authenticatedRouter('member').router
    for (const path of ['/admin', '/admin/users', '/admin/dashboard', '/admin/knowledge']) {
      await member.push(path)
      expect(member.currentRoute.value.name).toBe('overview')
    }

    for (const path of ['/notifications', '/notifications/preferences', '/settings/notifications']) {
      await member.push(path)
      expect(member.currentRoute.value.name).toBe('not-found')
    }
  })

  it('redirects learning and settings roots to the first personal tab', async () => {
    const { router } = authenticatedRouter('member')
    await router.push('/learning')
    expect(router.currentRoute.value.name).toBe('challenges')
    await router.push('/settings')
    expect(router.currentRoute.value.name).toBe('settings-learning')
  })

  it('forces a password change before other authenticated routes', async () => {
    const { router } = authenticatedRouter('member', true)
    await router.push('/wordbooks')
    expect(router.currentRoute.value.name).toBe('change-password')
  })
})
