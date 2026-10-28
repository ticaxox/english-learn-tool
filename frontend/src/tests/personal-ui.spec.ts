import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'

function source(relativePath: string): string {
  return readFileSync(new URL(relativePath, import.meta.url), 'utf8')
}

describe('T-FE-020 personal UI system', () => {
  it('publishes one responsive shell, spacing scale and control size', () => {
    const css = source('../personal-ui.css')
    for (const token of [
      '--ui-space-1: 4px',
      '--ui-space-2: 8px',
      '--ui-space-3: 12px',
      '--ui-space-4: 16px',
      '--ui-space-5: 24px',
      '--ui-space-6: 32px',
      '--ui-control: 44px',
    ]) {
      expect(css).toContain(token)
    }
    expect(css).toContain('@media (max-width: 860px)')
    expect(css).toContain('@media (max-width: 620px)')
    expect(css).toContain('padding-bottom: calc(88px + env(safe-area-inset-bottom))')
  })

  it('keeps mobile Today copy horizontal and exposes the primary action above the fold', () => {
    const today = source('../views/TodayView.vue')
    const css = source('../personal-ui.css')
    expect(today).toContain('crumb-today-mobile-cta')
    expect(css).toContain('overflow-wrap: normal')
    expect(css).toContain('word-break: normal')
    expect(css).toContain('.personal-workspace .crumb-trail-footer .crumb-primary-action { display: none; }')
  })

  it('uses one settings title and a grouped field layout', () => {
    const css = source('../personal-ui.css')
    expect(css).toContain('.personal-workspace .ia-settings-hub .settings-hero { display: none; }')
    expect(css).toContain('grid-template-columns: repeat(2, minmax(0, 1fr))')
    expect(css).toContain('.personal-workspace .settings-form fieldset')
  })

  it('keeps technical diagnostics out of the production error surface', () => {
    const error = source('../api/errors.ts')
    const notice = source('../components/ErrorNotice.vue')
    const gate = source('../components/ContractGate.vue')
    expect(error).not.toContain('开发代理地址')
    expect(error).not.toContain('frontend/README.md')
    expect(notice).toContain('查看问题详情')
    expect(gate).toContain('const showDiagnostics = import.meta.env.DEV')
    expect(gate).toContain('<details v-if="showDiagnostics">')
  })

  it('keeps full-width mobile table rows inside the viewport', () => {
    const css = source('../personal-ui.css')
    expect(css).toContain('table-layout: fixed')
    expect(css).toContain('td[data-label="结果"]')
    expect(css).toContain('.personal-workspace .mistake-table thead { display: none; }')
  })
})
