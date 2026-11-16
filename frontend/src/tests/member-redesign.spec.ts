import { mount } from '@vue/test-utils'
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
  it('keeps personal navigation to four primary groups', async () => {
    const router = makeRouter()
    await router.push('/overview')
    await router.isReady()
    const wrapper = mount(MemberShell, {
      props: { displayName: 'Harold Chen', username: 'demo_member' },
      global: { plugins: [router] },
    })

    expect(wrapper.findAll('.ia-nav-group')).toHaveLength(4)
    expect(wrapper.findAll('.ia-nav-subitem')).toHaveLength(0)
    expect(wrapper.findAll('.ia-mobile-nav a')).toHaveLength(4)
    expect(wrapper.get('.workspace-nav').text()).toContain('Hob')
    expect(wrapper.find('.ia-notification-button').exists()).toBe(false)
    expect(wrapper.text()).toContain('今天也学一点')
  })

  it('offers the coach as a page and no longer as a floating window', async () => {
    const router = makeRouter()
    await router.push('/overview')
    await router.isReady()
    const wrapper = mount(MemberShell, {
      props: { displayName: 'Harold Chen', username: 'demo_member' },
      global: { plugins: [router] },
    })

    // The drawer is gone: nothing in the top bar opens a panel over the page.
    expect(wrapper.find('.ia-coach-toggle').exists()).toBe(false)
    expect(wrapper.find('.ia-coach-panel').exists()).toBe(false)
    expect(wrapper.find('.personal-workspace.is-coach-open').exists()).toBe(false)
    // The coach still has a home of its own, one click from the rail.
    expect(wrapper.find('.workspace-nav a[href="/coach"]').exists()).toBe(true)
  })

  it('renders the real wordbook as a bare shelf object that opens its panel', async () => {
    const wrapper = mount(WordbookShelfCard, { props: { book: book() } })

    const card = wrapper.get('.wordbook-card')
    expect(card.get('.wordbook-cover__name').text()).toBe('Business English')
    // Nothing but the binding and the name: the actions live in the panel.
    expect(card.find('.wordbook-card-actions').exists()).toBe(false)
    expect(card.find('.wordbook-card-body').exists()).toBe(false)
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
