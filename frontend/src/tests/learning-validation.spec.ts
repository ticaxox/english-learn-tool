import { describe, expect, it } from 'vitest'
import {
  DAILY_MINUTES_MAX,
  DAILY_MINUTES_MIN,
  DAILY_NEW_WORDS_MAX,
  DAILY_NEW_WORDS_MIN,
  defaultMemoryConfig,
} from '../lib/learning-validation'
import {
  enabledModules,
  hasFieldErrors,
  isExamTarget,
  isSpellingBlankType,
  isSpellingComplete,
  normaliseSpellingInput,
  todayIsoDate,
  validateDailyMinutes,
  validateDailyNewWords,
  validateExamDate,
  validateMemoryConfig,
  validateProfile,
} from '../lib/learning-validation'

const TODAY = '2026-10-23'

function baseUpdate() {
  return {
    examTarget: 'CET4' as const,
    examDate: '2026-12-19',
    dailyNewWords: 20,
    dailyMinutes: 30,
    memoryConfig: defaultMemoryConfig(),
    practicePoolTarget: 0,
    challengeGenerationTime: null,
  }
}

describe('profile field ranges', () => {
  it('accepts the documented new-word boundaries and rejects outside them', () => {
    expect(validateDailyNewWords(DAILY_NEW_WORDS_MIN)).toBeNull()
    expect(validateDailyNewWords(DAILY_NEW_WORDS_MAX)).toBeNull()
    expect(validateDailyNewWords(DAILY_NEW_WORDS_MIN - 1)).toContain('5')
    expect(validateDailyNewWords(DAILY_NEW_WORDS_MAX + 1)).toContain('100')
  })

  it('rejects fractional new-word counts', () => {
    expect(validateDailyNewWords(20.5)).toContain('整数')
  })

  it('accepts the documented minute boundaries and rejects outside them', () => {
    expect(validateDailyMinutes(DAILY_MINUTES_MIN)).toBeNull()
    expect(validateDailyMinutes(DAILY_MINUTES_MAX)).toBeNull()
    expect(validateDailyMinutes(DAILY_MINUTES_MIN - 1)).toContain('15')
    expect(validateDailyMinutes(DAILY_MINUTES_MAX + 1)).toContain('180')
  })

  it('allows an empty exam date but rejects past and today dates', () => {
    expect(validateExamDate(null, TODAY)).toBeNull()
    expect(validateExamDate('', TODAY)).toBeNull()
    expect(validateExamDate(TODAY, TODAY)).toContain('晚于今天')
    expect(validateExamDate('2026-10-22', TODAY)).toContain('晚于今天')
    expect(validateExamDate('2026-12-19', TODAY)).toBeNull()
  })

  it('rejects malformed exam dates', () => {
    expect(validateExamDate('19/12/2026', TODAY)).toContain('YYYY-MM-DD')
    expect(validateExamDate('2026-13-45', TODAY)).toContain('YYYY-MM-DD')
  })
})

describe('memory module configuration', () => {
  it('requires at least one enabled module', () => {
    const config = defaultMemoryConfig()
    config.flashcard.enabled = false
    config.choice.enabled = false
    config.spelling.enabled = false
    expect(validateMemoryConfig(config)).toContain('至少需要启用一种')
  })

  it('accepts a configuration with only one module enabled', () => {
    const config = defaultMemoryConfig()
    config.flashcard.enabled = false
    config.choice.enabled = false
    expect(validateMemoryConfig(config)).toBeNull()
    expect(enabledModules(config)).toEqual(['spelling'])
  })

  it('lists enabled modules in a stable order', () => {
    const config = defaultMemoryConfig()
    config.choice.enabled = false
    expect(enabledModules(config)).toEqual(['flashcard', 'spelling'])
  })
})

describe('validateProfile aggregation', () => {
  it('returns no errors for a valid profile', () => {
    expect(hasFieldErrors(validateProfile(baseUpdate(), TODAY))).toBe(false)
  })

  it('collects every invalid field at once instead of failing fast', () => {
    const errors = validateProfile(
      {
        examTarget: 'GRE' as never,
        examDate: '2020-01-01',
        dailyNewWords: 2,
        dailyMinutes: 400,
        memoryConfig: { ...defaultMemoryConfig(), flashcard: { enabled: false, blankType: null }, choice: { enabled: false, blankType: null }, spelling: { enabled: false, blankType: null } },
        practicePoolTarget: 0,
        challengeGenerationTime: null,
      },
      TODAY,
    )
    expect(Object.keys(errors).sort()).toEqual([
      'dailyMinutes',
      'dailyNewWords',
      'examDate',
      'examTarget',
      'memoryConfig',
    ])
  })
})

describe('spelling helpers', () => {
  it('normalises answers to trimmed lowercase without deciding correctness', () => {
    expect(normaliseSpellingInput('  GolDen  ')).toBe('golden')
  })

  it('requires every letter slot to be filled before submitting', () => {
    expect(isSpellingComplete(['g', 'o', 'l'])).toBe(true)
    expect(isSpellingComplete(['g', '', 'l'])).toBe(false)
    expect(isSpellingComplete([])).toBe(false)
  })
})

describe('type guards', () => {
  it('accepts only published exam targets', () => {
    expect(isExamTarget('IELTS')).toBe(true)
    expect(isExamTarget('GRE')).toBe(false)
    expect(isExamTarget(42)).toBe(false)
  })

  it('accepts only published blank strategies', () => {
    expect(isSpellingBlankType('partial')).toBe(true)
    expect(isSpellingBlankType('random')).toBe(false)
  })
})

describe('local calendar date', () => {
  it('is stable at day boundaries without UTC shifting', () => {
    expect(todayIsoDate(new Date(2026, 9, 23, 0, 0))).toBe('2026-10-23')
    expect(todayIsoDate(new Date(2026, 9, 23, 23, 59))).toBe('2026-10-23')
  })
})
