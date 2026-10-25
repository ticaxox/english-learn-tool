import { mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import { describe, expect, it } from 'vitest'
import MemberShell from '../components/MemberShell.vue'
import WordbookShelfCard from '../components/WordbookShelfCard.vue'
import type { Wordbook } from '../api/wordbooks'

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
  it('keeps member navigation compact and exposes real routes on mobile', async () => {
    const router = makeRouter()
    await router.push('/overview')
    await router.isReady()
    const wrapper = mount(MemberShell, {
      props: { displayName: 'Harold Chen', username: 'demo_member' },
      global: { plugins: [router] },
    })

    expect(wrapper.findAll('.member-nav-link')).toHaveLength(8)
    expect(wrapper.findAll('.member-mobile-nav a')).toHaveLength(6)
    expect(wrapper.text()).toContain('@demo_member')
    expect(wrapper.text()).toContain('今天也学一点')
    expect(wrapper.find('.member-mobile-nav a[href="/memory"]').exists()).toBe(true)
  })

  it('opens the concierge as navigation guidance, not a fake AI response', async () => {
    const router = makeRouter()
    const wrapper = mount(MemberShell, {
      props: { displayName: 'Harold Chen', username: 'demo_member' },
      global: { plugins: [router] },
    })
    await wrapper.get('.member-concierge-link').trigger('click')

    expect(wrapper.get('.member-concierge-drawer').text()).toContain('对话仅你可见')
    expect(wrapper.find('.member-drawer-actions a[href="/coach"]').exists()).toBe(true)
    expect(wrapper.find('.member-drawer-actions a[href="/overview"]').exists()).toBe(true)
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
      },
    })

    const card = wrapper.get('.wordbook-card')
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
