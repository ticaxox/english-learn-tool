import { describe, expect, it } from 'vitest'
import {
  ContractPendingError,
  contractCoordinateLabel,
  contractHelpers,
  isContractFrozen,
  parseLearningProfile,
  parseMistakes,
  parseStudyFeedback,
  parseTodayPlan,
  serializeHeartbeat,
  serializeProfileUpdate,
} from '../api/contract-adapter'
import { defaultMemoryConfig, todayIsoDate } from '../lib/learning-validation'
import { ContractError } from '../api/errors'

/**
 * These tests pin the contract gate itself. While T-BE-004 is unfrozen, the
 * adapter must refuse to parse anything: silently accepting an unknown payload
 * is exactly how fabricated data reaches production.
 */
describe('contract adapter gate', () => {
  it('reports an unfrozen contract before the backend publishes OpenAPI', () => {
    expect(isContractFrozen()).toBe(false)
    expect(contractCoordinateLabel()).toContain('未冻结')
    expect(contractCoordinateLabel()).toContain('T-BE-004')
  })

  it('refuses to parse a profile while the contract is unfrozen', () => {
    expect(() => parseLearningProfile({ exam_target: 'CET4' })).toThrow(ContractPendingError)
  })

  it('refuses to parse today, mistakes and feedback while unfrozen', () => {
    expect(() => parseTodayPlan({ new_words: 20 })).toThrow(ContractPendingError)
    expect(() => parseMistakes({ items: [] })).toThrow(ContractPendingError)
    expect(() => parseStudyFeedback({ ok: true })).toThrow(ContractPendingError)
  })

  it('refuses to serialize requests while unfrozen', () => {
    const update = {
      examTarget: 'CET4' as const,
      examDate: null,
      dailyNewWords: 20,
      dailyMinutes: 30,
      memoryConfig: defaultMemoryConfig(),
    }
    expect(() => serializeProfileUpdate(update)).toThrow(ContractPendingError)
    expect(() => serializeHeartbeat({ windowSeconds: 30 })).toThrow(ContractPendingError)
  })

  it('names the specific endpoint in the pending error', () => {
    try {
      parseTodayPlan({})
      throw new Error('expected a ContractPendingError')
    } catch (error) {
      expect(error).toBeInstanceOf(ContractPendingError)
      expect((error as ContractPendingError).endpoint).toBe('/learning/today')
      expect((error as ContractPendingError).message).toContain('/learning/today')
    }
  })

  it('treats a pending contract as a contract error so the UI shows contract guidance', () => {
    const error = new ContractPendingError('/learning/today')
    expect(error).toBeInstanceOf(ContractError)
    expect(error.code).toBe('API_CONTRACT_MISMATCH')
  })

  it('does not leak mock data through the pending path', () => {
    let result: unknown = { suspicious: true }
    try {
      result = parseTodayPlan({})
    } catch {
      result = null
    }
    expect(result).toBeNull()
  })
})

describe('contract helpers', () => {
  const endpoint = '/test'

  it('accepts the documented enum values and rejects others', () => {
    expect(contractHelpers.requireEnum('not_started', contractHelpers.TODAY_STATUSES, endpoint, 'status')).toBe(
      'not_started',
    )
    expect(() => contractHelpers.requireEnum('done', contractHelpers.TODAY_STATUSES, endpoint, 'status')).toThrow(
      ContractError,
    )
  })

  it('rejects non-integer numbers so counts cannot be fractional or NaN', () => {
    expect(contractHelpers.requireInt(3, endpoint, 'count')).toBe(3)
    expect(() => contractHelpers.requireInt(3.5, endpoint, 'count')).toThrow(ContractError)
    expect(() => contractHelpers.requireInt(Number.NaN, endpoint, 'count')).toThrow(ContractError)
  })

  it('rejects arrays where an object is required', () => {
    expect(() => contractHelpers.requireRecord([], endpoint, 'body')).toThrow(ContractError)
    expect(() => contractHelpers.requireRecord(null, endpoint, 'body')).toThrow(ContractError)
  })

  it('normalises optional strings to null rather than undefined', () => {
    expect(contractHelpers.optionalString(undefined, endpoint, 'x')).toBeNull()
    expect(() => contractHelpers.optionalString(3, endpoint, 'x')).toThrow(ContractError)
  })

  it('accepts only the published exam targets', () => {
    expect(contractHelpers.EXAM_TARGETS).toEqual(['CET4', 'CET6', 'POSTGRAD', 'IELTS', 'TOEFL'])
  })

  it('keeps the three memory modules in a stable order', () => {
    expect(contractHelpers.MEMORY_MODULES).toEqual(['flashcard', 'choice', 'spelling'])
  })

  it('publishes the three spelling blank strategies', () => {
    expect(contractHelpers.BLANK_TYPES).toEqual(['full', 'partial', 'first_letter'])
  })
})

describe('date helper', () => {
  it('formats the local calendar date without timezone drift', () => {
    expect(todayIsoDate(new Date(2026, 9, 23, 23, 30))).toBe('2026-10-23')
    expect(todayIsoDate(new Date(2026, 0, 1, 0, 5))).toBe('2026-01-01')
  })
})
