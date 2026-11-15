<script setup lang="ts">
/**
 * The week as a shape: one spoke per part of speech.
 *
 * A spoke's outer edge is how many words of that kind the active wordbook
 * holds; the filled part is how many the learner actually touched this week.
 * A wide spoke means "you worked a lot of this kind"; a short one means the
 * week leaned elsewhere.
 *
 * The chart is drawn as SVG so it scales with the panel and can be animated
 * by growing the polygon from its centre.
 */
import { computed } from 'vue'
import type { RadarAxis } from '../api/progress'

const props = defineProps<{
  axes: RadarAxis[]
}>()

const SIZE = 260
const CENTRE = SIZE / 2
const RADIUS = 92

/** The spokes, evenly spaced, starting at the top and going clockwise. */
const spokes = computed(() =>
  props.axes.map((axis, index) => {
    const angle = (Math.PI * 2 * index) / props.axes.length - Math.PI / 2
    return {
      ...axis,
      angle,
      // A spoke with no supply in the book cannot show a share of it.
      share: axis.total > 0 ? Math.min(1, axis.studied / axis.total) : 0,
    }
  }),
)

const hasShape = computed(() => spokes.value.some((spoke) => spoke.studied > 0))

const radarLabel = computed(() => {
  const parts = props.axes
    .filter((axis) => axis.studied > 0)
    .map((axis) => `${axis.label} ${axis.studied} 个`)
  return parts.length ? `本周词性分布：${parts.join('，')}` : '本周还没有学习记录'
})

function point(index: number, ratio: number): { x: number; y: number } {
  const angle = (Math.PI * 2 * index) / props.axes.length - Math.PI / 2
  const radius = RADIUS * ratio
  return { x: CENTRE + Math.cos(angle) * radius, y: CENTRE + Math.sin(angle) * radius }
}

function polygonPoints(ratioOf: (index: number) => number): string {
  return spokes.value
    .map((_, index) => {
      const p = point(index, ratioOf(index))
      return `${p.x.toFixed(1)},${p.y.toFixed(1)}`
    })
    .join(' ')
}

/**
 * The filled shape: how much of each kind was studied.
 *
 * A share of 0.02 is still drawn as a visible sliver — a word the learner
 * touched this week should never vanish into the hub.
 */
const studiedShape = computed(() =>
  polygonPoints((index) => {
    const axis = spokes.value[index]
    if (axis.studied <= 0) return 0
    const largest = Math.max(...spokes.value.map((spoke) => spoke.total))
    if (largest <= 0) return 0
    // The fill is the studied count on the book's own scale, so the two
    // shapes are directly comparable; a small count still shows as a sliver.
    return Math.max(0.08, (axis.studied / largest) * 0.94)
  }),
)

/**
 * The outline of the whole book.
 *
 * Each spoke reaches the share of that kind inside the book, so the dashed
 * shape is the book's real mix rather than a flat hexagon: a book heavy on
 * verbs shows a wide verb edge, and the studied shape is read against it.
 */
const supplyShape = computed(() =>
  polygonPoints((index) => {
    const axis = spokes.value[index]
    if (!axis.total) return 0
    const largest = Math.max(...spokes.value.map((spoke) => spoke.total))
    if (largest <= 0) return 0
    return Math.max(0.08, axis.total / largest)
  }),
)

/** A spoke's label, pushed just outside the outer ring. */
function labelAt(index: number): { x: number; y: number; anchor: string } {
  const p = point(index, 1.16)
  const cos = Math.cos((Math.PI * 2 * index) / props.axes.length - Math.PI / 2)
  return {
    x: p.x,
    y: p.y,
    anchor: cos > 0.25 ? 'start' : cos < -0.25 ? 'end' : 'middle',
  }
}
</script>

<template>
  <figure v-if="axes.length" class="word-radar">
    <figcaption class="word-radar__caption">
      <span class="word-radar__title">本周词性分布</span>
      <span class="word-radar__legend">
        <i class="word-radar__key word-radar__key--studied" aria-hidden="true"></i>本周学过
        <i class="word-radar__key word-radar__key--supply" aria-hidden="true"></i>词书总量
      </span>
    </figcaption>

    <svg
      class="word-radar__chart"
      :viewBox="`0 0 ${SIZE} ${SIZE}`"
      role="img"
      :aria-label="radarLabel"
    >
      <!-- the spokes; the two shapes carry the scale on their own -->
      <g class="word-radar__spokes">
        <line
          v-for="(spoke, index) in spokes"
          :key="spoke.key"
          :x1="CENTRE"
          :y1="CENTRE"
          :x2="point(index, 1).x"
          :y2="point(index, 1).y"
        />
      </g>

      <!-- what the book holds, then what was studied -->
      <polygon class="word-radar__supply" :points="supplyShape" />
      <polygon v-if="hasShape" class="word-radar__studied" :points="studiedShape" />

      <g class="word-radar__labels">
        <text
          v-for="(spoke, index) in spokes"
          :key="spoke.key"
          :x="labelAt(index).x"
          :y="labelAt(index).y"
          :text-anchor="labelAt(index).anchor"
        >
          {{ spoke.label }}
        </text>
      </g>

      <circle class="word-radar__hub" :cx="CENTRE" :cy="CENTRE" r="3" />
    </svg>

    <p v-if="!hasShape" class="word-radar__empty">这周还没开始学词。</p>
  </figure>
</template>

<style scoped>
.word-radar {
  margin: 0;
  display: grid;
  gap: 8px;
  justify-items: center;
}

.word-radar__caption {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 12px;
  width: 100%;
}

.word-radar__title {
  font-size: 0.8rem;
  font-weight: 800;
  letter-spacing: 0.04em;
  color: var(--ui-ink);
}

.word-radar__legend {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  font-size: 0.68rem;
  color: var(--ui-muted);
}

.word-radar__key {
  width: 9px;
  height: 9px;
  border-radius: 2px;
  display: inline-block;
}

.word-radar__key--studied { background: var(--g-orange, #ff9600); }
.word-radar__key--supply { background: transparent; border: 1.5px dashed var(--g-gold-edge, #d9a400); }

.word-radar__chart {
  width: 100%;
  max-width: 260px;
  height: auto;
  overflow: visible;
}

.word-radar__spokes line {
  stroke: var(--ui-line, #ecd9bb);
  stroke-width: 1;
}

.word-radar__supply {
  fill: none;
  stroke: var(--g-gold-edge, #d9a400);
  stroke-width: 1.5;
  stroke-dasharray: 4 3;
}

.word-radar__studied {
  fill: color-mix(in oklab, var(--g-orange, #ff9600) 26%, transparent);
  stroke: var(--g-orange, #ff9600);
  stroke-width: 2;
  stroke-linejoin: round;
  transform-origin: 50% 50%;
}

.word-radar__labels text {
  font-size: 10px;
  font-weight: 700;
  fill: var(--ui-muted, #7d6247);
}

.word-radar__hub {
  fill: var(--ui-ink, #35240f);
}

.word-radar__empty {
  margin: 0;
  font-size: 0.75rem;
  color: var(--ui-muted, #7d6247);
}
</style>
