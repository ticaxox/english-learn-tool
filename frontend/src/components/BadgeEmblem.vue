<script setup lang="ts">
/**
 * The disc a badge is struck on, in three dies.
 *
 *  - `seal`  the enamel medal the wall shipped with: a scalloped disc.
 *  - `wax`   a wax seal pressed onto the page, with a drip.
 *  - `iron`  a riveted iron plate with a pumpkin-lit rim.
 *
 * The emblem itself is the same drawing in all three; only the chrome changes,
 * so a badge reads as the same achievement whichever die we settle on.
 */
import { computed } from 'vue'

const props = withDefaults(defineProps<{
  glyph: string[]
  accent: string
  earned: boolean
  variant?: 'seal' | 'wax' | 'iron'
}>(), { variant: 'seal' })

/** Scalloped disc: 18 petals, generated so every badge shares one die. */
const seal = computed(() => {
  const petals = 18
  const step = (Math.PI * 2) / petals
  const at = (angle: number, radius: number): string =>
    `${(50 + Math.cos(angle - Math.PI / 2) * radius).toFixed(2)} ${(50 + Math.sin(angle - Math.PI / 2) * radius).toFixed(2)}`
  let d = `M ${at(0, 47.5)}`
  for (let i = 0; i < petals; i += 1) {
    d += ` Q ${at(i * step + step / 2, 40)} ${at((i + 1) * step, 47.5)}`
  }
  return `${d} Z`
})

/** Wax: an uneven blob, smoothed through its vertices so it reads as poured. */
const wax = computed(() => {
  const lobes = 13
  const step = (Math.PI * 2) / lobes
  const radiusAt = (i: number): number => 43.5 + 3.1 * Math.sin(i * 2.3 + 0.7) + 1.6 * Math.cos(i * 1.7)
  const pts = Array.from({ length: lobes }, (_, i) => {
    const angle = i * step - Math.PI / 2
    const r = radiusAt(i)
    return [50 + Math.cos(angle) * r, 50 + Math.sin(angle) * r] as const
  })
  const mid = (a: readonly [number, number], b: readonly [number, number]) =>
    `${(((a[0] + b[0]) / 2).toFixed(2))} ${(((a[1] + b[1]) / 2).toFixed(2))}`
  let d = `M ${mid(pts[lobes - 1], pts[0])}`
  for (let i = 0; i < lobes; i += 1) {
    const point = pts[i]
    const next = pts[(i + 1) % lobes]
    d += ` Q ${point[0].toFixed(2)} ${point[1].toFixed(2)} ${mid(point, next)}`
  }
  return `${d} Z`
})

/** Iron: an octagonal plate, corners cut back. */
const iron = computed(() => {
  const points: string[] = []
  for (let i = 0; i < 8; i += 1) {
    const angle = (Math.PI * 2 * i) / 8 + Math.PI / 8
    points.push(`${(50 + Math.cos(angle) * 45).toFixed(2)} ${(50 + Math.sin(angle) * 45).toFixed(2)}`)
  }
  return `M ${points.join(' L ')} Z`
})

const rivets = computed(() =>
  Array.from({ length: 8 }, (_, i) => {
    const angle = (Math.PI * 2 * i) / 8 + Math.PI / 8
    return { cx: 50 + Math.cos(angle) * 38, cy: 50 + Math.sin(angle) * 38 }
  }),
)

const shape = computed(() => (props.variant === 'wax' ? wax.value : props.variant === 'iron' ? iron.value : seal.value))
</script>

<template>
  <svg
    class="emblem"
    :class="[`emblem--${variant}`, { 'is-earned': earned }]"
    viewBox="0 0 100 100"
    :style="{ '--badge-accent': accent }"
    aria-hidden="true"
  >
    <path class="emblem__disc" :d="shape" />
    <circle class="emblem__plate" cx="50" cy="50" r="33" />
    <circle v-if="variant === 'iron'" class="emblem__rim" cx="50" cy="50" r="42" />
    <circle v-for="(rivet, index) in variant === 'iron' ? rivets : []" :key="index" class="emblem__rivet" :cx="rivet.cx" :cy="rivet.cy" r="2.6" />
    <g class="emblem__glyph" transform="translate(50 50) scale(1.72) translate(-12 -12)">
      <path v-for="(d, index) in glyph" :key="index" :d="d" />
    </g>
    <path v-if="variant === 'wax' && earned" class="emblem__drip" d="M 62 87 q 3 8 -1 11 q -4 -3 -1 -11 Z" />
  </svg>
</template>
