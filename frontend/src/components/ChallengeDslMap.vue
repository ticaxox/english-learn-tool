<script setup lang="ts">
/**
 * Render the server's Markdown-like map description as a board-game trail.
 *
 * Every stop is one chunky token; the wave keeps the row from reading as a
 * linear table. The path is drawn from the same fixed geometry the CSS uses,
 * so connectors stay attached without measuring the DOM.
 */
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import HobMark from './HobMark.vue'
import { parseChallengeMapDsl, spreadSpacing, type ChallengeMapNode } from '../utils/challenge-map'
import { illustration, pumpkins } from '../assets/halloween'
import { themeMode } from '../composables/useTheme'

import { bump, drawPaths, gsap, motionAllowed, popIn } from '../composables/useMotion'

const props = withDefaults(defineProps<{ dsl: string; variant?: 'coin' | 'lantern' | 'pumpkin' }>(), { variant: 'pumpkin' })
const emit = defineEmits<{ select: [id: string] }>()

const NODE = 80
const BOSS = 96
const BRANCH = 60
const COLUMN = 146
const WAVE = 46
const TOP = 58
const BRANCH_GAP = 34

// Portrait phones and tablets get a vertical trail; wide screens a horizontal one.
const VERTICAL_QUERY = '(max-width: 819px)'
const V_ROW = 124
const V_AMPLITUDE = 44
const V_TOP = 44
const V_WIDTH = 320

const vertical = ref(false)
const trackRef = ref<HTMLElement | null>(null)
const boardRef = ref<HTMLElement | null>(null)
const trackWidth = ref(0)
let query: MediaQueryList | null = null
let resizeObserver: ResizeObserver | null = null

function syncOrientation(event?: MediaQueryListEvent): void {
  vertical.value = event ? event.matches : Boolean(query?.matches)
}

onMounted(() => {
  if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') return
  query = window.matchMedia(VERTICAL_QUERY)
  syncOrientation()
  query.addEventListener?.('change', syncOrientation)
  // The wide trail spreads across the card instead of leaving empty margins.
  if (typeof ResizeObserver !== 'undefined' && trackRef.value) {
    resizeObserver = new ResizeObserver((entries) => {
      trackWidth.value = Math.round(entries[0]?.contentRect.width ?? 0)
    })
    resizeObserver.observe(trackRef.value)
  }
})

onUnmounted(() => {
  query?.removeEventListener?.('change', syncOrientation)
  resizeObserver?.disconnect()
  resizeObserver = null
  walkTween?.kill()
  walkTween = null
})

const map = computed(() => parseChallengeMapDsl(props.dsl))

const isBoss = (node: ChallengeMapNode): boolean => node.typeLabel.includes('终点')
/** Matches the server's award table: boss 50 XP, ordinary nodes 20. */

const depths = computed(() => {
  const byId = new Map(map.value.nodes.map((node) => [node.id, node]))
  const result = new Map<string, number>()
  const resolve = (node: ChallengeMapNode, trail: Set<string>): number => {
    if (result.has(node.id)) return result.get(node.id)!
    if (trail.has(node.id)) return 0
    trail.add(node.id)
    const parents = node.previous
      .map((id) => byId.get(id))
      .filter((parent): parent is ChallengeMapNode => Boolean(parent))
    const parentDepth = parents.length
      ? Math.max(...parents.map((parent) => resolve(parent, trail)))
      : -1
    const depth = parents.length ? (node.optional ? parentDepth : parentDepth + 1) : 0
    result.set(node.id, depth)
    return depth
  }
  for (const node of map.value.nodes) resolve(node, new Set())
  return result
})

const columns = computed(() => {
  const grouped = new Map<number, { main: ChallengeMapNode[]; branches: ChallengeMapNode[] }>()
  for (const node of map.value.nodes) {
    const depth = depths.value.get(node.id) ?? 0
    const bucket = grouped.get(depth) ?? { main: [], branches: [] }
    if (node.optional) bucket.branches.push(node)
    else bucket.main.push(node)
    grouped.set(depth, bucket)
  }
  return [...grouped.entries()]
    .sort(([left], [right]) => left - right)
    .map(([depth, bucket]) => ({
      depth,
      main: bucket.main[0] ?? null,
      branches: [...bucket.branches].sort((a, b) => a.title.localeCompare(b.title, 'zh-CN')),
    }))
})

interface Placed {
  node: ChallengeMapNode
  x: number
  y: number
  size: number
}

interface Layout {
  list: Placed[]
  byId: Map<string, Placed>
  width: number
  height: number
}

function branchParent(branch: ChallengeMapNode, byId: Map<string, Placed>): Placed | null {
  const parentId = branch.previous.find((id) => byId.has(id))
  return parentId ? byId.get(parentId)! : null
}

/** Wide screens: one row that gently rises and falls. */
const horizontalLayout = computed<Layout>(() => {
  const list: Placed[] = []
  const byId = new Map<string, Placed>()
  const mainCount = columns.value.filter((column) => column.main).length
  const spacing = spreadSpacing(trackWidth.value, mainCount, BOSS, COLUMN)
  let columnIndex = 0
  for (const column of columns.value) {
    if (!column.main) continue
    const node = column.main
    const size = isBoss(node) ? BOSS : NODE
    const centerX = columnIndex * spacing + BOSS / 2 + 10
    const y = TOP + (columnIndex % 2) * WAVE
    const placed = { node, x: centerX - size / 2, y, size }
    list.push(placed)
    byId.set(node.id, placed)
    columnIndex += 1
  }
  for (const column of columns.value) {
    for (const branch of column.branches) {
      const parent = branchParent(branch, byId)
      if (!parent) continue
      const centerX = parent.x + parent.size / 2
      const y = parent.y + parent.size + BRANCH_GAP
      const placed = { node: branch, x: centerX - BRANCH / 2, y, size: BRANCH }
      list.push(placed)
      byId.set(branch.id, placed)
    }
  }
  const width = list.reduce((max, item) => Math.max(max, item.x + item.size), 0) + 10
  const height = list.reduce((max, item) => Math.max(max, item.y + item.size), 0) + 18
  return { list, byId, width: Math.max(width, 1), height: Math.max(height, 1) }
})

/** Portrait: the same trail read top to bottom, like a level path in a game. */
const verticalLayout = computed<Layout>(() => {
  const list: Placed[] = []
  const byId = new Map<string, Placed>()
  let index = 0
  for (const column of columns.value) {
    if (!column.main) continue
    const node = column.main
    const size = isBoss(node) ? BOSS : NODE
    const centerX = V_WIDTH / 2 + (index % 2 === 0 ? -V_AMPLITUDE : V_AMPLITUDE)
    const y = V_TOP + index * V_ROW
    const placed = { node, x: centerX - size / 2, y, size }
    list.push(placed)
    byId.set(node.id, placed)
    index += 1
  }
  for (const column of columns.value) {
    for (const branch of column.branches) {
      const parent = branchParent(branch, byId)
      if (!parent) continue
      const centerX = parent.x + parent.size / 2
      const placed = {
        node: branch,
        x: centerX - BRANCH / 2,
        y: parent.y + parent.size + 24,
        size: BRANCH,
      }
      list.push(placed)
      byId.set(branch.id, placed)
    }
  }
  const height = list.reduce((max, item) => Math.max(max, item.y + item.size), 0) + 30
  return { list, byId, width: V_WIDTH, height: Math.max(height, 1) }
})

const layout = computed(() => (vertical.value ? verticalLayout.value : horizontalLayout.value))

/** The stop the learner should act on next. Locked stops only get the number. */
const focusId = computed(() => {
  const nodes = map.value.nodes.filter((node) => !node.optional)
  return nodes.find((node) => node.statusKey === 'in_progress')?.id
    ?? nodes.find((node) => node.statusKey === 'unlocked')?.id
    ?? ''
})

const hasFocus = computed(() => Boolean(focusId.value))

/** Where Hob stands, in canvas pixels. Animated so it can walk the trail. */
const guidePos = ref<{ x: number; y: number } | null>(null)
const walking = ref(false)
let walkTween: gsap.core.Tween | null = null

/**
 * The stop the learner was on last time the map was on screen. This module
 * keeps it for the session, so coming back from a finished exercise still
 * shows the mascot walking the leg just earned instead of finding it teleported.
 */
let lastStop: { id: string; at: number } | null = null
const RETURN_WINDOW_MS = 10 * 60 * 1000

function centerOf(id: string): { x: number; y: number } | null {
  const placed = layout.value.byId.get(id)
  if (!placed) return null
  return { x: placed.x + placed.size / 2, y: placed.y + placed.size / 2 }
}

function cardElement(id: string): HTMLElement | null {
  return boardRef.value?.querySelector<HTMLElement>(`[data-node="${id}"]`) ?? null
}

/** Keep the stop that matters on screen when the trail is wider than the card. */
function keepFocusInSight(smooth: boolean): void {
  const track = trackRef.value
  const placed = focusId.value ? layout.value.byId.get(focusId.value) : null
  if (!track || !placed) return
  const center = placed.x + placed.size / 2
  const left = Math.max(0, center - track.clientWidth / 2)
  if (Math.abs(track.scrollLeft - left) < 4) return
  if (!smooth || !motionAllowed()) {
    track.scrollLeft = left
    return
  }
  try {
    track.scrollTo({ left, behavior: 'smooth' })
  } catch {
    track.scrollLeft = left
  }
}

/** Drop one spark behind the walker; it fades on its own. */
function dropCrumb(x: number, y: number): void {
  const canvas = boardRef.value?.querySelector('.challenge-dsl-canvas')
  if (!canvas) return
  const spark = document.createElement('span')
  spark.className = 'challenge-dsl-spark'
  spark.style.left = `${x}px`
  spark.style.top = `${y}px`
  canvas.appendChild(spark)
  gsap.to(spark, {
    opacity: 0,
    scale: 0.4,
    duration: 0.75,
    delay: 0.1,
    ease: 'power2.out',
    onComplete: () => spark.remove(),
  })
}

/**
 * Point on the leg at `t`. The mascot travels centre to centre — the drawn
 * line runs edge to edge — so it steps off and onto the stops it stands on.
 */
function pointOn(edge: Edge, start: { x: number; y: number }, end: { x: number; y: number }, t: number): { x: number; y: number } {
  const u = 1 - t
  const [c1, c2] = edge.controls
  return {
    x: u * u * u * start.x + 3 * u * u * t * c1.x + 3 * u * t * t * c2.x + t * t * t * end.x,
    y: u * u * u * start.y + 3 * u * u * t * c1.y + 3 * u * t * t * c2.y + t * t * t * end.y,
  }
}

function land(id: string, travelled: boolean): void {
  const card = cardElement(id)
  if (!card) return
  bump(card, 1.12)
  card.classList.add('is-landed')
  window.setTimeout(() => card.classList.remove('is-landed'), 900)
  if (travelled) {
    const reward = card.querySelector('.challenge-dsl-reward')
    if (reward) bump(reward, 1.6)
  }
}

/**
 * Walk the trail from one stop to the next instead of teleporting.
 * The leg's gold is drawn in step with the mascot, so the trail reads as
 * "you just came this way".
 */
function walkTo(fromId: string, toId: string): void {
  const target = centerOf(toId)
  if (!target) return
  walkTween?.kill()
  walkTween = null

  const edge = edges.value.find((item) => item.id === `${fromId}->${toId}`)
  const start = centerOf(fromId)
  walking.value = false
  if (!edge || !start || !motionAllowed() || !guidePos.value) {
    // The stop jumped (two nodes finished at once) — set down, do not walk.
    guidePos.value = target
    land(toId, Boolean(edge))
    return
  }
  walking.value = true

  const leg = boardRef.value?.querySelector<SVGPathElement>(`[data-edge="${edge.id}"]`)
  const duration = gsap.utils.clamp(0.55, 1.05, edge.length / 320)
  if (leg) {
    gsap.fromTo(leg, { drawSVG: '0%' }, { drawSVG: '100%', duration, ease: 'power1.inOut' })
  }

  const state = { t: 0 }
  const sparkPoints = [0.18, 0.38, 0.58, 0.78]
  let dropped = 0
  walkTween = gsap.to(state, {
    t: 1,
    duration,
    ease: 'power1.inOut',
    onUpdate: () => {
      const point = pointOn(edge, start, target, state.t)
      // A small hop arc keeps the walk from looking like a slide.
      guidePos.value = { x: point.x, y: point.y - Math.sin(state.t * Math.PI) * 12 }
      if (dropped < sparkPoints.length && state.t >= sparkPoints[dropped]) {
        dropCrumb(point.x, point.y)
        dropped += 1
      }
    },
    onComplete: () => {
      guidePos.value = target
      walkTween = null
      walking.value = false
      land(toId, true)
    },
  })
}

// Stand on the current stop, and walk there whenever the stop moves forward.
watch(
  focusId,
  (next, previous) => {
    if (!next) {
      guidePos.value = null
      return
    }
    const remembered = lastStop
    lastStop = { id: next, at: Date.now() }
    const from = previous && previous !== next
      ? previous
      : remembered && remembered.id !== next && Date.now() - remembered.at < RETURN_WINDOW_MS
        ? remembered.id
        : null
    if (from && layout.value.byId.has(from)) {
      // Start the mascot on the stop it left, then let it walk over. On the
      // first render the board is not in the DOM yet, so wait one tick for the
      // leg and the nodes to exist before measuring them.
      guidePos.value = centerOf(from) ?? centerOf(next)
      walking.value = true
      const start = () => {
        walkTo(from, next)
        keepFocusInSight(true)
      }
      if (previous) start()
      else void nextTick(start)
      return
    }
    guidePos.value = centerOf(next)
    nextTick(() => keepFocusInSight(false))
  },
  { immediate: true },
)

/**
 * The board's own watcher. The entrance only replays when the geometry really
 * changed — a finished stop re-derives the same positions and must not pop
 * every card again under the walking mascot.
 */
let layoutKey = ''

watch(layout, () => {
  const key = [
    vertical.value ? 'v' : 'h',
    layout.value.width,
    layout.value.height,
    ...layout.value.list.map((placed) => `${placed.node.id}:${placed.x},${placed.y},${placed.size}`),
  ].join('|')
  if (key !== layoutKey && !walking.value) {
    layoutKey = key
    nextTick(() => {
      if (!boardRef.value) return
      drawPaths(boardRef.value.querySelector('.challenge-dsl-links'))
      popIn(Array.from(boardRef.value.querySelectorAll('.challenge-dsl-card')), {
        y: 12,
        scale: 0.8,
        stagger: 0.05,
      })
    })
  }
  layoutKey = key

  // Never leave the mascot floating between stops after a resize.
  if (walking.value || !focusId.value) return
  guidePos.value = centerOf(focusId.value)
  keepFocusInSight(false)
})

interface Edge {
  id: string
  path: string
  /** Geometry kept alongside the path so the mascot can walk it exactly. */
  from: { x: number; y: number }
  to: { x: number; y: number }
  controls: [{ x: number; y: number }, { x: number; y: number }]
  length: number
  classes: Record<string, boolean>
}

const edges = computed<Edge[]>(() => {
  const result: Edge[] = []
  for (const node of map.value.nodes) {
    const child = layout.value.byId.get(node.id)
    if (!child) continue
    for (const parentId of node.previous) {
      const parent = layout.value.byId.get(parentId)
      if (!parent) continue
      const parentCenterX = parent.x + parent.size / 2
      const parentCenterY = parent.y + parent.size / 2
      const childCenterX = child.x + child.size / 2
      const childCenterY = child.y + child.size / 2
      const from = {
        x: vertical.value ? parentCenterX : parent.x + parent.size,
        y: vertical.value ? parent.y + parent.size : parentCenterY,
      }
      const to = {
        x: vertical.value ? childCenterX : child.x,
        y: vertical.value ? child.y : childCenterY,
      }
      let controls: [{ x: number; y: number }, { x: number; y: number }]
      if (vertical.value) {
        const lift = node.optional ? 20 : 44
        controls = [
          { x: parentCenterX, y: parent.y + parent.size + lift },
          { x: childCenterX, y: child.y - lift },
        ]
      } else if (node.optional) {
        controls = [
          { x: parentCenterX, y: parent.y + parent.size + BRANCH_GAP / 2 },
          { x: childCenterX, y: child.y - BRANCH_GAP / 2 },
        ]
      } else {
        controls = [
          { x: parent.x + parent.size + 46, y: parentCenterY },
          { x: child.x - 46, y: childCenterY },
        ]
      }
      const path = `M ${from.x} ${from.y} C ${controls[0].x} ${controls[0].y}, ${controls[1].x} ${controls[1].y}, ${to.x} ${to.y}`
      result.push({
        id: `${parentId}->${node.id}`,
        path,
        from,
        to,
        controls,
        length: Math.hypot(to.x - from.x, to.y - from.y),
        classes: {
          // A leg already walked is gold even when its far stop is still open.
          'is-done': node.statusKey === 'completed' || parent.node.statusKey === 'completed',
          // The leg leaving the current stop is the one the learner takes next.
          'is-next': parentId === focusId.value,
          'is-branch': node.optional,
        },
      })
    }
  }
  return result
})

const remaining = computed(() => map.value.nodes.filter((node) => node.statusKey !== 'completed').length)
const minutesLeft = computed(() => map.value.nodes
  .filter((node) => node.statusKey !== 'completed')
  .reduce((total, node) => total + node.minutes, 0))

function cardClasses(node: ChallengeMapNode): Record<string, boolean> {
  return {
    [`is-${node.statusKey}`]: true,
    'is-boss': isBoss(node),
    'is-branch': node.optional,
    'is-focus': node.id === focusId.value && hasFocus.value,
  }
}
</script>

<template>
  <section
    class="challenge-dsl-map panel"
    :class="`challenge-dsl-map--${variant}`"
    :style="variant === 'pumpkin' ? { '--pumpkin-done': `url(${pumpkins.done[themeMode]})`, '--pumpkin-todo': `url(${pumpkins.todo[themeMode]})`, '--pumpkin-boss': `url(${pumpkins.boss[themeMode]})`, '--pumpkin-branch': `url(${pumpkins.branch[themeMode]})` } : undefined"
    aria-label="闯关地图"
  >
    <header class="challenge-dsl-map__head">
      <div>
        <p class="challenge-dsl-summary">
          还剩 <strong>{{ remaining }}</strong> 关<template v-if="minutesLeft > 0"> · 约 {{ minutesLeft }} 分钟</template>
        </p>
        <p class="field-hint">点一下节点，看这一关的说明和开始按钮。</p>
      </div>
      <div class="challenge-dsl-legend" aria-hidden="true">
        <span class="is-done"><i></i>已完成</span>
        <span class="is-open"><i></i>进行中</span>
        <span class="is-locked"><i></i>未解锁</span>
      </div>
    </header>

    <div ref="trackRef" class="challenge-dsl-track">
      <div ref="boardRef" class="challenge-dsl-board">
      <div
        class="challenge-dsl-canvas"
        :style="{ width: `${layout.width}px`, height: `${layout.height}px` }"
      >
        <svg
          class="challenge-dsl-links"
          :width="layout.width"
          :height="layout.height"
          :viewBox="`0 0 ${layout.width} ${layout.height}`"
          aria-hidden="true"
        >
          <path
            v-for="edge in edges"
            :key="edge.id"
            :data-edge="edge.id"
            :d="edge.path"
            :class="edge.classes"
          />
        </svg>

        <DivButton
          v-for="placed in layout.list"
          :key="placed.node.id"
          type="button"
          class="challenge-dsl-card"
          :class="cardClasses(placed.node)"
          :data-node="placed.node.id"
          :style="{ left: `${placed.x}px`, top: `${placed.y}px`, width: `${placed.size}px`, height: `${placed.size}px` }"
          :title="placed.node.title"
          :aria-label="`${placed.node.title}，${placed.node.typeLabel}，${placed.node.questionType}，${placed.node.statusLabel}，${placed.node.minutes} 分钟`"
          @click="emit('select', placed.node.id)"
        >
          <span class="visually-hidden">{{ placed.node.title }}</span>
        </DivButton>

        <HobMark
          v-if="guidePos"
          size="small"
          :set="illustration.result"
          class="challenge-dsl-guide"
          :style="{ left: `${guidePos.x}px`, top: `${guidePos.y}px` }"
        />
      </div>
      </div>
    </div>
  </section>
</template>
