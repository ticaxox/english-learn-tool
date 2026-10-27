import { readFileSync } from 'node:fs'
import { flushPromises, mount } from '@vue/test-utils'
import { defineComponent, h } from 'vue'
import { createMemoryHistory, createRouter } from 'vue-router'
import { describe, expect, it, vi } from 'vitest'
import MemberShell from '../components/MemberShell.vue'
import SettingsHubView from '../views/SettingsHubView.vue'

vi.mock('../views/CoachView.vue', () => ({
  default: defineComponent({ render: () => h('div', { class: 'coach-test-stub' }, '对话仅你可见') }),
}))

const StubPage = defineComponent({ render: () => h('div') })

function makeRouter() {
  return createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/overview', name: 'overview', component: StubPage },
      { path: '/wordbooks', name: 'wordbooks', component: StubPage },
      { path: '/challenges', name: 'challenges', component: StubPage },
      { path: '/memory', name: 'memory', component: StubPage },
      { path: '/practice', name: 'practice', component: StubPage },
      { path: '/coach', name: 'coach', component: StubPage },
      { path: '/notifications', name: 'notifications', component: StubPage },
      { path: '/admin/users', name: 'admin-users', component: StubPage },
      { path: '/admin/dashboard', name: 'admin-dashboard', component: StubPage },
      { path: '/admin/ai/providers', name: 'admin-providers', component: StubPage },
      {
        path: '/settings',
        component: SettingsHubView,
        children: [
          { path: 'learning', name: 'settings-learning', component: StubPage },
          { path: 'notifications', name: 'settings-notifications', component: StubPage },
          { path: 'security', name: 'settings-security', component: StubPage },
        ],
      },
    ],
  })
}

async function mountShell(isAdmin = false) {
  const router = makeRouter()
  await router.push('/overview')
  await router.isReady()
  const wrapper = mount(MemberShell, {
    props: { displayName: 'Harold Chen', username: 'demo_member', isAdmin },
    global: { plugins: [router] },
  })
  return { wrapper, router }
}

function source(path: string): string {
  return readFileSync(new URL(path, import.meta.url), 'utf8')
}

describe('T-FE-019 information architecture', () => {
  it('shows five first-level groups to admins and hides organization management from members', async () => {
    const member = await mountShell(false)
    expect(member.wrapper.findAll('.ia-nav-group')).toHaveLength(4)
    expect(member.wrapper.find('[data-nav-group="organization"]').exists()).toBe(false)
    expect(member.wrapper.findAll('.ia-mobile-nav a')).toHaveLength(4)

    const admin = await mountShell(true)
    expect(admin.wrapper.findAll('.ia-nav-group')).toHaveLength(5)
    expect(admin.wrapper.get('[data-nav-group="organization"] a').attributes('href')).toBe('/admin/users')
  })

  it('keeps learning subitems below one learning-center group and removes coach/notifications from primary navigation', async () => {
    const { wrapper } = await mountShell(false)
    const learning = wrapper.get('[data-nav-group="learning"]')
    expect(learning.findAll('.ia-nav-subitem').map((link) => link.text())).toEqual([
      '每日闯关',
      '记忆练习',
      'AI 练习',
    ])
    expect(wrapper.get('.workspace-nav').text()).not.toContain('学习管家')
    expect(wrapper.get('.workspace-nav').text()).not.toContain('通知')
    expect(wrapper.get('.ia-notification-button').attributes('href')).toBe('/notifications')
  })

  it('moves profile and signout into the topbar avatar menu', async () => {
    const { wrapper } = await mountShell(false)
    await wrapper.get('.ia-profile-trigger').trigger('click')
    const menu = wrapper.get('.ia-profile-menu')
    expect(menu.text()).toContain('个人资料')
    expect(menu.text()).toContain('Harold Chen')
    expect(menu.text()).toContain('@demo_member')
    expect(menu.find('a[href="/settings"]').exists()).toBe(true)
    expect(menu.find('a[href="/settings/security"]').exists()).toBe(true)
    expect(menu.text()).toContain('退出登录')
  })

  it('opens the global coach panel and the /coach deep link without a left navigation item', async () => {
    const { wrapper, router } = await mountShell(false)
    expect(wrapper.get('.ia-coach-toggle').attributes('aria-label')).toBe('打开学习管家')
    await wrapper.get('.ia-coach-toggle').trigger('click')
    await flushPromises()
    expect(router.currentRoute.value.name).toBe('coach')
    expect(wrapper.get('.ia-coach-panel').text()).toContain('对话仅你可见')
    await flushPromises()
    await wrapper.get('.ia-coach-panel button[aria-label="关闭学习管家"]').trigger('click')
    await flushPromises()
    expect(router.currentRoute.value.name).toBe('overview')

    const deepLinkRouter = makeRouter()
    await deepLinkRouter.push('/coach')
    await deepLinkRouter.isReady()
    const deepLink = mount(MemberShell, {
      props: { displayName: 'Harold Chen', username: 'demo_member', isAdmin: false },
      global: { plugins: [deepLinkRouter] },
    })
    await flushPromises()
    expect(deepLink.find('.ia-coach-panel').exists()).toBe(true)
  })

  it('defines organization and AI platform internal tabs plus the merged settings tabs', async () => {
    const adminHtml = source('../views/AdminManagementView.vue')
    expect(adminHtml).toContain("label: '成员管理'")
    expect(adminHtml).toContain("label: '组织看板'")
    expect(adminHtml).toContain("label: 'AI 平台'")

    const aiHtml = source('../views/AdminAiPlatformView.vue')
    expect(aiHtml).toContain("label: '提供商'")
    expect(aiHtml).toContain("label: '提示词'")
    expect(aiHtml).toContain("label: '用量'")

    const router = makeRouter()
    await router.push('/settings/notifications')
    await router.isReady()
    const settings = mount(SettingsHubView, { global: { plugins: [router] } })
    const settingsTabs = settings.findAll('.ia-settings-tabs')[0].findAll('.ia-tab')
    expect(settingsTabs).toHaveLength(3)
    expect(settingsTabs.find((tab) => tab.classes().includes('ia-tab--active'))?.text()).toContain('通知与免打扰')
  })

  it('exposes the two self-study entries from the challenge page', () => {
    const challenge = source('../views/ChallengeView.vue')
    expect(challenge).toContain('challenge-self-study')
    expect(challenge).toContain('to="/memory"')
    expect(challenge).toContain('to="/practice"')
    expect(source('../information-architecture.css')).toContain('.ia-coach-panel')
  })
})
