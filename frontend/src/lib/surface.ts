/**
 * Desktop and mobile are the same build under two URL trees:
 *   /…    desktop surface
 *   /m/…  mobile surface
 *
 * The surface follows the screen orientation, so rotating a phone or a
 * portrait desktop window moves the visitor across. Both trees share the API
 * and the router; they exist so layouts can diverge per surface later.
 */

export const MOBILE_PREFIX = '/m'
export const MOBILE_BASE = '/m/'

export function isMobilePath(pathname: string): boolean {
  return pathname === MOBILE_PREFIX || pathname.startsWith(`${MOBILE_PREFIX}/`)
}

/** Where the current URL should move to for the given orientation, if anywhere. */
export function viewportRedirect(pathname: string, portrait: boolean): string | null {
  const mobile = isMobilePath(pathname)
  if (portrait && !mobile) return pathname === '/' ? MOBILE_BASE : `${MOBILE_PREFIX}${pathname}`
  if (!portrait && mobile) return pathname.replace(new RegExp(`^${MOBILE_PREFIX}`), '') || '/'
  if (portrait && pathname === MOBILE_PREFIX) return MOBILE_BASE
  return null
}

export function isPortrait(): boolean {
  if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') return false
  return window.matchMedia('(orientation: portrait)').matches
}

export function isMobileSurface(): boolean {
  return typeof window !== 'undefined' && isMobilePath(window.location.pathname)
}

/** Route history base for the surface the page was loaded on. */
export function surfaceBase(): string {
  return isMobileSurface() ? MOBILE_BASE : '/'
}

export function redirectForViewport(): void {
  if (typeof window === 'undefined') return
  const target = viewportRedirect(window.location.pathname, isPortrait())
  if (target) window.location.replace(`${target}${window.location.search}${window.location.hash}`)
}

/** Tag the document so surface-specific layout rules can target it later. */
export function markSurface(): void {
  if (typeof document === 'undefined') return
  document.documentElement.dataset.surface = isMobileSurface() ? 'mobile' : 'desktop'
}

export function watchOrientation(): void {
  if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') return
  window.matchMedia('(orientation: portrait)').addEventListener('change', redirectForViewport)
}
