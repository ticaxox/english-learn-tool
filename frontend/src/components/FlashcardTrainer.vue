<script setup lang="ts">
/**
 * Flashcard trainer. Renders the server-provided front, and only reveals the
 * back after an explicit flip. The back is never rendered into the DOM before
 * that point, so it cannot be read from the page source.
 */
import { computed, nextTick, ref, watch } from 'vue'
import type { FlashcardQuestion, FlashcardRating } from '../types/learning'

const props = defineProps<{
  question: FlashcardQuestion
  disabled?: boolean
}>()

const emit = defineEmits<{
  (event: 'rate', rating: FlashcardRating): void
  (event: 'reveal'): void
  (event: 'master'): void
}>()

const revealed = ref(false)
const frontHeading = ref<HTMLElement | null>(null)
const backRegion = ref<HTMLElement | null>(null)

watch(
  () => props.question.questionId,
  () => {
    revealed.value = false
    // The next card replaces the previous one without a navigation, so focus
    // would otherwise stay on a button from a card that no longer exists.
    // Moving it to the new prompt keeps keyboard and screen-reader users at the
    // content instead of at a dead control.
    void nextTick(() => frontHeading.value?.focus())
  },
)

const canRate = computed(() => revealed.value && !props.disabled)

function flip(): void {
  if (revealed.value) {
    return
  }
  revealed.value = true
  emit('reveal')
  // The flip button unmounts, so focus would silently fall back to <body>.
  // Move it to the newly revealed answer instead of losing it.
  void nextTick(() => backRegion.value?.focus())
}

function rate(rating: FlashcardRating): void {
  if (!canRate.value) {
    return
  }
  emit('rate', rating)
}
</script>

<template>
  <section class="study-card" aria-labelledby="flashcard-front">
    <p class="study-card__meta">
      <span class="study-badge">翻卡</span>
      <span>剩余 {{ props.question.remaining }} 张</span>
    </p>

    <h2 id="flashcard-front" ref="frontHeading" class="study-card__word" tabindex="-1">{{ props.question.front }}</h2>
    <p v-if="props.question.phonetic" class="study-card__phonetic">{{ props.question.phonetic }}</p>

    <!--
      Flipping stays available while a submission is in flight: blocking it would
      leave the learner staring at a card whose answer they already know. Only
      the rating actions are gated by `disabled`.
    -->
    <DivButton
      v-if="!revealed"
      class="button study-card__flip"
      type="button"
      @click="flip"
    >
      翻到背面
    </DivButton>

    <div v-else ref="backRegion" class="study-card__back" aria-live="polite" tabindex="-1">
      <p v-if="props.question.partOfSpeech" class="study-card__phonetic">{{ props.question.partOfSpeech }}</p>
      <p v-if="props.question.back" class="study-card__definition">{{ props.question.back }}</p>
      <p v-else class="inline-note">暂时没有释义，可以按自己的印象选择。</p>
      <p v-if="props.question.example" class="study-card__example">{{ props.question.example }}</p>
      <div class="button-row">
        <DivButton class="button-secondary" type="button" :disabled="!canRate" @click="rate('again')">
          无印象
        </DivButton>
        <DivButton class="button-secondary" type="button" :disabled="!canRate" @click="rate('good')">
          有印象
        </DivButton>
        <DivButton
          class="button-secondary"
          type="button"
          :disabled="props.disabled"
          @click="emit('master')"
        >
          已记住
        </DivButton>
      </div>
    </div>
  </section>
</template>
