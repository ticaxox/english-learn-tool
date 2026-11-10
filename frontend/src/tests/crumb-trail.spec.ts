import { readFileSync } from 'node:fs'
import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import WordbookShelfCard from '../components/WordbookShelfCard.vue'
import type { Wordbook } from '../api/wordbooks'

function source(path: string): string {
  return readFileSync(new URL(path, import.meta.url), 'utf8')
}

const book: Wordbook = {
  id: 'crumb-book-1',
  name: 'Campus English',
  description: 'Theme: campus. Source: self-authored.',
  visibility: 'organization',
  status: 'ready',
  version: '1',
  entry_count: 88,
  is_active: true,
  owner_id: null,
  created_by: null,
  created_at: '2026-10-20T10:00:00Z',
  updated_at: '2026-10-22T10:00:00Z',
}

describe('T-FE-018 CrumbTrail IP depth', () => {
  it('renames the member brand and gives Crumbo one reusable mark', () => {
    const shell = source('../components/MemberShell.vue')
    expect(shell).toContain('CrumbTrail')
    expect(shell).toContain('CrumboMark')
    // The mascot is the drawn character (day/night), not a second vector sketch.
    expect(source('../components/CrumboMark.vue')).toContain('illustration.crumbo')
  })

  it('uses a crumb trail, not the old generic Today workbench', () => {
    const today = source('../views/TodayView.vue')
    expect(today).toContain('crumb-today')
    expect(today).toContain('crumb-trail-board')
    expect(today).toContain('today-task-sentence')
    expect(today).toContain('crumb-primary-action')
    expect(today).toContain('CrumboMark')
    expect(today).not.toContain('today-workbench')
    expect(today).not.toContain('member-hero')
  })

  it('turns wordbooks into CrumbTrail books, not rows', () => {
    const wordbooks = source('../views/WordbooksView.vue')
    expect(wordbooks).toContain('crumb-bookshelf')
    expect(wordbooks).toContain('crumb-shelf-header')
    expect(wordbooks).toContain('crumb-current-book')
    // The card is the book itself: no row arrow and no action strip.
    expect(source('../components/WordbookShelfCard.vue')).not.toContain('wordbook-row-arrow')
  })

  it('shows a wordbook as a bare cover carrying only its name', async () => {
    const wrapper = mount(WordbookShelfCard, { props: { book } })

    // No letter, no badges, no body: the cover and the name are the card.
    expect(wrapper.find('.wordbook-card-badges').exists()).toBe(false)
    expect(wrapper.find('.wordbook-cover-letter').exists()).toBe(false)
    expect(wrapper.find('.wordbook-card-body').exists()).toBe(false)
    expect(wrapper.get('.wordbook-cover__name').text()).toBe('Campus English')

    await wrapper.get('.wordbook-card').trigger('click')
    expect(wrapper.emitted('detail')).toHaveLength(1)

    await wrapper.setProps({ book: { ...book, name: 'Harbor Reader' } })
    expect(wrapper.get('.wordbook-cover__name').text()).toBe('Harbor Reader')
  })

  it('marks the wordbook in use with a bookmark, not a label', () => {
    const active = mount(WordbookShelfCard, { props: { book } })
    const idle = mount(WordbookShelfCard, { props: { book: { ...book, is_active: false } } })
    expect(active.find('.wordbook-cover__bookmark').exists()).toBe(true)
    expect(idle.find('.wordbook-cover__bookmark').exists()).toBe(false)
  })

  it('renders the daily map from the DSL instead of a station strip', () => {
    const challenge = source('../views/ChallengeView.vue')
    const map = source('../components/ChallengeDslMap.vue')
    expect(challenge).toContain('crumb-challenge')
    expect(challenge).toContain('ChallengeDslMap')
    expect(map).toContain('challenge-dsl-card')
    expect(map).toContain('challenge-dsl-links')
    expect(map).toContain('is-branch')
  })

  it('defines the CrumbTrail palette and no-legacy structure tokens', () => {
    const css = source('../workspace-reset.css')
    expect(css).toContain('--crumb-forest')
    expect(css).toContain('--crumb-pumpkin')
    expect(css).toContain('--crumb-parchment')
    expect(css).toContain('--crumb-cocoa')
    expect(css).toContain('--crumb-moss')
    expect(css).toContain('.crumb-trail-board')
    expect(css).toContain('.workspace-shell .crumb-wordbooks .wordbook-cover--clay')
    expect(css).toContain('.crumb-challenge .challenge-path::before { display: none; }')
  })
})