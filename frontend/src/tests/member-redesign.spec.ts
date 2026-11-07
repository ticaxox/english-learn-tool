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
      { path: '/settings', name: 'settings', component: StubPage },
    ],
  })
}

function book(): Wordbook {
  return {
    id: 'book-1',
    name: 'Business English',
    description: 'Working English for product teams',
    visibility: 'private',
    status: 'ready',
    version: '3',
    entry_count: 128,
    is_active: false,
    owner_id: 'member-1',
    created_by: 'member-1',
    created_at: '2026-10-20T10:00:00Z',
    updated_at: '2026-10-22T10:00:00Z',
  }
}

describe('member redesign', () => {
  it('keeps personal navigation to five primary groups', async () => {
    const router = makeRouter()
    await router.push('/overview')
    await router.isReady()
    const wrapper = mount(MemberShell, {
      props: { displayName: 'Harold Chen', username: 'demo_member' },
      global: { plugins: [router] },
    })

    expect(wrapper.findAll('.ia-nav-group')).toHaveLength(5)
    expect(wrapper.findAll('.ia-nav-subitem')).toHaveLength(0)
    expect(wrapper.findAll('.ia-mobile-nav a')).toHaveLength(5)
    expect(wrapper.get('.workspace-nav').text()).toContain('AI 教练')
    expect(wrapper.find('.ia-notification-button').exists()).toBe(false)
    expect(wrapper.text()).toContain('今天也学一点')
  })

  it('keeps the floating coach and also offers a full coach page', async () => {
    const router = makeRouter()
    await router.push('/overview')
    await router.isReady()
    const wrapper = mount(MemberShell, {
      props: { displayName: 'Harold Chen', username: 'demo_member' },
      global: { plugins: [router] },
    })
    await wrapper.get('.ia-coach-toggle').trigger('click')
    await flushPromises()

    // Floating window: the page underneath does not change.
    expect(router.currentRoute.value.name).toBe('overview')
    expect(wrapper.get('.ia-coach-panel').text()).toContain('对话仅你可见')
    // The panel has no history list; the page route does.
    expect(wrapper.find('.ia-coach-panel .coach-history').exists()).toBe(false)
    expect(wrapper.find('.workspace-nav a[href="/coach"]').exists()).toBe(true)
    // The shell marks itself so the desktop layout can give the coach real space.
    expect(wrapper.find('.personal-workspace.is-coach-open').exists()).toBe(true)
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
    expect(card.find('.wordbook-card-badges').exists()).toBe(false)

    await card.trigger('click')
    expect(wrapper.emitted('detail')).toHaveLength(1)
    expect(wrapper.emitted('activate')).toBeUndefined()
    expect(wrapper.emitted('export')).toBeUndefined()
    expect(wrapper.emitted('delete')).toBeUndefined()
  })

  it('keeps member shell free of browser business storage', () => {
    expect(localStorage.length).toBe(0)
    expect(sessionStorage.length).toBe(0)
  })
})
