import { describe, expect, it } from 'vitest'
import { isMobilePath, viewportRedirect } from '../lib/surface'

describe('surface split', () => {
  it('sends portrait visits to the mobile tree', () => {
    expect(viewportRedirect('/', true)).toBe('/m/')
    expect(viewportRedirect('/overview', true)).toBe('/m/overview')
    expect(viewportRedirect('/memory/mistakes', true)).toBe('/m/memory/mistakes')
    expect(viewportRedirect('/m/overview', true)).toBeNull()
  })

  it('sends landscape visits back to the desktop tree', () => {
    expect(viewportRedirect('/m/', false)).toBe('/')
    expect(viewportRedirect('/m/overview', false)).toBe('/overview')
    expect(viewportRedirect('/overview', false)).toBeNull()
  })

  it('normalizes the bare mobile prefix', () => {
    expect(viewportRedirect('/m', true)).toBe('/m/')
    expect(viewportRedirect('/m', false)).toBe('/')
  })

  it('recognises only the mobile tree', () => {
    expect(isMobilePath('/m')).toBe(true)
    expect(isMobilePath('/m/memory')).toBe(true)
    expect(isMobilePath('/mobile')).toBe(false)
    expect(isMobilePath('/memory')).toBe(false)
  })
})
