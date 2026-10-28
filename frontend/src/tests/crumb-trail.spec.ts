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
  it('renames the member brand and gives Crumbo a reusable vector mark', () => {
    const shell = source('../components/MemberShell.vue')
    expect(shell).toContain('CrumbTrail')
    expect(shell).toContain('CrumboMark')
    expect(source('../components/CrumboMark.vue')).toContain('<svg')
  })

  it('uses a crumb trail, not the old generic Today workbench', () => {
    const today = source('../views/TodayView.vue')
    expect(today).toContain('crumb-today')
    expect(today).toContain('crumb-trail-board')
    expect(today).toContain('crumb-stop')
    expect(today).toContain('crumb-route-progress')
    expect(today).toContain('crumb-primary-action')
    expect(today).toContain('CrumboMark')
    expect(today).not.toContain('today-workbench')
    expect(today).not.toContain('member-hero')
  })

  it('turns wordbooks into numbered, bitten CrumbTrail covers', () => {
    const wordbooks = source('../views/WordbooksView.vue')
    expect(wordbooks).toContain('crumb-bookshelf')
    expect(wordbooks).toContain('crumb-shelf-header')
    expect(wordbooks).toContain('crumb-current-book')
    expect(source('../components/WordbookShelfCard.vue')).toContain('crumb-book-number')
  })

  it('renders numbered book covers with structural bite marks', async () => {
    const wrapper = mount(WordbookShelfCard, {
      props: {
        book,
        statusLabel: '可用',
        statusDescription: '88 个词条',
        formattedDate: '2026/10/22',
        canActivate: false,
        canExport: true,
        canDelete: true,
        activating: false,
        compact: true,
        sequence: 3,
      },
    })

    expect(wrapper.get('.crumb-book-number').text()).toContain('03')
    expect(wrapper.findAll('.crumb-book-bite')).toHaveLength(3)
    expect(wrapper.get('.wordbook-cover').classes()).toContain('wordbook-cover--clay')
    expect(wrapper.get('.wordbook-cover-letter').text()).toBe('C')
    await wrapper.setProps({ book: { ...book, name: 'Harbor Reader' } })
    expect(wrapper.get('.wordbook-cover-letter').text()).toBe('H')
    await wrapper.setProps({ book: { ...book, name: '  journey workbook' } })
    expect(wrapper.get('.wordbook-cover-letter').text()).toBe('J')
  })

  it('uses a curved CrumbTrail route and castle boss structure', () => {
    const challenge = source('../views/ChallengeView.vue')
    expect(challenge).toContain('crumb-challenge')
    expect(challenge).toContain('crumb-route-svg')
    expect(challenge).toContain('challenge-node--boss')
    expect(challenge).toContain('CrumboMark')
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