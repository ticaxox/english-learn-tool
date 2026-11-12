<script setup lang="ts">
/**
 * The three memory drills as cards, plus the conversation drill as a book.
 *
 * A memory drill is a card drill - you look at a face, you turn it over - so it
 * is drawn as a card. The AI exercise types on the row below are generated
 * sets, which is what a book means here. The two rows then carry that
 * distinction instead of repeating one shape twice.
 *
 * This row stands on the page itself: no board under it, and the covers a
 * little smaller than the books below, because four sit across instead of
 * three.
 *
 * `.module-card` and `aria-disabled` are kept as the contract the view tests
 * and the screen reader both rely on.
 */
import { computed } from 'vue'
import { memoryCards, practiceBooks } from '../assets/halloween'
import ArtImage from './ArtImage.vue'
import type { PracticeType } from '../api/practice'

export type ShelfModule = 'flashcard' | 'choice' | 'spelling'

/** A book that sits on this row rather than the AI-exercise row below. */
export interface ShelfBook {
  type: PracticeType
  label: string
  hint: string
}

const props = withDefaults(defineProps<{
  modules: readonly ShelfModule[]
  enabled: readonly ShelfModule[]
  labels: Record<string, string>
  /** Extra entries drawn as books, after the cards. */
  books?: readonly ShelfBook[]
}>(), {
  books: () => [],
})

const emit = defineEmits<{
  (event: 'pick', module: ShelfModule): void
  (event: 'pick-book', type: PracticeType): void
}>()

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
  <div class="shelf shelf--cards" role="group" aria-label="选择一种复习方式">
    <button
      v-for="module in modules"
      :key="module"
      class="module-card shelf-book shelf-card"
      :class="[`shelf-book--${module}`, { 'is-locked': !enabled.includes(module) }]"
      type="button"
      :aria-disabled="enabled.includes(module) ? undefined : 'true'"
      :disabled="!enabled.includes(module)"
      @click="pick(module)"
    >
      <ArtImage class="shelf-book__art" :set="memoryCards[module]" />

      <span class="shelf-book__title">{{ titles[module] }}</span>
      <span class="shelf-book__hint">{{ hints[module] }}</span>
    </button>

    <button
      v-for="book in books"
      :key="book.type"
      class="module-card shelf-book shelf-card"
      :class="`shelf-book--${book.type}`"
      type="button"
      @click="emit('pick-book', book.type)"
    >
      <ArtImage class="shelf-book__art" :set="practiceBooks[book.type]" />

      <span class="shelf-book__title">{{ book.label }}</span>
      <span class="shelf-book__hint">{{ book.hint }}</span>
    </button>
  </div>
</template>

<style scoped>
/* The shelf rules live in practice.css: the AI exercise types below use the
   same ones, so both rows stay one system. */
</style>
