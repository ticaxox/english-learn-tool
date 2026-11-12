<script setup lang="ts">
/**
 * The four AI exercise types as books on the same shelf as the memory modes.
 *
 * They sit below the three memory books and read the same way: a cover you
 * pick up, a name, one line about what the book holds. Picking one does not
 * start anything — it opens the settings for that kind of exercise, because
 * how many questions and from which source is the learner's call.
 *
 * The conversation book has no painted cover yet, so it is drawn: a book in
 * the same 2:3 frame with a speech mark on it. It is a placeholder for the
 * artwork, not a different kind of control.
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
      <ArtImage v-if="book.art" class="shelf-book__art" :set="book.art" />
      <svg
        v-else
        class="shelf-book__art shelf-book__art--drawn"
        viewBox="0 0 120 180"
        role="img"
        :aria-label="`${book.label}书`"
      >
        <rect x="6" y="4" width="108" height="172" rx="10" fill="#3f6b52" />
        <rect x="18" y="4" width="96" height="172" rx="10" fill="#4f8463" />
        <rect x="18" y="4" width="14" height="172" fill="#3a6149" />
        <rect x="42" y="30" width="58" height="46" rx="6" fill="#f6e7c3" opacity="0.92" />
        <path d="M52 46h38M52 58h26" stroke="#3f6b52" stroke-width="5" stroke-linecap="round" />
        <path d="M52 84c8 0 10 6 18 6s10-6 18-6" stroke="#f6e7c3" stroke-width="4" fill="none" stroke-linecap="round" />
        <rect x="42" y="120" width="58" height="8" rx="4" fill="#c9a227" opacity="0.85" />
        <rect x="42" y="136" width="40" height="8" rx="4" fill="#c9a227" opacity="0.6" />
      </svg>

      <span class="shelf-book__title">{{ book.label }}</span>
      <span class="shelf-book__hint">{{ book.hint }}</span>
    </button>
    <span class="shelf-board" aria-hidden="true"></span>
  </div>
</template>

<style scoped>
/* The shelf itself is drawn by ShelfPicker's rules; these are the two things
   this row needs on top of them: five columns, and a drawn cover. */
.practice-shelf {
  grid-template-columns: repeat(5, minmax(0, 1fr));
  padding-bottom: 2.2rem;
}

/* A drawn cover has no painted contact shadow to sit in, so it needs its own
   frame: the same 2:3 box, a leather tint, and the shelf's shadow. The painted
   covers leave a margin inside their box; this one fills it, so it is scaled
   down to read at the same weight. */
.shelf-book__art--drawn {
  width: min(100%, 104px);
  border-radius: 8px;
  background: #4f8463;
  box-shadow: 0 10px 10px rgb(40 24 8 / 26%);
}

@media (max-width: 900px) {
  .practice-shelf { grid-template-columns: repeat(3, minmax(0, 1fr)); }
}

@media (max-width: 620px) {
  .practice-shelf { grid-template-columns: repeat(2, minmax(0, 1fr)); }
}
</style>
