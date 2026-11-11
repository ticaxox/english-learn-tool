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
  /** A painted charge drawn instead of the line glyph. */
  sticker?: string | null
  variant?: 'seal' | 'wax' | 'iron' | 'heraldry' | 'sticker'
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

/**
 * Iron, abstracted: a hexagon of flat plates, a rule line inset from the
 * edge, and three chevrons in the middle. Nothing here is a photograph of
 * metal — it is a symbol drawn with the same bold rules as the rest of the art.
 */
const iron = computed(() => {
  const points: string[] = []
  for (let i = 0; i < 6; i += 1) {
    const angle = (Math.PI * 2 * i) / 6 - Math.PI / 2
    points.push(`${(50 + Math.cos(angle) * 46).toFixed(2)} ${(50 + Math.sin(angle) * 46).toFixed(2)}`)
  }
  return `M ${points.join(' L ')} Z`
})

/** The inset rule line, the same hexagon one step in. */
const ironRule = computed(() => {
  const points: string[] = []
  for (let i = 0; i < 6; i += 1) {
    const angle = (Math.PI * 2 * i) / 6 - Math.PI / 2
    points.push(`${(50 + Math.cos(angle) * 39).toFixed(2)} ${(50 + Math.sin(angle) * 39).toFixed(2)}`)
  }
  return `M ${points.join(' L ')} Z`
})

/** Three chevrons, stacked, the way a trail marker counts stops. */
const chevrons = computed(() =>
  [0, 1, 2].map((index) => {
    const y = 38 + index * 11
    return `M 39 ${y} L 50 ${y + 7} L 61 ${y}`
  }),
)

/** A heraldic shield: flat top, straight sides, a point at the bottom. */
const heraldry = computed(() => {
  const w = 34
  const top = 20
  const shoulder = 30
  const bottom = 84
  return `M ${50 - w} ${top} L ${50 + w} ${top} L ${50 + w} ${shoulder} L 50 ${bottom} L ${50 - w} ${shoulder} Z`
})

/** A chevron band across the shield — the plainest heraldic charge. */
const heraldryBand = computed(() => {
  const y = 46
  return `M 24 ${y} L 50 ${y + 13} L 76 ${y} L 76 ${y + 9} L 50 ${y + 22} L 24 ${y + 9} Z`
})

const shape = computed(() => {
  if (props.variant === 'wax') return wax.value
  if (props.variant === 'iron') return iron.value
  if (props.variant === 'heraldry') return heraldry.value
  return seal.value
})
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
    <circle v-if="variant !== 'iron'" class="emblem__plate" cx="50" cy="50" r="33" />
    <path v-else-if="variant === 'iron'" class="emblem__rule" :d="ironRule" />
    <path v-else class="emblem__band" :d="heraldryBand" />
    <path
      v-for="(chevron, index) in variant === 'iron' ? chevrons : []"
      :key="index"
      class="emblem__chevron"
      :d="chevron"
    />
    <image
      v-if="sticker"
      class="emblem__sticker"
      :href="sticker"
      x="20"
      y="20"
      width="60"
      height="60"
      preserveAspectRatio="xMidYMid meet"
    />
    <g v-else class="emblem__glyph" transform="translate(50 50) scale(1.72) translate(-12 -12)">
      <path v-for="(d, index) in glyph" :key="index" :d="d" />
    </g>
    <path v-if="variant === 'wax' && earned" class="emblem__drip" d="M 62 87 q 3 8 -1 11 q -4 -3 -1 -11 Z" />
  </svg>
</template>
