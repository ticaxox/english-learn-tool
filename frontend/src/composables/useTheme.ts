/**
 * Day or night — the whole app runs on one switch.
 *
 * The two looks are two separate paintings, not a filter: every asset ships a
 * day and a night version, and the shell flips its token set. The choice rides
 * in a cookie so a reload keeps it (the product keeps learning state on the
 * server; a look preference has no business there), and a first visit follows
 * the system preference.
 */
import { computed, ref, watch } from 'vue'
import type { Mode } from '../assets/halloween'

const COOKIE = 'crumb_theme'
const YEAR = 60 * 60 * 24 * 365

function readCookie(): Mode | null {
  if (typeof document === 'undefined') return null
  for (const part of document.cookie.split(';')) {
    const [name, ...rest] = part.trim().split('=')
    if (name !== COOKIE) continue
    const value = rest.join('=')
    return value === 'night' || value === 'day' ? value : null
  }
  return null
}

function systemPrefersNight(): boolean {
  if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') return false
  try {
    return window.matchMedia('(prefers-color-scheme: dark)').matches
  } catch {
    return false
  }
}

/** The live mode. Module-level, so every component reads the same value. */
export const themeMode = ref<Mode>(readCookie() ?? (systemPrefersNight() ? 'night' : 'day'))

export const isNight = computed(() => themeMode.value === 'night')

/** Stamp the mode on the document so plain CSS can reach it. */
function paint(mode: Mode): void {
  if (typeof document === 'undefined') return
  document.documentElement.dataset.theme = mode
}

paint(themeMode.value)

watch(themeMode, (mode) => {
  paint(mode)
  if (typeof document === 'undefined') return
  const secure = typeof location !== 'undefined' && location.protocol === 'https:' ? '; Secure' : ''
  document.cookie = `${COOKIE}=${mode}; Path=/; Max-Age=${YEAR}; SameSite=Lax${secure}`
})

export function setTheme(mode: Mode): void {
  themeMode.value = mode
}

export function toggleTheme(): void {
  themeMode.value = themeMode.value === 'day' ? 'night' : 'day'
}
