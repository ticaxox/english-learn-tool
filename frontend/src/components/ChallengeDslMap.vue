<script setup lang="ts">
/**
 * Render the server's Markdown-like map description as a clickable path.
 *
 * Columns follow the longest path from the start; a branch sits below its
 * parent. Geometry comes from the same fixed node size and gaps the CSS uses,
 * so connectors stay attached without measuring the DOM.
 */
import { computed } from 'vue'
import { parseChallengeMapDsl, type ChallengeMapNode } from '../utils/challenge-map'

const props = defineProps<{ dsl: string }>()
const emit = defineEmits<{ select: [id: string] }>()

const NODE = 64
const COLUMN_GAP = 90
const ROW_GAP = 20

const map = computed(() => parseChallengeMapDsl(props.dsl))

const nodeMarks = computed(() => {
  const marks = new Map<string, string>()
  let order = 0
  for (const node of map.value.nodes) {
    if (node.optional) {
      marks.set(node.id, '✦')
      continue
    }
    order += 1
    marks.set(node.id, node.typeLabel.includes('终点') ? '★' : String(order))
  }
  return marks
})

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

interface Column {
  depth: number
  nodes: ChallengeMapNode[]
}

const columns = computed<Column[]>(() => {
  const grouped = new Map<number, ChallengeMapNode[]>()
  for (const node of map.value.nodes) {
    const depth = depths.value.get(node.id) ?? 0
    const bucket = grouped.get(depth) ?? []
    bucket.push(node)
    grouped.set(depth, bucket)
  }
  return [...grouped.entries()]
    .sort(([left], [right]) => left - right)
    .map(([depth, nodes]) => ({
      depth,
      nodes: [...nodes].sort((left, right) => {
        if (left.optional !== right.optional) return left.optional ? 1 : -1
        return left.title.localeCompare(right.title, 'zh-CN')
      }),
    }))
})

interface Point {
  x: number
  y: number
  column: number
}

const layout = computed(() => {
  const points = new Map<string, Point>()
  let maxRows = 1
  columns.value.forEach((column, columnIndex) => {
    maxRows = Math.max(maxRows, column.nodes.length)
    column.nodes.forEach((node, rowIndex) => {
      points.set(node.id, {
        x: columnIndex * (NODE + COLUMN_GAP) + NODE / 2,
        y: rowIndex * (NODE + ROW_GAP) + NODE / 2,
        column: columnIndex,
      })
    })
  })
  return {
    points,
    width: Math.max(1, columns.value.length * NODE + (columns.value.length - 1) * COLUMN_GAP),
    height: Math.max(NODE, maxRows * NODE + (maxRows - 1) * ROW_GAP),
  }
})

const edges = computed(() => {
  const { points } = layout.value
  const result: Array<{ id: string; path: string; optional: boolean }> = []
  for (const node of map.value.nodes) {
    const child = points.get(node.id)
    if (!child) continue
    for (const parentId of node.previous) {
      const parent = points.get(parentId)
      if (!parent) continue
      let path: string
      if (parent.column === child.column) {
        const y1 = parent.y + NODE / 2
        const y2 = child.y - NODE / 2
        path = `M ${parent.x} ${y1} C ${parent.x} ${y1 + 20}, ${child.x} ${y2 - 20}, ${child.x} ${y2}`
      } else {
        const x1 = parent.x + NODE / 2
        const x2 = child.x - NODE / 2
        const bend = Math.max(24, (x2 - x1) / 2)
        path = `M ${x1} ${parent.y} C ${x1 + bend} ${parent.y}, ${x2 - bend} ${child.y}, ${x2} ${child.y}`
      }
      result.push({ id: `${parentId}->${node.id}`, path, optional: node.optional })
    }
  }
  return result
})
</script>

<template>
  <section class="challenge-dsl-map panel" aria-label="闯关地图">
    <header class="challenge-dsl-map__head">
      <div>
        <p class="eyebrow">闯关地图</p>
        <p class="field-hint">按连线顺序解锁；虚线支线可自由选择。</p>
      </div>
      <div class="challenge-dsl-legend" aria-label="地图图例">
        <span class="is-main">主线</span>
        <span class="is-branch">支线</span>
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
            :class="{ 'is-branch': edge.optional }"
          />
        </svg>

        <div class="challenge-dsl-columns">
          <div v-for="column in columns" :key="column.depth" class="challenge-dsl-column">
            <div v-for="node in column.nodes" :key="node.id" class="challenge-dsl-slot">
              <DivButton
                type="button"
                class="challenge-dsl-card"
                :class="[`is-${node.statusKey}`, { 'is-branch': node.optional }]"
                :title="node.title"
                :aria-label="`${node.title}，${node.typeLabel}，${node.questionType}，${node.statusLabel}，${node.minutes} 分钟`"
                @click="emit('select', node.id)"
              >
                <span class="challenge-dsl-card__mark">{{ nodeMarks.get(node.id) }}</span>
                <span class="visually-hidden">{{ node.title }}</span>
              </DivButton>
            </div>
          </div>
        </div>
      </div>
    </div>
  </section>
</template>
