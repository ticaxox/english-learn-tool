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
  it('adds a readable Today progress ring and real streak/goal support', () => {
    const today = source('../views/TodayView.vue')
    expect(today).toContain('crumb-route-progress')
    expect(today).toContain('<StudyStatsPanel')
    expect(today).toContain('crumb-stop-state')
  })

  it('keeps compact wordbook cards free of technical English metadata', () => {
    const wrapper = mount(WordbookShelfCard, {
      props: {
        book: book(),
        statusLabel: '可用',
        statusDescription: '120 个词条',
        formattedDate: '2026/10/22',
        canActivate: false,
        canExport: true,
        canDelete: true,
        activating: false,
        compact: true,
      },
    })

    expect(wrapper.find('.wordbook-description').exists()).toBe(false)
    expect(wrapper.find('.wordbook-card-meta').exists()).toBe(false)
    expect(wrapper.get('.wordbook-entry-count').text()).toContain('120 词条')
  })

  it('shows all three memory styles with enabled and disabled states', () => {
    const memory = source('../views/MemoryPracticeView.vue')
    expect(memory).toContain('`memory-action-card--${module}`')
    expect(memory).toContain('memory-action-status')
    expect(memory).toContain(':disabled="!activeModules.includes(module)"')
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

  it('adds an actionable next step and status legend to the challenge map', () => {
    const challenge = source('../views/ChallengeView.vue')
    expect(challenge).toContain('challenge-next-step')
    expect(challenge).toContain('challenge-state-legend')
  })
})