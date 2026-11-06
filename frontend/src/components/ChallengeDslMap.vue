<script setup lang="ts">
/**
 * Render the server's Markdown-like map description as a board-game trail.
 *
 * Every stop is one chunky token; the wave keeps the row from reading as a
 * linear table. The path is drawn from the same fixed geometry the CSS uses,
 * so connectors stay attached without measuring the DOM.
 */
import { computed, onMounted, onUnmounted, ref } from 'vue'
import AppIcon from './AppIcon.vue'
import CrumboMark from './CrumboMark.vue'
import { parseChallengeMapDsl, type ChallengeMapNode } from '../utils/challenge-map'

const props = defineProps<{ dsl: string }>()
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
let query: MediaQueryList | null = null

function syncOrientation(event?: MediaQueryListEvent): void {
  vertical.value = event ? event.matches : Boolean(query?.matches)
}

onMounted(() => {
  if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') return
  query = window.matchMedia(VERTICAL_QUERY)
  syncOrientation()
  query.addEventListener?.('change', syncOrientation)
})

onUnmounted(() => {
  query?.removeEventListener?.('change', syncOrientation)
})

const map = computed(() => parseChallengeMapDsl(props.dsl))

const isBoss = (node: ChallengeMapNode): boolean => node.typeLabel.includes('终点')

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
  let columnIndex = 0
  for (const column of columns.value) {
    if (!column.main) continue
    const node = column.main
    const size = isBoss(node) ? BOSS : NODE
    const centerX = columnIndex * COLUMN + BOSS / 2 + 10
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
      const preferred = parent.x + parent.size / 2 + 78
      const centerX = Math.min(preferred, V_WIDTH - BRANCH / 2 - 4)
      const placed = { node: branch, x: centerX - BRANCH / 2, y: parent.y + 16, size: BRANCH }
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
const guide = computed(() => {
  const placed = focusId.value ? layout.value.byId.get(focusId.value) : null
  if (!placed) return null
  return { left: `${placed.x + placed.size - 10}px`, top: `${placed.y - 34}px` }
})

interface Edge {
  id: string
  path: string
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
      let path: string
      if (vertical.value) {
        path = node.optional
          ? `M ${parent.x + parent.size} ${parentCenterY} C ${parent.x + parent.size + 34} ${parentCenterY}, ${child.x - 34} ${childCenterY}, ${child.x} ${childCenterY}`
          : `M ${parentCenterX} ${parent.y + parent.size} C ${parentCenterX} ${parent.y + parent.size + 44}, ${childCenterX} ${child.y - 44}, ${childCenterX} ${child.y}`
      } else {
        path = node.optional
          ? `M ${parentCenterX} ${parent.y + parent.size} C ${parentCenterX} ${parent.y + parent.size + BRANCH_GAP / 2}, ${childCenterX} ${child.y - BRANCH_GAP / 2}, ${childCenterX} ${child.y}`
          : `M ${parent.x + parent.size} ${parentCenterY} C ${parent.x + parent.size + 46} ${parentCenterY}, ${child.x - 46} ${childCenterY}, ${child.x} ${childCenterY}`
      }
      result.push({
        id: `${parentId}->${node.id}`,
        path,
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

const orderById = computed(() => {
  const result = new Map<string, number>()
  let order = 0
  for (const node of map.value.nodes) {
    if (node.optional) continue
    order += 1
    result.set(node.id, order)
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
  <section class="challenge-dsl-map panel" aria-label="闯关地图">
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

    <div class="challenge-dsl-track">
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
          :style="{ left: `${placed.x}px`, top: `${placed.y}px`, width: `${placed.size}px`, height: `${placed.size}px` }"
          :title="placed.node.title"
          :aria-label="`${placed.node.title}，${placed.node.typeLabel}，${placed.node.questionType}，${placed.node.statusLabel}，${placed.node.minutes} 分钟`"
          @click="emit('select', placed.node.id)"
        >
          <svg
            v-if="placed.node.statusKey === 'completed'"
            class="challenge-dsl-check"
            viewBox="0 0 24 24"
            aria-hidden="true"
          >
            <path d="m5 12.5 4.5 4.5L19 7.5" />
          </svg>
          <AppIcon v-else-if="isBoss(placed.node)" name="star" />
          <AppIcon v-else-if="placed.node.optional" name="spark" />
          <AppIcon v-else-if="placed.node.statusKey === 'locked'" name="lock" />
          <span v-else class="challenge-dsl-card__mark">{{ orderById.get(placed.node.id) }}</span>
          <span class="visually-hidden">{{ placed.node.title }}</span>
        </DivButton>

        <CrumboMark v-if="guide" size="small" class="challenge-dsl-guide" :style="guide" />
      </div>
    </div>
  </section>
</template>
