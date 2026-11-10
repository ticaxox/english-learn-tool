<script setup lang="ts">
/**
 * Flashcard trainer as a physical card.
 *
 * The card has two real faces stacked in 3D and turns over on reveal. The back
 * is never rendered into the DOM before the reveal, so it cannot be read from
 * the page source — the same guarantee the previous layout gave.
 *
 * `.study-card` and role="button" stay as the contract the tests and screen
 * readers already use.
 */
import { computed, nextTick, ref, watch } from 'vue'
import SpeakButton from './SpeakButton.vue'
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
    void nextTick(() => frontHeading.value?.focus())
  },
)

const canRate = computed(() => revealed.value && !props.disabled)

function flip(): void {
  if (revealed.value) return
  revealed.value = true
  emit('reveal')
  // The flip button unmounts, so focus would silently fall back to <body>.
  void nextTick(() => backRegion.value?.focus())
}

function rate(rating: FlashcardRating): void {
  if (!canRate.value) return
  emit('rate', rating)
}
</script>

<template>
  <section
    class="study-card"
    :class="{ 'is-revealed': revealed }"
    :aria-labelledby="revealed ? 'flashcard-back' : 'flashcard-front'"
    :role="revealed ? undefined : 'button'"
    :tabindex="revealed ? undefined : 0"
    @click="flip"
    @keydown.enter.prevent="flip"
    @keydown.space.prevent="flip"
  >
    <div class="flipstage">
      <div class="flipcard" :class="{ 'is-flipped': revealed }">
        <!-- Front: the word alone on a card face. -->
        <div class="flipface flipface--front">
          <span class="flipface__eyebrow">正面</span>
          <h2 id="flashcard-front" ref="frontHeading" class="flipface__word" tabindex="-1">
            {{ props.question.front }}
          </h2>
          <div class="flipface__phoneticrow">
            <SpeakButton :text="props.question.front" />
            <p v-if="props.question.phonetic" class="flipface__phonetic">{{ props.question.phonetic }}</p>
          </div>
          <span class="flipface__cue">点一下翻面</span>
        </div>

        <!-- Back: only mounted after the reveal. -->
        <div class="flipface flipface--back">
          <template v-if="revealed">
            <span class="flipface__eyebrow">背面</span>
            <div id="flashcard-back" ref="backRegion" class="flipface__body study-card__back" aria-live="polite" tabindex="-1">
              <p class="flipface__meaning">
                <span v-if="props.question.partOfSpeech" class="flipface__pos">{{ props.question.partOfSpeech }}</span>
                <span v-if="props.question.back" class="flipface__definition">{{ props.question.back }}</span>
                <span v-else class="inline-note">暂时没有释义，可以按自己的印象选择。</span>
              </p>
              <p v-if="props.question.example" class="flipface__example">{{ props.question.example }}</p>
            </div>
          </template>
        </div>
      </div>
    </div>
  </section>

  <div v-if="revealed" class="button-row study-card__rating">
    <DivButton class="button-secondary" type="button" :disabled="!canRate" @click="rate('again')">
      无印象
    </DivButton>
    <DivButton class="button-secondary" type="button" :disabled="!canRate" @click="rate('good')">
      有印象
    </DivButton>
    <DivButton class="button-secondary" type="button" :disabled="props.disabled" @click="emit('master')">
      已记住
    </DivButton>
  </div>
</template>

<style scoped>
/* The stage gives the card room to rotate without clipping its corners. */
.flipstage {
  perspective: 1600px;
  width: 100%;
  max-width: 620px;
  margin: 0 auto;
}

.flipcard {
  position: relative;
  display: grid;
  width: 100%;
  min-height: 380px;
  transform-style: preserve-3d;
  transition: transform 640ms cubic-bezier(0.2, 0.9, 0.25, 1.02);
}

.flipcard.is-flipped {
  transform: rotateY(180deg);
}

.flipface {
  grid-area: 1 / 1;
  display: grid;
  align-content: center;
  justify-items: center;
  gap: 0.8rem;
  padding: clamp(1.6rem, 4vw, 2.8rem);
  border: 2px solid #3b2a1a;
  border-radius: 20px;
  text-align: center;
  backface-visibility: hidden;
  -webkit-backface-visibility: hidden;
  /* A paper deck edge: a lighter inner rule inside the dark outline. */
  box-shadow:
    inset 0 0 0 6px #fffdf6,
    inset 0 0 0 8px #ecd9bb,
    0 10px 0 #d8c3a0,
    0 22px 34px -18px rgb(40 24 8 / 55%);
}

.flipface--front {
  background: linear-gradient(168deg, #fffdf6, #fff4e2 62%, #ffeacd);
}

.flipface--back {
  background: linear-gradient(168deg, #fffdf6, #eef8f0 62%, #ddf7e1);
  transform: rotateY(180deg);
}

.flipface__eyebrow {
  font-size: 0.7rem;
  font-weight: 800;
  letter-spacing: 0.22em;
  text-transform: uppercase;
  color: #a08a6a;
}

.flipface__word {
  margin: 0;
  font-family: Georgia, 'Times New Roman', serif;
  font-size: clamp(2.2rem, 7vw, 3.6rem);
  font-weight: 700;
  line-height: 1.1;
  letter-spacing: -0.02em;
  color: #2f2013;
}

.flipface__phoneticrow {
  display: flex;
  gap: 0.5rem;
  align-items: center;
}

.flipface__phonetic {
  margin: 0;
  font-family: ui-monospace, Consolas, monospace;
  font-size: 0.94rem;
  color: #7a6448;
}

.flipface__cue {
  margin-top: 0.4rem;
  font-size: 0.78rem;
  font-weight: 700;
  color: #b09a78;
  animation: cuePulse 2.4s ease-in-out infinite;
}

@keyframes cuePulse {
  50% { opacity: 0.45; }
}

.flipface__body {
  display: grid;
  gap: 1rem;
  outline: none;
}

.flipface__meaning {
  display: grid;
  gap: 0.35rem;
  margin: 0;
}

.flipface__pos {
  font-size: 0.82rem;
  font-weight: 700;
  color: #4a7a55;
  letter-spacing: 0.06em;
}

.flipface__definition {
  font-size: clamp(1.1rem, 2.6vw, 1.35rem);
  line-height: 1.55;
  color: #2f2013;
}

.flipface__example {
  margin: 0;
  padding: 0.8rem 1rem;
  border-left: 3px solid #9ec9a8;
  border-radius: 8px;
  background: rgb(255 255 255 / 66%);
  font-size: 0.95rem;
  line-height: 1.6;
  color: #4b3a26;
  text-align: left;
}

.study-card {
  display: block;
  padding: 0;
  border: 0;
  background: none;
  box-shadow: none;
}

.study-card:not(.is-revealed) { cursor: pointer; }

.study-card:focus-visible {
  outline: 3px solid #1cb0f6;
  outline-offset: 8px;
  border-radius: 24px;
}

.study-card__rating {
  justify-content: center;
  margin-top: 1.6rem;
}

@media (prefers-reduced-motion: reduce) {
  .flipcard { transition: none; }
  .flipface__cue { animation: none; }
}

@media (max-width: 620px) {
  .flipcard { min-height: 320px; }
}
</style>
