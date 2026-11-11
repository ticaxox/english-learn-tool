import { computed, ref, watch } from 'vue'
import { onMounted } from 'vue'

/**
 * Day and night are two drawings, not a filter.
 *
 * The app owns the switch: `html[data-mode]` carries the mode, and every
 * artwork swaps through it. The operating system's colour scheme is only the
 * initial default — it never overrides a choice the learner made.
 */

export type Mode = 'day' | 'night'

const STORAGE_KEY = 'crumbtrail.mode'

/** Read the stored preference, falling back to the system's colour scheme. */
function initialMode(): Mode {
  if (typeof window === 'undefined') return 'day'
  try {
    const stored = window.localStorage.getItem(STORAGE_KEY)
    if (stored === 'day' || stored === 'night') return stored
  } catch {
    // Private mode or a blocked storage: fall through to the default.
  }
  return window.matchMedia?.('(prefers-color-scheme: dark)').matches ? 'night' : 'day'
}

const mode = ref<Mode>(initialMode())

/** Apply the mode to the document so the CSS and the artwork both follow it. */
function apply(next: Mode): void {
  if (typeof document === 'undefined') return
  document.documentElement.setAttribute('data-mode', next)
}

apply(mode.value)

watch(mode, (next) => {
  apply(next)
  try {
    window.localStorage.setItem(STORAGE_KEY, next)
  } catch {
    // A blocked storage must not break the switch.
  }
})

export function useMode() {
  const isNight = computed(() => mode.value === 'night')

  function toggle(): void {
    mode.value = mode.value === 'day' ? 'night' : 'day'
  }

  function set(next: Mode): void {
    mode.value = next
  }

  return { mode, isNight, toggle, set }
}

/**
 * Cross-fade between the two drawings.
 *
 * The artwork is two separate images per element, stacked; the old one is
 * faded out while the new one fades in. Nothing is tinted — night really is a
 * different picture.
 */
export function useArtSwap() {
  const swapped = ref(false)

  onMounted(() => {
    swapped.value = true
  })

  return { swapped }
}
