/**
 * One place for the game-feel motion.
 *
 * Every helper no-ops when the learner asked for reduced motion, so the UI stays
 * usable without animation instead of degrading into flicker.
 */
import gsap from 'gsap'
import { DrawSVGPlugin } from 'gsap/DrawSVGPlugin'
import { prefersReducedMotion } from '../lib/motion-preference'

gsap.registerPlugin(DrawSVGPlugin)

export { gsap }

export function motionAllowed(): boolean {
  return !prefersReducedMotion()
}

/** Staggered entrance for a list of elements. */
export function popIn(
  targets: Element[] | Element | null,
  options: { y?: number; delay?: number; stagger?: number; scale?: number } = {},
): gsap.core.Tween | null {
  if (!targets || !motionAllowed()) return null
  const list = Array.isArray(targets) ? targets : [targets]
  if (list.length === 0) return null
  return gsap.from(list, {
    y: options.y ?? 18,
    scale: options.scale ?? 0.96,
    opacity: 0,
    duration: 0.45,
    ease: 'back.out(1.4)',
    stagger: options.stagger ?? 0.06,
    delay: options.delay ?? 0,
    clearProps: 'transform,opacity',
  })
}

/** Count a number up, used for XP and scores. */
export function countUp(
  element: HTMLElement | null,
  to: number,
  options: { duration?: number; suffix?: string } = {},
): void {
  if (!element) return
  if (!motionAllowed()) {
    element.textContent = `${Math.round(to)}${options.suffix ?? ''}`
    return
  }
  const state = { value: 0 }
  gsap.to(state, {
    value: to,
    duration: options.duration ?? 0.9,
    ease: 'power2.out',
    onUpdate: () => {
      element.textContent = `${Math.round(state.value)}${options.suffix ?? ''}`
    },
  })
}

/** A quick squash-and-pop on a value change. */
export function bump(targets: Element | Element[] | null, scale = 1.18): void {
  if (!targets || !motionAllowed()) return
  gsap.fromTo(
    targets,
    { scale },
    { scale: 1, duration: 0.5, ease: 'elastic.out(1, 0.4)', clearProps: 'transform' },
  )
}

/** Shake for a wrong answer. */
export function shake(target: Element | null): void {
  if (!target || !motionAllowed()) return
  gsap.fromTo(
    target,
    { x: 0 },
    { x: 0, duration: 0.45, ease: 'power2.out', clearProps: 'transform',
      keyframes: { x: [-8, 8, -5, 5, 0] } },
  )
}

/** Draw every SVG path inside the container, left to right. */
export function drawPaths(container: Element | null, options: { delay?: number } = {}): void {
  if (!container || !motionAllowed()) return
  const paths = Array.from(container.querySelectorAll('path'))
  if (paths.length === 0) return
  gsap.fromTo(
    paths,
    { drawSVG: '0%' },
    {
      drawSVG: '100%',
      duration: 1.1,
      ease: 'power2.inOut',
      stagger: 0.05,
      delay: options.delay ?? 0.15,
    },
  )
}

/**
 * Reward burst: a handful of crumbs fly out from an element.
 * Uses DOM nodes rather than canvas so it inherits the theme colours.
 */
export function crumbBurst(anchor: Element | null, count = 14): void {
  if (!anchor || !motionAllowed()) return
  const rect = anchor.getBoundingClientRect()
  if (rect.width === 0) return
  const layer = document.createElement('div')
  layer.className = 'game-burst-layer'
  document.body.appendChild(layer)
  for (let index = 0; index < count; index += 1) {
    const dot = document.createElement('span')
    dot.className = 'game-burst-dot'
    dot.style.left = `${rect.left + rect.width / 2}px`
    dot.style.top = `${rect.top + rect.height / 2}px`
    layer.appendChild(dot)
    const angle = (Math.PI * 2 * index) / count + Math.random() * 0.5
    const distance = 70 + Math.random() * 90
    gsap.to(dot, {
      x: Math.cos(angle) * distance,
      y: Math.sin(angle) * distance - 30,
      opacity: 0,
      scale: 0.4,
      duration: 0.9 + Math.random() * 0.4,
      ease: 'power2.out',
      onComplete: () => dot.remove(),
    })
  }
  window.setTimeout(() => layer.remove(), 1600)
}

/** Idle bob for Hob, so the mascot reads as alive. */
export function breathe(target: Element | null): gsap.core.Timeline | null {
  if (!target || !motionAllowed()) return null
  const timeline = gsap.timeline({ repeat: -1, yoyo: true })
  timeline.to(target, { y: -4, duration: 1.6, ease: 'sine.inOut' })
  return timeline
}
