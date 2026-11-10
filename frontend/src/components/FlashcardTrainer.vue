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
import ArtImage from './ArtImage.vue'
import { questionCard } from '../assets/halloween'
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
        <!-- Front: the generated card frame IS the card. -->
        <div class="flipface flipface--front">
          <ArtImage class="flipface__frame" :set="questionCard.frame" />
          <div class="flipface__content">
            <h2 id="flashcard-front" ref="frontHeading" class="flipface__word" tabindex="-1">
              {{ props.question.front }}
            </h2>
            <div class="flipface__phoneticrow">
              <SpeakButton :text="props.question.front" />
              <p v-if="props.question.phonetic" class="flipface__phonetic">{{ props.question.phonetic }}</p>
            </div>
            <span class="flipface__cue">点一下翻面</span>
          </div>
        </div>

        <!-- Back: the generated card back, contents only after the reveal. -->
        <div class="flipface flipface--back">
          <ArtImage class="flipface__frame" :set="questionCard.frame" />
          <div class="flipface__content">
            <template v-if="revealed">
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
.flipstage {
  perspective: 1600px;
  width: 100%;
  max-width: 430px;
  margin: 0 auto;
}

.flipcard {
  position: relative;
  display: grid;
  width: 100%;
  aspect-ratio: 2 / 3;
  transform-style: preserve-3d;
  transition: transform 640ms cubic-bezier(0.2, 0.9, 0.25, 1.02);
}

.flipcard.is-flipped { transform: rotateY(180deg); }

/* No plate, no border, no radius: the artwork is the card. */
.flipface {
  grid-area: 1 / 1;
  position: relative;
  backface-visibility: hidden;
  -webkit-backface-visibility: hidden;
}

.flipface--back { transform: rotateY(180deg); }

.flipface__frame {
  display: block;
  width: 100%;
  height: 100%;
  object-fit: contain;
  filter: drop-shadow(0 14px 18px rgb(40 24 8 / 28%));
}

/* Content sits inside the frame's border band, which is ~11% on each side. */
.flipface__content {
  position: absolute;
  inset: 13% 15% 14%;
  display: grid;
  align-content: center;
  justify-items: center;
  gap: 0.55rem;
  text-align: center;
}

.flipface__word {
  margin: 0;
  font-family: Georgia, 'Times New Roman', serif;
  font-size: clamp(1.7rem, 4.6vw, 2.5rem);
  font-weight: 700;
  line-height: 1.15;
  letter-spacing: -0.02em;
  color: #2f2013;
  overflow-wrap: anywhere;
}

.flipface__phoneticrow {
  display: flex;
  gap: 0.4rem;
  align-items: center;
}

.flipface__phonetic {
  margin: 0;
  font-family: ui-monospace, Consolas, monospace;
  font-size: 0.88rem;
  color: #7a6448;
}

.flipface__cue {
  margin-top: 0.3rem;
  font-size: 0.72rem;
  font-weight: 700;
  letter-spacing: 0.06em;
  color: #b09a78;
  animation: cuePulse 2.4s ease-in-out infinite;
}

@keyframes cuePulse { 50% { opacity: 0.4; } }

.flipface__body {
  display: grid;
  gap: 0.7rem;
  outline: none;
}

.flipface__meaning {
  display: grid;
  gap: 0.3rem;
  margin: 0;
}

.flipface__pos {
  font-size: 0.76rem;
  font-weight: 700;
  letter-spacing: 0.06em;
  color: #4a7a55;
}

.flipface__definition {
  font-size: clamp(0.98rem, 2.2vw, 1.18rem);
  line-height: 1.5;
  color: #2f2013;
  overflow-wrap: anywhere;
}

/* A phrasebook line, not a tinted box. */
.flipface__example {
  margin: 0;
  padding-bottom: 0.4rem;
  border-bottom: 1.5px dotted #b7c9b9;
  font-family: Georgia, 'Times New Roman', serif;
  font-size: 0.86rem;
  font-style: italic;
  line-height: 1.6;
  color: #5a4732;
}

.study-card,
.personal-workspace .study-card,
.personal-workspace .memory-main-card .study-card,
.personal-workspace .memory-page .memory-main-card .study-card {
  display: block;
  padding: 0;
  border: 0 !important;
  border-radius: 0 !important;
  background: none !important;
  box-shadow: none !important;
}

.study-card:not(.is-revealed) { cursor: pointer; }

.study-card:focus-visible {
  outline: 3px solid #1cb0f6;
  outline-offset: 10px;
  border-radius: 20px;
}

.study-card__rating {
  justify-content: center;
  margin-top: 1.6rem;
}

@media (prefers-reduced-motion: reduce) {
  .flipcard { transition: none; }
  .flipface__cue { animation: none; }
}
</style>
