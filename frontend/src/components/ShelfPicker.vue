<script setup lang="ts">
/**
 * The three memory modes as books standing on a shelf.
 *
 * Each book is a real 3D object: a spine you see face-on at rest, and a cover
 * that swings out when you hover or focus it. Disabled modes stay on the shelf
 * as chained, dimmed books so the shelf never reflows when config changes.
 *
 * `.module-card` and `aria-disabled` are kept as the contract the view tests
 * and the screen reader both rely on.
 */
import { computed } from 'vue'
import { practiceBooks } from '../assets/halloween'
import ArtImage from './ArtImage.vue'

export type ShelfModule = 'flashcard' | 'choice' | 'spelling'

const props = defineProps<{
  modules: readonly ShelfModule[]
  enabled: readonly ShelfModule[]
  labels: Record<string, string>
}>()

const emit = defineEmits<{ (event: 'pick', module: ShelfModule): void }>()

/** Hints are fixed per mode, matching the copy the old cards carried. */
const hints: Record<ShelfModule, string> = {
  flashcard: '看词回忆释义',
  choice: '选出正确释义',
  spelling: '按提示拼写',
}

const titles = computed(() => props.labels)

function pick(module: ShelfModule): void {
  if (!props.enabled.includes(module)) return
  emit('pick', module)
}
</script>

<template>
  <div class="shelf" role="group" aria-label="选择一种复习方式">
    <button
      v-for="module in modules"
      :key="module"
      class="module-card shelf-book"
      :class="[`shelf-book--${module}`, { 'is-locked': !enabled.includes(module) }]"
      type="button"
      :aria-disabled="enabled.includes(module) ? undefined : 'true'"
      :disabled="!enabled.includes(module)"
      @click="pick(module)"
    >
      <ArtImage class="shelf-book__art" :set="practiceBooks[module]" />

      <span class="shelf-book__title">{{ titles[module] }}</span>
      <span class="shelf-book__hint">{{ hints[module] }}</span>
    </button>
    <span class="shelf-board" aria-hidden="true"></span>
  </div>
</template>

<style scoped>
/* The shelf itself lives in practice.css: the AI exercise types stand on the
   same board, so both components need the same rules. */
</style>
