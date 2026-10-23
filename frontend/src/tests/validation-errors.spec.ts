import { describe, expect, it } from 'vitest'
import {
  MAX_VALIDATION_ISSUES,
  isValidationPayload,
  parseValidationIssues,
} from '../api/validation-errors'

/**
 * The 422 envelope is `HTTPValidationError` from the already-frozen baseline
 * OpenAPI (`detail: ValidationError[]`, each `{loc,msg,type}`). These tests pin
 * the documented shape only; no T-BE-004 field name is asserted.
 */
describe('server validation issue parsing', () => {
  it('reads location and message from the documented envelope', () => {
    const issues = parseValidationIssues({
      detail: [
        { loc: ['body', 'daily_new_words'], msg: 'Input should be less than or equal to 100', type: 'less_than_equal' },
      ],
    })

    expect(issues).toEqual([
      { path: 'daily_new_words', message: 'Input should be less than or equal to 100', type: 'less_than_equal' },
    ])
  })

  it('strips the request-part segment so the path names the field only', () => {
    const issues = parseValidationIssues({
      detail: [{ loc: ['query', 'limit'], msg: 'Input should be a valid integer', type: 'int_parsing' }],
    })

    expect(issues[0].path).toBe('limit')
  })

  it('keeps nested locations for array members', () => {
    const issues = parseValidationIssues({
      detail: [{ loc: ['body', 'modules', 0, 'enabled'], msg: 'Input should be a valid boolean', type: 'bool' }],
    })

    expect(issues[0].path).toBe('modules.0.enabled')
  })

  it('returns nothing for a plain ErrorResponse payload', () => {
    expect(
      parseValidationIssues({ code: 'ACTIVE_WORDBOOK_REQUIRED', message: '需要激活词书。', request_id: 'r-1' }),
    ).toEqual([])
  })

  it('returns nothing for non-object and nullish payloads', () => {
    expect(parseValidationIssues(null)).toEqual([])
    expect(parseValidationIssues('oops')).toEqual([])
    expect(parseValidationIssues([])).toEqual([])
  })

  it('skips malformed entries instead of failing the whole response', () => {
    const issues = parseValidationIssues({
      detail: [
        { loc: ['body', 'a'], msg: 'ok', type: 'value_error' },
        { loc: ['body', 'b'] },
        { msg: 'no loc either' },
        null,
        'nope',
      ],
    })

    expect(issues.map((issue) => issue.message)).toEqual(['ok', 'no loc either'])
    expect(issues[1].path).toBe('')
  })

  it('caps the reported issues so a broken payload cannot flood the form', () => {
    const detail = Array.from({ length: 50 }, (_, index) => ({
      loc: ['body', `field_${index}`],
      msg: `error ${index}`,
      type: 'value_error',
    }))

    expect(parseValidationIssues({ detail })).toHaveLength(MAX_VALIDATION_ISSUES)
  })

  it('recognises the documented envelope only', () => {
    expect(isValidationPayload({ detail: [] })).toBe(true)
    expect(isValidationPayload({ code: 'X', message: 'y', request_id: 'z' })).toBe(false)
    expect(isValidationPayload(undefined)).toBe(false)
  })
})
