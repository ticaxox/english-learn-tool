<script setup lang="ts">
/**
 * The type mark: the spine of the book that stands for this practice type.
 *
 * Same seven books as the shelf and the type picker, so a type is recognisable
 * before its label is read. `mixed` has no book of its own and shows nothing.
 */
import { computed } from 'vue'
import { practiceBooks } from '../assets/halloween'
import ModeArt from './ModeArt.vue'

const props = defineProps<{
  type: string
  size?: number
}>()

const book = computed(() => practiceBooks[props.type as keyof typeof practiceBooks] ?? null)
</script>

<template>
  <ModeArt
    v-if="book"
    class="type-mark"
    :day="book.day"
    :night="book.night"
    :style="{ width: `${size ?? 22}px` }"
  />
</template>

<style scoped>
.type-mark {
  display: inline-block;
  aspect-ratio: 2 / 3;
  object-fit: contain;
  flex: 0 0 auto;
}
</style>
