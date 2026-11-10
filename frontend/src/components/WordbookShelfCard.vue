<script setup lang="ts">
/**
 * One wordbook, as a book on the shelf.
 *
 * The card carries no buttons and no badges: the binding says what kind of book
 * it is — a private wordbook is bound in the pumpkin-vine paper, an
 * organisation one in green leather — and the name is written straight on the
 * cover. Everything else (the entries, and the actions on them) lives in the
 * dialog this opens.
 */
import { computed } from 'vue'
import ArtImage from './ArtImage.vue'
import { questionCard, wordbookCover } from '../assets/halloween'
import type { Wordbook } from '../api/wordbooks'

const props = defineProps<{ book: Wordbook }>()
const emit = defineEmits<{ detail: [] }>()

const cover = computed(() =>
  props.book.visibility === 'private' ? questionCard.frame : wordbookCover,
)
</script>

<template>
  <article
    class="wordbook-card"
    :class="[`wordbook-card--${book.visibility}`, { 'wordbook-card--active': book.is_active }]"
    role="button"
    tabindex="0"
    :aria-label="`${book.name}${book.is_active ? '，使用中' : ''}，打开查看词条`"
    @click="emit('detail')"
    @keydown.enter="emit('detail')"
    @keydown.space.prevent="emit('detail')"
  >
    <span class="wordbook-cover">
      <ArtImage class="wordbook-cover__art" :set="cover" />
      <span v-if="book.is_active" class="wordbook-cover__bookmark" aria-hidden="true"></span>
      <span class="wordbook-cover__name">{{ book.name }}</span>
    </span>
  </article>
</template>
