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

describe('route guards', () => {
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

  it('blocks member access to admin routes', async () => {
    const pinia = createPinia()
    const auth = useAuthStore(pinia)
    auth.user = user('member')
    auth.status = 'authenticated'
    auth.initialized = true

    const router = createAppRouter(pinia, createMemoryHistory())
    await router.push('/admin/users')

    expect(router.currentRoute.value.name).toBe('overview')
    expect(router.currentRoute.value.query.access).toBe('denied')
  })

  it('blocks member access to admin AI usage routes', async () => {
    const pinia = createPinia()
    const auth = useAuthStore(pinia)
    auth.user = user('member')
    auth.status = 'authenticated'
    auth.initialized = true

    const router = createAppRouter(pinia, createMemoryHistory())
    await router.push('/admin/ai/usage')

    expect(router.currentRoute.value.name).toBe('overview')
    expect(router.currentRoute.value.query.access).toBe('denied')
  })

  it('allows members to open the AI coach workspace', async () => {
    const pinia = createPinia()
    const auth = useAuthStore(pinia)
    auth.user = user('member')
    auth.status = 'authenticated'
    auth.initialized = true

    const router = createAppRouter(pinia, createMemoryHistory())
    await router.push('/coach')
    expect(router.currentRoute.value.name).toBe('coach')
  })
  it('allows members to open the notification center and preferences', async () => {
    const pinia = createPinia()
    const auth = useAuthStore(pinia)
    auth.user = user('member')
    auth.status = 'authenticated'
    auth.initialized = true

    const router = createAppRouter(pinia, createMemoryHistory())
    await router.push('/notifications')
    expect(router.currentRoute.value.name).toBe('notifications')

    await router.push('/notifications/preferences')
    expect(router.currentRoute.value.name).toBe('notification-preferences')
  })

  it('redirects unauthenticated notification access to login with a return path', async () => {
    const pinia = createPinia()
    const auth = useAuthStore(pinia)
    auth.clearSession()

    const router = createAppRouter(pinia, createMemoryHistory())
    await router.push('/notifications/preferences')

    expect(router.currentRoute.value.name).toBe('login')
    expect(router.currentRoute.value.query.redirect).toBe('/notifications/preferences')
  })
  it('forces a password change before other authenticated routes', async () => {
    const pinia = createPinia()
    const auth = useAuthStore(pinia)
    auth.user = user('member', true)
    auth.status = 'authenticated'
    auth.initialized = true

    const router = createAppRouter(pinia, createMemoryHistory())
    await router.push('/wordbooks')

    expect(router.currentRoute.value.name).toBe('change-password')
  })
})
