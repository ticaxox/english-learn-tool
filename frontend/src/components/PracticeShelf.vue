<script setup lang="ts">
/**
 * The four AI exercise types as books on the same shelf as the memory modes.
 *
 * They sit below the three memory books and read the same way: a cover you
 * pick up, a name, one line about what the book holds. Picking one does not
 * start anything — it opens the settings for that kind of exercise, because
 * how many questions and from which source is the learner's call.
 */
import { computed } from 'vue'
import { practiceBooks } from '../assets/halloween'
import ArtImage from './ArtImage.vue'
import type { PracticeType } from '../api/practice'

const props = defineProps<{
  types: readonly PracticeType[]
  labels: Record<string, string>
}>()

const emit = defineEmits<{ (event: 'pick', type: PracticeType): void }>()

/** One line under each book: what that exercise asks of you. */
const hints: Record<string, string> = {
  fill_blank: '在句子里补上缺的词',
  reading: '读一篇真题再答题',
  translation: '把句子译成另一种语言',
  writing: '按题目写一篇短文',
  conversation: '和 AI 角色对话',
}

const books = computed(() =>
  props.types.map((type) => ({
    type,
    label: props.labels[type] ?? type,
    hint: hints[type] ?? '',
    art: practiceBooks[type] ?? null,
  })),
)
</script>

<template>
  <div class="shelf practice-shelf" role="group" aria-label="选择一种 AI 练习">
    <button
      v-for="book in books"
      :key="book.type"
      class="module-card shelf-book"
      :class="`shelf-book--${book.type}`"
      type="button"
      @click="emit('pick', book.type)"
    >
      <ArtImage class="shelf-book__art" :set="book.art" />

      <span class="shelf-book__title">{{ book.label }}</span>
      <span class="shelf-book__hint">{{ book.hint }}</span>
    </button>
    <span class="shelf-board" aria-hidden="true"></span>
  </div>
</template>

<style scoped>
/* The shelf itself is drawn by ShelfPicker's rules; this row only needs its
   own column count on top of them. */
.practice-shelf {
  grid-template-columns: repeat(5, minmax(0, 1fr));
  padding-bottom: 2.2rem;
}

@media (max-width: 900px) {
  .practice-shelf { grid-template-columns: repeat(3, minmax(0, 1fr)); }
}

@media (max-width: 620px) {
  .practice-shelf { grid-template-columns: repeat(2, minmax(0, 1fr)); }
}
</style>
