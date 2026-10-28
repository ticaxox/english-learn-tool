/// <reference types="node" />
import { mount } from '@vue/test-utils'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { describe, expect, it } from 'vitest'
import WhiskerCrumbMark from '../components/WhiskerCrumbMark.vue'

function source(relativePath: string): string {
  return readFileSync(fileURLToPath(new URL(relativePath, import.meta.url)), 'utf8')
}

const theme = source('../cookie-theme.css')
const main = source('../main.ts')
const shell = source('../components/AppShell.vue')

describe('Whisker Crumb theme contract', () => {
  it('publishes the full biscuit, cocoa, jam and British-ink token set', () => {
    expect(theme).toContain('--cookie-50: #fff8e9')
    expect(theme).toContain('--cookie-100: #f7e7c6')
    expect(theme).toContain('--cocoa-900: #2b1c17')
    expect(theme).toContain('--jam-action: #a8454c')
    expect(theme).toContain('--butter-400: #f3c85b')
    expect(theme).toContain('--pistachio-500: #6f9365')
    expect(theme).toContain('--ink-blue: #2e4766')
    expect(theme).toContain('--font-display: Georgia')
    expect(theme).toContain('--font-body: "Trebuchet MS"')
  })

  it('loads after the original base stylesheet', () => {
    expect(main.indexOf("import './style.css'")).toBeGreaterThanOrEqual(0)
    expect(main.indexOf("import './cookie-theme.css'")).toBeGreaterThan(main.indexOf("import './style.css'"))
  })

  it('covers the member journeys, administrator surfaces and state panels', () => {
    for (const selector of [
      '.today-page',
      '.wordbooks-page',
      '.memory-page',
      '.practice-page',
      '.coach-page',
      '.challenge-page',
      '.notifications-page',
      '.dashboard-page',
      '.ai-admin-page',
      '.admin-users',
      '.notification-state',
      '.empty-state',
      '.dialog-card',
    ]) {
      expect(theme).toContain(selector)
    }
  })

  it('keeps keyboard focus and reduced motion explicit', () => {
    expect(theme).toContain('outline: 3px solid var(--ink-blue)')
    expect(theme).toContain('box-shadow: 0 0 0 6px var(--cookie-50) !important')
    expect(theme).toContain('@media (prefers-reduced-motion: reduce)')
  })

  it('does not introduce external fonts, imagery or CDN requests', () => {
    expect(theme).not.toMatch(/@import|fonts\.googleapis|fonts\.gstatic|https?:\/\//i)
    expect(theme).not.toMatch(/url\(['"]?https?:/i)
  })

  it('keeps one personal application shell without administrator navigation', () => {
    expect(shell).toContain('<MemberShell')
    expect(shell).not.toContain(':is-admin="auth.isAdmin"')
    expect(shell).not.toContain('app-shell--admin')
    expect(shell).not.toContain('WhiskerCrumbMark')
  })

  it('renders an abstract hat, eyes, moustache and bow without a human figure', () => {
    const wrapper = mount(WhiskerCrumbMark, { props: { size: 'hero' } })
    expect(wrapper.find('svg').exists()).toBe(true)
    expect(wrapper.classes()).toContain('whisker-crumb-mark')
    expect(wrapper.classes()).toContain('whisker-crumb-mark--hero')
    expect(wrapper.html()).toContain('whisker-crumb-mark__hat')
    expect(wrapper.html()).toContain('whisker-crumb-mark__eye')
    expect(wrapper.html()).toContain('whisker-crumb-mark__moustache')
    expect(wrapper.html()).toContain('whisker-crumb-mark__bow')
    expect(wrapper.attributes('aria-hidden')).toBe('true')
  })
})
