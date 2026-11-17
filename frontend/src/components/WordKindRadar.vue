<script setup lang="ts">
/**
 * The week as a shape: one spoke per part of speech.
 *
 * The outer ring is the active wordbook's own total, so the furthest edge of
 * the chart means "all of this kind, learned". The filled part is how many of
 * them the learner actually touched this week; one shape read against the rim,
 * no second outline to compare against.
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

/** Three fainter rings and the rim: the scale the shape is read against. */
const gridRings = computed(() =>
  [0.25, 0.5, 0.75, 1].map((ratio) => polygonPoints(() => ratio)),
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
    <svg
      class="word-radar__chart"
      :viewBox="`0 0 ${SIZE} ${SIZE}`"
      role="img"
      :aria-label="radarLabel"
    >
      <!-- the rings carry the scale: the rim is the whole wordbook -->
      <g class="word-radar__grid">
        <polygon v-for="(ring, index) in gridRings" :key="index" :points="ring" />
      </g>

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

  </figure>
</template>

<style scoped>
.word-radar {
  margin: 0;
  display: grid;
  gap: 8px;
  justify-items: center;
  height: 100%;
  min-height: 0;
}

/* The radar is as tall as the card it sits in, not a 260px thumbnail. */
.word-radar__chart {
  width: 100%;
  max-width: none;
  height: 100%;
  /* Capped so the radar never becomes the card that sets the row height:
   * 学习足迹 beside it is the taller one. */
  max-height: 280px;
  min-height: 0;
  overflow: visible;
}

.word-radar__grid polygon {
  fill: none;
  stroke: var(--ui-line, #ecd9bb);
  stroke-width: 1;
}

.word-radar__grid polygon:last-child {
  stroke: var(--ui-line-strong, #3b2a1a);
  stroke-opacity: 0.22;
}

.word-radar__spokes line {
  stroke: var(--ui-line, #ecd9bb);
  stroke-width: 1;
}

.word-radar__studied {
  /* 和「学习足迹」的格子、词态条同一盏灯：白天橙，夜里薄荷。 */
  fill: var(--insight-hot-soft, color-mix(in oklab, #ff9600 26%, transparent));
  stroke: var(--insight-hot, #ff9600);
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
