/**
 * Display-only session clock. Counts up by default, counts down when the
 * session was opened with a `timer` limit. It never measures study time — the
 * heartbeat remains the only source for that.
 */
import { computed, onBeforeUnmount, ref } from 'vue'

export function useSessionTimer() {
  const startedAt = ref<number | null>(null)
  const limitMinutes = ref<number | null>(null)
  const now = ref(Date.now())
  let frame: number | null = null
  let lastSecond = -1

  function stop(): void {
    if (frame !== null) {
      cancelAnimationFrame(frame)
      frame = null
    }
  }

  function tick(): void {
    const second = Math.floor(Date.now() / 1000)
    if (second !== lastSecond) {
      lastSecond = second
      now.value = Date.now()
    }
    frame = requestAnimationFrame(tick)
  }

  function start(limit: number | null): void {
    stop()
    startedAt.value = Date.now()
    limitMinutes.value = limit
    now.value = Date.now()
    lastSecond = Math.floor(Date.now() / 1000)
    if (typeof requestAnimationFrame === 'function') frame = requestAnimationFrame(tick)
  }

  function reset(): void {
    stop()
    startedAt.value = null
    limitMinutes.value = null
  }

  const running = computed(() => startedAt.value !== null)
  const elapsedSeconds = computed(() => (
    startedAt.value === null ? 0 : Math.max(0, Math.floor((now.value - startedAt.value) / 1000))
  ))
  const remainingSeconds = computed(() => (
    limitMinutes.value === null ? null : Math.max(0, limitMinutes.value * 60 - elapsedSeconds.value)
  ))
  const label = computed(() => {
    const total = remainingSeconds.value ?? elapsedSeconds.value
    const minutes = Math.floor(total / 60)
    const seconds = total % 60
    return `${minutes}:${String(seconds).padStart(2, '0')}`
  })
  const expired = computed(() => remainingSeconds.value === 0)

  onBeforeUnmount(stop)

  return { start, stop, reset, running, label, remainingSeconds, expired }
}

/** Reads a `timer` query value (minutes) without trusting malformed input. */
export function timerLimitFromQuery(value: unknown): number | null {
  if (typeof value !== 'string') return null
  const minutes = Number(value)
  return Number.isInteger(minutes) && minutes > 0 && minutes <= 120 ? minutes : null
}
