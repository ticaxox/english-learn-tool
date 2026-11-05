<script setup lang="ts">
/**
 * Render the server's Markdown-like map description as a clickable graph.
 *
 * Columns follow the longest path from the start; branches stack under the
 * node they split from. Curved SVG links mirror the `前置 / 分支` lines, so the
 * map stays driven by the text instead of a hard-coded station strip.
 */
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { parseChallengeMapDsl, type ChallengeMapNode } from '../utils/challenge-map'

const props = defineProps<{ dsl: string }>()
const emit = defineEmits<{ select: [id: string] }>()

const map = computed(() => parseChallengeMapDsl(props.dsl))
const track = ref<HTMLElement | null>(null)
const slots = ref<Record<string, HTMLElement | null>>({})
const edges = ref<Array<{ id: string; path: string; optional: boolean }>>([])
const canvasSize = ref({ width: 0, height: 0 })
let observer: ResizeObserver | null = null

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
    // A branch sits in the same column as its parent, below it.
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

function setSlot(id: string, element: unknown): void {
  slots.value[id] = (element as HTMLElement | null) ?? null
}

async function drawEdges(): Promise<void> {
  await nextTick()
  const container = track.value
  if (!container) return
  const containerRect = container.getBoundingClientRect()
  canvasSize.value = { width: container.scrollWidth, height: container.scrollHeight }
  const nextEdges: Array<{ id: string; path: string; optional: boolean }> = []
  for (const node of map.value.nodes) {
    const child = slots.value[node.id]
    if (!child) continue
    const childRect = child.getBoundingClientRect()
    for (const parentId of node.previous) {
      const parent = slots.value[parentId]
      if (!parent) continue
      const parentRect = parent.getBoundingClientRect()
      const sameColumn = Math.abs(parentRect.left - childRect.left) < 8
      let path: string
      if (sameColumn) {
        const x = parentRect.left + parentRect.width / 2 - containerRect.left
        const y1 = parentRect.bottom - containerRect.top
        const y2 = childRect.top - containerRect.top
        path = `M ${x} ${y1} C ${x} ${y1 + 20}, ${x} ${y2 - 20}, ${x} ${y2}`
      } else {
        const x1 = parentRect.right - containerRect.left
        const y1 = parentRect.top + parentRect.height / 2 - containerRect.top
        const x2 = childRect.left - containerRect.left
        const y2 = childRect.top + childRect.height / 2 - containerRect.top
        const bend = Math.max(28, (x2 - x1) / 2)
        path = `M ${x1} ${y1} C ${x1 + bend} ${y1}, ${x2 - bend} ${y2}, ${x2} ${y2}`
      }
      nextEdges.push({
        id: `${parentId}->${node.id}`,
        path,
        optional: node.optional,
      })
    }
  }
  edges.value = nextEdges
}

watch(
  () => props.dsl,
  () => {
    slots.value = {}
    void drawEdges()
  },
)

onMounted(() => {
  void drawEdges()
  if (typeof ResizeObserver !== 'undefined') {
    observer = new ResizeObserver(() => void drawEdges())
    if (track.value) observer.observe(track.value)
  }
  window.addEventListener('resize', drawEdges)
})

onBeforeUnmount(() => {
  observer?.disconnect()
  window.removeEventListener('resize', drawEdges)
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

    <div ref="track" class="challenge-dsl-track" :style="{ '--map-columns': columns.length }">
      <div class="challenge-dsl-canvas">
        <svg
          class="challenge-dsl-links"
          :width="canvasSize.width"
          :height="canvasSize.height"
          :viewBox="`0 0 ${canvasSize.width || 1} ${canvasSize.height || 1}`"
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
            <div
              v-for="node in column.nodes"
              :key="node.id"
              :ref="(element) => setSlot(node.id, element)"
              class="challenge-dsl-slot"
            >
              <DivButton
                type="button"
                class="challenge-dsl-card"
                :class="[`is-${node.statusKey}`, { 'is-branch': node.optional }]"
                :aria-label="`${node.title}，${node.typeLabel}，${node.statusLabel}`"
                @click="emit('select', node.id)"
              >
                <span class="challenge-dsl-card__type">{{ node.typeLabel }} · {{ node.questionType }}</span>
                <strong>{{ node.title }}</strong>
                <span class="challenge-dsl-card__meta">{{ node.minutes }} 分钟 · {{ node.statusLabel }}</span>
              </DivButton>
            </div>
          </div>
        </div>
      </div>
    </div>
  </section>
</template>
