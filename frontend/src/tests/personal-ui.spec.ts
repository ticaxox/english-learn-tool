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
    expect(today).toContain('crumb-task-row')
    expect(css).toContain('overflow-wrap: normal')
    expect(css).toContain('word-break: normal')
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

  it('keeps mobile actions at least 44px and leaves no floating coach window behind', () => {
    const css = source('../personal-ui.css')
    expect(css).toContain('.personal-workspace.workspace-shell .button-small')
    expect(css).toContain('min-height: 44px')
    // The floating coach is gone, so its window and its button have no styles.
    expect(css).not.toContain('.ia-coach-panel-body')
    expect(css).not.toContain('.workspace-coach-button')
  })

  it('keeps choice radios at their intrinsic size instead of stretching to the row', () => {
    const css = source('../personal-ui.css')
    expect(css).toContain('.personal-workspace input:not([type="checkbox"]):not([type="radio"])')
    expect(css).toContain('.personal-workspace .choice-option input[type="radio"]')
    expect(css).toContain('.personal-workspace .practice-option input[type="radio"]')
  })

  it('gives the AI provider page a desktop master-detail layout', () => {
    const css = source('../personal-ui.css')
    expect(css).toContain('.personal-workspace .personal-ai-main')
    expect(css).toContain('.personal-workspace .personal-ai-aside')
    expect(css).toContain('grid-template-columns: minmax(0, 7fr) minmax(0, 9fr)')
    expect(css).toContain('.personal-workspace .personal-ai-empty { max-width: none; }')
  })

  it('leaves the workspace full width now that no coach panel docks beside it', () => {
    const css = source('../game-ui.css')
    // The docking layout belonged to the floating window; with it gone the
    // workspace keeps the whole row and no margin is reserved for a panel.
    expect(css).not.toContain('.personal-workspace.is-coach-open .workspace-main')
    expect(css).not.toContain('margin-right: 460px')
  })

  it('lets wordbook dialogs use their designed desktop width', () => {
    const css = source('../wordbooks.css')
    expect(css).toContain('.dialog-card.wordbook-import-dialog')
    expect(css).toContain('.dialog-card.wordbook-detail-dialog')
    expect(css).toContain('calc(100vw - 3rem)')
  })
})
