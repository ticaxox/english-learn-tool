import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import { describe, expect, it, vi } from 'vitest'
import MemberShell from '../components/MemberShell.vue'
import WordbookShelfCard from '../components/WordbookShelfCard.vue'
import type { Wordbook } from '../api/wordbooks'

vi.mock('../views/CoachView.vue', () => ({
  default: { template: '<div class="coach-test-stub">对话仅你可见</div>' },
}))

const StubPage = { template: '<div />' }

function makeRouter() {
  return createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/overview', name: 'overview', component: StubPage },
      { path: '/wordbooks', name: 'wordbooks', component: StubPage },
      { path: '/memory', name: 'memory', component: StubPage },
      { path: '/practice', name: 'practice', component: StubPage },
      { path: '/challenges', name: 'challenges', component: StubPage },
      { path: '/coach', name: 'coach', component: StubPage },
      { path: '/notifications', name: 'notifications', component: StubPage },
      { path: '/settings', name: 'settings', component: StubPage },
    ],
  })
}

function book(): Wordbook {
  return {
    id: 'book-1',
    name: 'Business English',
    description: 'Working English for product teams',
    visibility: 'organization',
    status: 'ready',
    version: '3',
    entry_count: 128,
    is_active: false,
    owner_id: null,
    created_by: null,
    created_at: '2026-10-20T10:00:00Z',
    updated_at: '2026-10-22T10:00:00Z',
  }
}

describe('member redesign', () => {
  it('keeps member navigation compact and exposes five primary information groups', async () => {
    const router = makeRouter()
    await router.push('/overview')
    await router.isReady()
    const wrapper = mount(MemberShell, {
      props: { displayName: 'Harold Chen', username: 'demo_member', isAdmin: false },
      global: { plugins: [router] },
    })

    expect(wrapper.findAll('.ia-nav-group')).toHaveLength(4)
    expect(wrapper.findAll('.ia-nav-subitem')).toHaveLength(0)
    expect(wrapper.findAll('.ia-mobile-nav a')).toHaveLength(4)
    expect(wrapper.find('.ia-notification-button').attributes('href')).toBe('/notifications')
    expect(wrapper.text()).toContain('今天也学一点')
  })

  it('opens the coach as a global side panel instead of a left navigation item', async () => {
    const router = makeRouter()
    await router.push('/overview')
    await router.isReady()
    const wrapper = mount(MemberShell, {
      props: { displayName: 'Harold Chen', username: 'demo_member', isAdmin: false },
      global: { plugins: [router] },
    })
    await wrapper.get('.ia-coach-toggle').trigger('click')
    await flushPromises()

    expect(router.currentRoute.value.name).toBe('coach')
    expect(wrapper.get('.ia-coach-panel').text()).toContain('对话仅你可见')
    expect(wrapper.find('.workspace-nav').text()).not.toContain('学习管家')
  })

  it('renders the real wordbook as a shelf object and emits guarded actions', async () => {
    const wrapper = mount(WordbookShelfCard, {
      props: {
        book: book(),
        statusLabel: '可用',
        statusDescription: '128 个词条',
        formattedDate: '2026/10/22',
        canActivate: true,
        canExport: true,
        canDelete: true,
        activating: false,
        compact: true,
      },
    })

    const card = wrapper.get('.wordbook-card')
    expect(wrapper.classes()).toContain('wordbook-card--compact')
    expect(card.get('.wordbook-card-body h3').text()).toBe('Business English')
    expect(card.find('.wordbook-cover h3').exists()).toBe(false)
    expect(card.text()).toContain('Business English')
    expect(card.text()).toContain('128 词条')
    expect(card.get('.wordbook-cover .wordbook-cover-stamp').text()).toBe('书架中')

    await card.get('[aria-label="查看 Business English 的词条"]').trigger('click')
    await card.get('[aria-label="将 Business English 设为当前主词书"]').trigger('click')
    await card.get('[aria-label="导出 Business English"]').trigger('click')
    await card.get('[aria-label="删除 Business English"]').trigger('click')

    expect(wrapper.emitted('detail')).toHaveLength(1)
    expect(wrapper.emitted('activate')).toHaveLength(1)
    expect(wrapper.emitted('export')).toHaveLength(1)
    expect(wrapper.emitted('delete')).toHaveLength(1)
  })

  it('keeps member shell free of browser business storage', () => {
    expect(localStorage.length).toBe(0)
    expect(sessionStorage.length).toBe(0)
  })
})
