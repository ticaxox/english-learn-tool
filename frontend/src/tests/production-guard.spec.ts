import { describe, expect, it } from 'vitest'

/**
 * Static guard for the T-FE-004 prohibitions that no component test can catch:
 * a `localStorage` write buried in a view, a fabricated countdown, or a mock
 * fixture that slipped into the production bundle.
 *
 * Sources are pulled through Vite's `?raw` glob rather than `node:fs`, so the
 * guard runs inside the same browser-typed project as the app and needs no
 * node types in the build.
 */
const rawSources = import.meta.glob('/src/**/*.{ts,vue}', {
  query: '?raw',
  import: 'default',
  eager: true,
}) as Record<string, string>

/** Test doubles stay legal; shipped code must not acquire a second truth. */
const files = Object.entries(rawSources).filter(([path]) => !path.startsWith('/src/tests/'))

/** Strip comments so documentation may discuss the banned APIs by name. */
function code(text: string): string {
  return text
    .replace(/\/\*[\s\S]*?\*\//g, '')
    .replace(/(^|[^:])\/\/.*$/gm, '$1')
    .replace(/<!--[\s\S]*?-->/g, '')
}

function offenders(pattern: RegExp): string[] {
  return files
    .filter(([, text]) => pattern.test(code(text)))
    .map(([path]) => path.replace('/src/', ''))
}

describe('production code prohibitions', () => {
  it('scans a non-trivial number of source files', () => {
    expect(files.length).toBeGreaterThan(20)
    expect(files.some(([path]) => path.endsWith('useStudyHeartbeat.ts'))).toBe(true)
    expect(files.some(([path]) => path.startsWith('/src/tests/'))).toBe(false)
  })

  it('never uses browser storage for learning state', () => {
    // Matches real access (`localStorage.setItem`, `window.localStorage`), not
    // prose that merely promises the reader there is none.
    //
    // One exception: the day/night preference, which is a display choice and
    // not learning state. It names the file rather than the pattern, so a
    // second storage user still fails this guard.
    const displayPreference = ['composables/useMode.ts']
    const users = offenders(/\b(?:window\.)?(?:local|session)Storage\s*[.[]/)
    expect(users.filter((path) => !displayPreference.includes(path))).toEqual([])
  })

  it('never keeps an answer key or correctness flag in a view model', () => {
    // The anti-leak design makes these type errors; this catches a bypass that
    // hand-builds an object with `as any`.
    expect(offenders(/\b(isCorrect|correctOptionId|answerKey|isRight)\b/)).toEqual([])
  })

  it('never ships a mock adapter or fixture loader', () => {
    expect(offenders(/\b(mockServer|mockApi|fakeFetch|seedData|fixtureData)\b/)).toEqual([])
  })

  it('never derives study minutes from a client-side accumulator', () => {
    // Exactly two timers are legitimate: the learning heartbeat, and the
    // wordbook import preview's expiry countdown (which only displays when a
    // server-issued preview token dies — it never counts study time).
    expect(offenders(/setInterval/)).toEqual([
      'components/WordbookImportDialog.vue',
      'composables/useStudyHeartbeat.ts',
    ])
  })

  it('never advances FSRS or scheduling state on the client', () => {
    const learning = offenders(/\b(stability|difficulty|fsrs|nextDueAt\s*=|intervalDays)\b/i)
    expect(learning.filter((path) => /composables|components|views/.test(path) && !/practice/i.test(path))).toEqual([])
  })
})
