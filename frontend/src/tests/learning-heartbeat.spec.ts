import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import {
  HEARTBEAT_INTERVAL_MS,
  HEARTBEAT_WINDOW_SECONDS,
  IDLE_PAUSE_MS,
  useStudyHeartbeat,
} from '../composables/useStudyHeartbeat'

/**
 * Heartbeat rules under test are the ones stated in the product contract:
 * 30s cadence, pause when hidden, pause after 60s idle, fixed 30s window,
 * idempotency key per beat, and failures that never fabricate time.
 *
 * These use a fake clock and a fake sender, so nothing depends on wall time.
 */
describe('study heartbeat', () => {
  let now = 0
  const sent: Array<{ windowSeconds: number; key: string }> = []
  let sender: ((windowSeconds: number, key: string) => Promise<void>) | null = null

  function build(enabled = true) {
    return useStudyHeartbeat({
      enabled: () => enabled,
      now: () => now,
      send: (windowSeconds, key) => {
        sent.push({ windowSeconds, key })
        return sender ? sender(windowSeconds, key) : Promise.resolve()
      },
    })
  }

  beforeEach(() => {
    vi.useFakeTimers()
    now = 0
    sent.length = 0
    sender = null
    Object.defineProperty(document, 'visibilityState', { configurable: true, value: 'visible' })
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('uses the published 30 second cadence and window', () => {
    expect(HEARTBEAT_INTERVAL_MS).toBe(30_000)
    expect(HEARTBEAT_WINDOW_SECONDS).toBe(30)
    expect(IDLE_PAUSE_MS).toBe(60_000)
  })

  it('sends a beat every 30 seconds while active', async () => {
    const heartbeat = build()
    heartbeat.start()

    await vi.advanceTimersByTimeAsync(30_000)
    expect(heartbeat.state.value).toBe('active')
    await vi.advanceTimersByTimeAsync(30_000)

    expect(sent).toHaveLength(2)
    for (const beat of sent) {
      expect(beat.windowSeconds).toBe(HEARTBEAT_WINDOW_SECONDS)
    }
  })

  it('gives every beat its own idempotency key', async () => {
    const heartbeat = build()
    heartbeat.start()

    await vi.advanceTimersByTimeAsync(30_000)
    await vi.advanceTimersByTimeAsync(30_000)

    expect(sent).toHaveLength(2)
    expect(sent[0].key).not.toBe(sent[1].key)
  })

  it('pauses when the tab becomes hidden and resumes when visible again', async () => {
    const heartbeat = build()
    heartbeat.start()

    Object.defineProperty(document, 'visibilityState', { configurable: true, value: 'hidden' })
    document.dispatchEvent(new Event('visibilitychange'))
    expect(heartbeat.state.value).toBe('paused-hidden')

    now = 10_000
    await vi.advanceTimersByTimeAsync(30_000)
    expect(sent).toHaveLength(0)

    Object.defineProperty(document, 'visibilityState', { configurable: true, value: 'visible' })
    heartbeat.markInteraction()
    document.dispatchEvent(new Event('visibilitychange'))
    expect(heartbeat.state.value).toBe('active')

    await vi.advanceTimersByTimeAsync(30_000)
    expect(sent).toHaveLength(1)
  })

  it('pauses after 60 seconds without interaction', async () => {
    const heartbeat = build()
    heartbeat.start()

    now = 60_000
    await vi.advanceTimersByTimeAsync(30_000)

    expect(heartbeat.state.value).toBe('paused-idle')
    expect(sent).toHaveLength(0)
  })

  it('resumes counting after the learner interacts again', async () => {
    const heartbeat = build()
    heartbeat.start()

    now = 60_000
    heartbeat.refreshState()
    expect(heartbeat.state.value).toBe('paused-idle')

    heartbeat.markInteraction()
    expect(heartbeat.state.value).toBe('active')
  })

  it('does not send anything when the page is not a countable surface', async () => {
    const heartbeat = build(false)
    heartbeat.start()

    await vi.advanceTimersByTimeAsync(90_000)

    expect(heartbeat.state.value).toBe('idle')
    expect(sent).toHaveLength(0)
  })

  it('keeps a failed beat visible without blocking later beats', async () => {
    sender = () => Promise.reject(new Error('network down'))
    const heartbeat = build()
    heartbeat.start()

    await vi.advanceTimersByTimeAsync(30_000)
    expect(heartbeat.lastError.value).toBeInstanceOf(Error)

    sender = () => Promise.resolve()
    await vi.advanceTimersByTimeAsync(30_000)
    expect(heartbeat.lastError.value).toBeNull()
    expect(sent).toHaveLength(2)
  })

  it('stops the timer and reports stopped after stop', async () => {
    const heartbeat = build()
    heartbeat.start()
    await vi.advanceTimersByTimeAsync(30_000)
    expect(sent).toHaveLength(1)

    heartbeat.stop()
    expect(heartbeat.state.value).toBe('stopped')

    await vi.advanceTimersByTimeAsync(120_000)
    expect(sent).toHaveLength(1)
  })

  it('never persists timing state to browser storage', async () => {
    // Both stores share Storage.prototype, so spy on each concrete instance.
    const localSet = vi.spyOn(window.localStorage, 'setItem')
    const sessionSet = vi.spyOn(window.sessionStorage, 'setItem')
    const localGet = vi.spyOn(window.localStorage, 'getItem')
    const sessionGet = vi.spyOn(window.sessionStorage, 'getItem')

    const heartbeat = build()
    heartbeat.start()
    await vi.advanceTimersByTimeAsync(90_000)
    heartbeat.stop()

    expect(localSet).not.toHaveBeenCalled()
    expect(sessionSet).not.toHaveBeenCalled()
    expect(localGet).not.toHaveBeenCalled()
    expect(sessionGet).not.toHaveBeenCalled()
  })
})
