import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'

const paths = {
  shell: '../components/MemberShell.vue',
  today: '../views/TodayView.vue',
  wordbooks: '../views/WordbooksView.vue',
  memory: '../views/MemoryPracticeView.vue',
  practice: '../views/PracticeHubView.vue',
  coach: '../views/CoachView.vue',
  challenge: '../views/ChallengeView.vue',
  css: '../workspace-reset.css',
}

function source(key: keyof typeof paths): string {
  return readFileSync(new URL(paths[key], import.meta.url), 'utf8')
}

describe('T-FE-016 member workspace reset', () => {
  it('uses a restrained application shell with the mascot limited to the coach page', () => {
    const shell = source('shell')
    expect(shell).toContain('workspace-shell')
    expect(shell).toContain('workspace-sidebar')
    expect(shell).toContain('workspace-topbar')
    expect(shell).not.toContain('member-drawer-mascot')
  })

  it('puts real Today tasks and their text guidance before supporting information', () => {
    const today = source('today')
    expect(today).toContain('crumb-trail-board')
    expect(today).toContain('today-task-sentence')
    expect(today).not.toContain('today-primary-action')
    expect(today).toContain('crumb-today-side')
    expect(today).not.toContain('member-hero')
    expect(today).not.toContain('today-workbench')
  })

  it('organizes the work pages around their actual tasks instead of marketing heroes', () => {
    expect(source('wordbooks')).toContain('wordbooks-workspace')
    expect(source('wordbooks')).not.toContain('member-page-heading')
    expect(source('memory')).toContain('memory-workbench')
    expect(source('memory')).not.toContain('memory-hero')
    // The exercise types are books on a shelf now; the settings for one open
    // in a dialog, so the page itself is the shelf plus the task list.
    expect(source('practice')).toContain('PracticeShelf')
    expect(source('practice')).toContain('practice-config-dialog')
    expect(source('practice')).toContain('PracticeTaskList')
    expect(source('practice')).not.toContain('practice-room-mascot')
    expect(source('coach')).toContain('coach-workspace')
    expect(source('challenge')).toContain('challenge-game-stage')
  })

  it('defines flat, task-first workspace styling without decorative display type', () => {
    const css = source('css')
    expect(css).toContain('--workspace-canvas')
    expect(css).toContain('--workspace-accent')
    expect(css).toContain('.workspace-shell')
    expect(css).toContain('.crumb-trail-board')
    expect(css).toContain('@media (max-width: 1024px)')
    expect(css).not.toContain('Georgia')
  })
})