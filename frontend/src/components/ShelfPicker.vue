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
      v-for="(module, index) in modules"
      :key="module"
      class="module-card shelf-book"
      :class="[`shelf-book--${module}`, { 'is-locked': !enabled.includes(module) }]"
      type="button"
      :aria-disabled="enabled.includes(module) ? undefined : 'true'"
      :disabled="!enabled.includes(module)"
      :style="{ '--i': index }"
      @click="pick(module)"
    >
      <span class="shelf-book__body" aria-hidden="true">
        <span class="shelf-book__cover">
          <img class="shelf-book__art" :src="practiceBooks[module].day" alt="" />
        </span>
        <span class="shelf-book__spine"><i></i><i></i><i></i><i></i></span>
      </span>
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
  gap: 1.4rem;
  padding: 1.6rem 1.2rem 2.6rem;
  /* The board is drawn by .shelf-board so the books overlap it like real books. */
}

/* The book is the object. `.module-card` in learning.css still draws a rounded
   tinted plate, so this has to out-specify it — otherwise the book ends up
   sitting inside a second rounded rectangle. */
.module-card.shelf-book,
.module-card.shelf-book:hover,
.module-card.shelf-book:active,
.module-card.shelf-book:focus-visible {
  position: relative;
  display: grid;
  justify-items: center;
  gap: 0.3rem;
  padding: 0;
  border: 0;
  border-radius: 0;
  background: none;
  box-shadow: none;
  color: inherit;
  text-align: center;
  cursor: pointer;
  perspective: 900px;
  transform: none;
  transition: none;
}

.module-card.shelf-book:focus-visible {
  outline: 3px solid var(--g-blue, #1cb0f6);
  outline-offset: 8px;
  border-radius: 14px;
}

.shelf-book__body {
  position: relative;
  display: block;
  width: 100%;
  max-width: 148px;
  aspect-ratio: 3 / 4;
  transform-style: preserve-3d;
  transform: rotateY(-18deg);
  transition: transform 420ms cubic-bezier(0.2, 0.9, 0.25, 1.05);
}

/* The cover swings toward the reader; the spine stays as the hinge edge. */
.shelf-book:hover .shelf-book__body,
.shelf-book:focus-visible .shelf-book__body {
  transform: rotateY(-4deg) translateY(-10px);
}

.shelf-book__cover {
  position: absolute;
  inset: 0;
  display: grid;
  place-items: center;
  border-radius: 4px 10px 10px 4px;
  background: var(--cover, #d9611f);
  box-shadow:
    inset -6px 0 0 rgb(0 0 0 / 12%),
    0 10px 18px -8px rgb(40 24 8 / 45%);
  overflow: hidden;
}

.shelf-book__art {
  width: 76%;
  height: 76%;
  object-fit: contain;
  filter: drop-shadow(0 4px 0 rgb(0 0 0 / 12%));
}

.shelf-book__spine {
  position: absolute;
  top: 0;
  bottom: 0;
  left: -14px;
  display: grid;
  gap: 6px;
  align-content: space-evenly;
  width: 16px;
  padding: 10px 0;
  border-radius: 4px 0 0 4px;
  background: color-mix(in srgb, var(--cover, #d9611f) 72%, #2b1c17);
  box-shadow: inset -3px 0 0 rgb(0 0 0 / 18%);
}

.shelf-book__spine i {
  display: block;
  height: 2px;
  background: rgb(255 255 255 / 34%);
}

.shelf-book__title {
  margin-top: 0.7rem;
  font-size: 1.02rem;
  font-weight: 800;
  color: var(--ui-ink, #35240f);
}

.shelf-book__hint {
  font-size: 0.8rem;
  color: var(--ui-muted, #7a6448);
}

.shelf-book--flashcard { --cover: #d9611f; }
.shelf-book--choice { --cover: #5f7f3a; }
.shelf-book--spelling { --cover: #d9be93; }

/* A chained book leans back and loses its colour. */
.shelf-book.is-locked { cursor: not-allowed; }
.shelf-book.is-locked .shelf-book__body { transform: rotateY(-30deg) translateY(6px); }
.shelf-book.is-locked .shelf-book__cover { filter: grayscale(0.85) brightness(0.92); }
.shelf-book.is-locked .shelf-book__spine { background: #6b5a48; }
.shelf-book.is-locked .shelf-book__title { color: var(--ui-muted, #7a6448); }

.shelf-board {
  position: absolute;
  right: 0;
  bottom: 0.9rem;
  left: 0;
  height: 14px;
  border-radius: 4px;
  background: linear-gradient(#8a5a35, #6b4527);
  box-shadow: 0 8px 14px -6px rgb(40 24 8 / 45%);
}

@media (prefers-reduced-motion: reduce) {
  .shelf-book__body { transition: none; transform: none; }
}

@media (max-width: 620px) {
  .shelf {
    gap: 0.8rem;
    padding: 1rem 0.6rem 2.2rem;
  }
  .shelf-book__title { font-size: 0.92rem; }
}
</style>
