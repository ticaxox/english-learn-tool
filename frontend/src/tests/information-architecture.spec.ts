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
      { path: '/wordbooks', redirect: '/settings/wordbooks' },
      { path: '/challenges', name: 'challenges', component: StubPage },
      { path: '/memory', name: 'memory', component: StubPage },
      { path: '/practice', name: 'practice', component: StubPage },
      { path: '/coach', name: 'coach', component: StubPage },
      {
        path: '/settings',
        component: SettingsHubView,
        children: [
          { path: 'learning', name: 'settings-learning', component: StubPage },
          { path: 'ai', name: 'settings-ai', component: StubPage },
          { path: 'security', name: 'settings-security', component: StubPage },
          { path: 'wordbooks', name: 'settings-wordbooks', component: StubPage },
        ],
      },
    ],
  })
}

async function mountShell() {
  const router = makeRouter()
  await router.push('/overview')
  await router.isReady()
  const wrapper = mount(MemberShell, {
    props: { displayName: 'Harold Chen', username: 'demo_member' },
    global: { plugins: [router] },
  })
  return { wrapper, router }
}

function source(path: string): string {
  return readFileSync(new URL(path, import.meta.url), 'utf8')
}

describe('T-FE-020 personal information architecture', () => {
  it('shows exactly four first-level destinations for every personal account', async () => {
    const { wrapper } = await mountShell()
    const labels = wrapper.findAll('.ia-nav-primary').map((link) => link.text().trim())
    expect(labels).toEqual(['今日学习', '记忆练习', 'AI 练习', '设置'])
    expect(wrapper.findAll('.ia-mobile-nav a')).toHaveLength(4)
    expect(wrapper.find('[data-nav-group="organization"]').exists()).toBe(false)
    expect(wrapper.find('.ia-notification-button').exists()).toBe(false)
  })

  it('keeps practice and memory as their own first-level destinations', async () => {
    const { wrapper } = await mountShell()
    expect(wrapper.findAll('.ia-nav-subitem')).toHaveLength(0)
    expect(wrapper.find('.workspace-nav a[href="/practice"]').exists()).toBe(true)
    expect(wrapper.find('.workspace-nav a[href="/memory"]').exists()).toBe(true)
    expect(wrapper.get('.workspace-nav').text()).not.toContain('学习中心')
    expect(wrapper.get('.workspace-nav').text()).not.toContain('通知')

    const router = makeRouter()
    await router.push('/practice')
    await router.isReady()
    const practiceShell = mount(MemberShell, {
      props: { displayName: 'Harold Chen', username: 'demo_member' },
      global: { plugins: [router] },
    })
    expect(practiceShell.findAll('.workspace-topbar-tab')).toHaveLength(0)
    expect(practiceShell.findAll('.workspace-mode')).toHaveLength(0)
    expect(practiceShell.get('.workspace-topbar-heading').text()).toContain('AI 练习')
  })

  it('keeps profile actions and the global AI coach on the shared shell', async () => {
    const { wrapper, router } = await mountShell()
    await wrapper.get('.ia-profile-trigger').trigger('click')
    const menu = wrapper.get('.ia-profile-menu')
    expect(menu.find('a[href="/settings/learning"]').exists()).toBe(true)
    expect(menu.find('a[href="/settings/security"]').exists()).toBe(true)
    expect(menu.text()).toContain('退出登录')

    await wrapper.get('.ia-coach-toggle').trigger('click')
    await flushPromises()
    // The coach is a floating window now: opening it leaves the page alone.
    expect(router.currentRoute.value.name).toBe('overview')
    expect(wrapper.get('.ia-coach-panel').text()).toContain('对话仅你可见')
  })

  it('puts the four settings tabs in the shared top bar', async () => {
    const router = makeRouter()
    await router.push('/settings/ai')
    await router.isReady()
    const wrapper = mount(MemberShell, {
      props: { displayName: 'Harold Chen', username: 'demo_member' },
      global: { plugins: [router] },
    })
    const tabs = wrapper.findAll('.workspace-topbar-tab')
    expect(tabs.map((tab) => tab.text().trim())).toEqual(['词书', '学习设置', 'AI 配置', '我的账户'])
    expect(tabs.map((tab) => tab.attributes('href'))).toEqual([
      '/settings/wordbooks',
      '/settings/learning',
      '/settings/ai',
      '/settings/security',
    ])
    expect(wrapper.get('.workspace-topbar-tab.is-active').text()).toContain('AI 配置')
  })

  it('renders the daily map from its Markdown-like description on Today', () => {
    const today = source('../views/TodayView.vue')
    const challenge = source('../views/ChallengeView.vue')
    expect(today).toContain('<ChallengeView embedded />')
    expect(today).toContain('crumb-trail-board')
    expect(challenge).toContain('ChallengeDslMap')
    expect(challenge).toContain('mapDsl')
    expect(challenge).toContain('parseChallengeMapDsl')
  })

  it('does not restore legacy organization or notification routes in the production router', () => {
    const router = source('../router/index.ts')
    expect(router).not.toContain("path: 'admin'")
    expect(router).not.toContain("path: 'notifications'")
    expect(router).toContain("path: 'ai'")
    expect(router).toContain('PersonalAiConfigView')
  })
})
