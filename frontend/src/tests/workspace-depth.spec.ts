import { readFileSync } from 'node:fs'
import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import WordbookShelfCard from '../components/WordbookShelfCard.vue'
import type { Wordbook } from '../api/wordbooks'

function source(path: string): string {
  return readFileSync(new URL(path, import.meta.url), 'utf8')
}

function book(): Wordbook {
  return {
    id: 'book-depth-1',
    name: '深度工作词汇',
    description: 'Theme: work. Source: self-authored. License: CC0.',
    visibility: 'organization',
    status: 'ready',
    version: '2',
    entry_count: 120,
    is_active: true,
    owner_id: null,
    created_by: null,
    created_at: '2026-10-20T10:00:00Z',
    updated_at: '2026-10-22T10:00:00Z',
  }
}

describe('T-FE-017 workspace depth', () => {
  it('puts the day\'s tasks and the wordbook on the Today board', () => {
    const today = source('../views/TodayView.vue')
    // The board is the tasks: no player bar restating them, no tip box.
    expect(today).not.toContain('<GameHud')
    expect(today).toContain('crumb-task-list')
    // The wordbook is the book itself, with the name written on the cover.
    expect(today).toContain('crumb-today-book')
    expect(today).toContain('crumb-today-book__name')
  })

  it('keeps a wordbook card to its cover and name', () => {
    const sample = book()
    const wrapper = mount(WordbookShelfCard, { props: { book: sample } })

    expect(wrapper.find('.wordbook-description').exists()).toBe(false)
    expect(wrapper.find('.wordbook-card-meta').exists()).toBe(false)
    expect(wrapper.find('.wordbook-entry-count').exists()).toBe(false)
    expect(wrapper.get('.wordbook-cover__name').text()).toBe(sample.name)
  })

  it('shows all three memory styles with enabled and disabled states', () => {
    const shelf = source('../components/ShelfPicker.vue')
    expect(shelf).toContain('`shelf-book--${module}`')
    expect(shelf).toContain('is-locked')
    expect(shelf).toContain(":disabled=\"!enabled.includes(module)\"")
    // The view hands the shelf the server config, so a disabled mode stays on
    // the shelf but cannot be picked.
    const memory = source('../views/MemoryPracticeView.vue')
    expect(memory).toContain(':enabled="activeModules"')
  })

  it('gives the four AI practice types distinct icons and generation feedback', () => {
    const topbar = source('../components/PracticeTopBar.vue')
    expect(topbar).toContain('practiceIcons')
    expect(topbar).toContain('practice-topbar__tab--')
    const practice = source('../views/PracticeHubView.vue')
    expect(practice).toContain('practice-generation-state')
  })

  it('keeps Coach hierarchy and streaming state visible', () => {
    const coach = source('../views/CoachView.vue')
    expect(coach).toContain('coach-message-avatar')
    expect(coach).toContain('coach-thinking')
  })

  it('adds a rendered DSL map with main-line and branch legends', () => {
    const challenge = source('../views/ChallengeView.vue')
    const map = source('../components/ChallengeDslMap.vue')
    expect(challenge).toContain('ChallengeDslMap')
    expect(map).toContain('challenge-dsl-legend')
    expect(map).toContain('is-branch')
  })
})
