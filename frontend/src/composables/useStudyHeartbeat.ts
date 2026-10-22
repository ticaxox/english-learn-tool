/**
 * Active-time heartbeat driver (T-FE-004).
 *
 * Rules implemented here are the ones the product contract states for the
 * client: one heartbeat every 30s, pause when the tab is hidden, pause after
 * 60s without user interaction, and never invent offline time.
 *
 * What this composable deliberately does NOT do:
 *  - it never accumulates a local "study time" total; each tick reports a
 *    fixed activity window and lets the server decide what to count;
 *  - it never persists anything to localStorage/sessionStorage;
 *  - it never retries a failed beat with a fabricated replacement window.
 */
import { onUnmounted, readonly, ref } from 'vue'
import { sendHeartbeat } from '../api/learning'
import { isContractFrozen } from '../api/contract-adapter'

export const HEARTBEAT_INTERVAL_MS = 30_000
export const IDLE_PAUSE_MS = 60_000
/** Server counts at most 30 seconds per accepted heartbeat. */
export const HEARTBEAT_WINDOW_SECONDS = 30

export type HeartbeatState = 'idle' | 'active' | 'paused-hidden' | 'paused-idle' | 'stopped'

export interface HeartbeatOptions {
  /** Only enable on pages that may count toward study time. */
  enabled: () => boolean
  /** Injectable for tests. */
  now?: () => number
  /** Injectable for tests; defaults to the real API call. */
  send?: (windowSeconds: number, idempotencyKey: string) => Promise<void>
}

function newIdempotencyKey(): string {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID()
  }
  return `hb-${Date.now()}-${Math.random().toString(16).slice(2)}`
}

export function useStudyHeartbeat(options: HeartbeatOptions) {
  const state = ref<HeartbeatState>('idle')
  const lastError = ref<unknown>(null)
  const sentCount = ref(0)

  const now = options.now ?? (() => Date.now())
  const send = options.send ?? ((windowSeconds: number, key: string) => sendHeartbeat({ windowSeconds }, key))

  let intervalId: number | null = null
  let lastInteractionAt = now()
  let running = false

  function clearTimer(): void {
    if (intervalId !== null) {
      window.clearInterval(intervalId)
      intervalId = null
    }
  }

  function isDocumentHidden(): boolean {
    return typeof document !== 'undefined' && document.visibilityState === 'hidden'
  }

  /** Re-evaluate pause conditions; called on ticks and on interaction. */
  function refreshState(): void {
    if (!running) {
      state.value = 'stopped'
      return
    }
    if (!options.enabled()) {
      state.value = 'idle'
      return
    }
    if (isDocumentHidden()) {
      state.value = 'paused-hidden'
      return
    }
    if (now() - lastInteractionAt >= IDLE_PAUSE_MS) {
      state.value = 'paused-idle'
      return
    }
    state.value = 'active'
  }

  function markInteraction(): void {
    lastInteractionAt = now()
    if (running && state.value === 'paused-idle') {
      refreshState()
    }
  }

  async function tick(): Promise<void> {
    refreshState()
    if (state.value !== 'active') {
      return
    }

    try {
      await send(HEARTBEAT_WINDOW_SECONDS, newIdempotencyKey())
      sentCount.value += 1
      lastError.value = null
    } catch (error) {
      // Surfaced to the page, but never blocks card work and never fabricates
      // a replacement window on retry.
      lastError.value = error
    }
  }

  function handleVisibilityChange(): void {
    refreshState()
  }

  function start(): void {
    if (running) {
      return
    }
    running = true
    lastInteractionAt = now()
    refreshState()
    intervalId = window.setInterval(() => {
      void tick()
    }, HEARTBEAT_INTERVAL_MS)
    document?.addEventListener('visibilitychange', handleVisibilityChange)
  }

  function stop(): void {
    running = false
    clearTimer()
    document?.removeEventListener('visibilitychange', handleVisibilityChange)
    state.value = 'stopped'
  }

  onUnmounted(stop)

  return {
    state: readonly(state),
    lastError: readonly(lastError),
    sentCount: readonly(sentCount),
    /** True when beats can currently count toward study time. */
    counting: () => state.value === 'active' && isContractFrozen(),
    start,
    stop,
    markInteraction,
    refreshState,
  }
}
