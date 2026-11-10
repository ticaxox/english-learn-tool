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
      <img class="shelf-book__art" :src="practiceBooks[module].day" alt="" />
      <span class="shelf-book__title">{{ titles[module] }}</span>
      <span class="shelf-book__hint">{{ hints[module] }}</span>
    </button>
    <span class="shelf-board" aria-hidden="true"></span>
  </div>
</template>

<style scoped>
.shelf {
  position: relative;
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 1.2rem;
  padding: 1.4rem 1rem 2.4rem;
}

/* The generated artwork IS the book. `.module-card` in learning.css still
   draws a tinted plate with a radius, so this has to out-specify it: the only
   things on screen are the book, its name and one line of guidance. */
.module-card.shelf-book,
.module-card.shelf-book:hover,
.module-card.shelf-book:active {
  position: relative;
  display: grid;
  justify-items: center;
  align-content: end;
  gap: 0.25rem;
  padding: 0;
  border: 0;
  border-radius: 0;
  background: none;
  box-shadow: none;
  color: inherit;
  text-align: center;
  cursor: pointer;
  transform: none;
  transition: none;
}

.module-card.shelf-book:focus-visible {
  outline: 3px solid var(--g-blue, #1cb0f6);
  outline-offset: 8px;
  border-radius: 14px;
}

.shelf-book__art {
  display: block;
  width: min(100%, 190px);
  height: auto;
  /* The book stands on the board: a soft contact shadow, no box behind it. */
  filter: drop-shadow(0 10px 10px rgb(40 24 8 / 26%));
  transition: transform 260ms cubic-bezier(0.2, 0.9, 0.25, 1.05), filter 260ms ease;
}

.shelf-book:hover .shelf-book__art,
.shelf-book:focus-visible .shelf-book__art {
  transform: translateY(-10px) scale(1.03);
  filter: drop-shadow(0 20px 16px rgb(40 24 8 / 30%));
}

/* A locked mode keeps its place on the shelf, chained and dimmed. */
.shelf-book.is-locked { cursor: not-allowed; }
.shelf-book.is-locked .shelf-book__art {
  filter: grayscale(0.9) brightness(0.9) drop-shadow(0 8px 8px rgb(40 24 8 / 20%));
  transform: none;
}
.shelf-book.is-locked .shelf-book__title { color: var(--ui-muted, #7a6448); }

.shelf-book__title {
  font-size: 1.05rem;
  font-weight: 800;
  color: var(--ui-ink, #35240f);
}

.shelf-book__hint {
  font-size: 0.8rem;
  color: var(--ui-muted, #7a6448);
}

.shelf-board {
  position: absolute;
  right: 0;
  bottom: 1.1rem;
  left: 0;
  height: 13px;
  border-radius: 3px;
  background: linear-gradient(#8a5a35, #6b4527);
  box-shadow: 0 10px 16px -8px rgb(40 24 8 / 50%);
}

@media (prefers-reduced-motion: reduce) {
  .shelf-book__art { transition: none; }
}

@media (max-width: 620px) {
  .shelf { gap: 0.7rem; padding: 1rem 0.5rem 2rem; }
  .shelf-book__title { font-size: 0.94rem; }
  .shelf-book__hint { font-size: 0.72rem; }
}
</style>
