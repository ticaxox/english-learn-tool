<script setup lang="ts">
/**
 * The moment after an answer.
 *
 * Every graded answer gets the same beat: a band slides up, says whether it
 * was right, shows the word if it wasn't, and offers one big Continue. Correct
 * answers are not silently advanced — that beat is where the streak is felt.
 *
 * The verdict and the correct word come from the server's StudyFeedback; this
 * component never grades anything.
 */
import { computed, nextTick, ref, watch } from 'vue'
import SpeakButton from './SpeakButton.vue'

const props = defineProps<{
  /** null while the sheet is closed. */
  verdict: { correct: boolean; headline: string } | null
  word: string | null
  phonetic: string | null
  partOfSpeech: string | null
  meaning: string | null
  combo: number
  busy?: boolean
}>()

const emit = defineEmits<{ (event: 'continue'): void }>()

const continueButton = ref<HTMLButtonElement | null>(null)

watch(
  () => props.verdict,
  (next) => {
    if (next) void nextTick(() => continueButton.value?.focus())
  },
)

const kind = computed(() => (props.verdict?.correct ? 'correct' : 'wrong'))
</script>

<template>
  <Transition name="lesson-sheet">
    <section v-if="verdict" class="lesson-feedback" :class="`is-${kind}`" role="status" aria-live="polite">
      <div class="lesson-feedback__inner">
        <div class="lesson-feedback__lead">
          <span class="lesson-feedback__mark" aria-hidden="true">
            <svg v-if="verdict.correct" viewBox="0 0 24 24"><path d="M4.5 12.5 9.5 17.5 19.5 6.5" /></svg>
            <svg v-else viewBox="0 0 24 24"><path d="M7 7 17 17" /><path d="M17 7 7 17" /></svg>
          </span>
          <div class="lesson-feedback__copy">
            <p class="lesson-feedback__headline">
              {{ verdict.headline }}
              <span v-if="verdict.correct && combo >= 2" class="lesson-feedback__combo">连对 {{ combo }}</span>
            </p>
            <p v-if="!verdict.correct && word" class="lesson-feedback__answer">
              <span class="lesson-feedback__answer-label">正确答案</span>
              <strong>{{ word }}</strong>
              <span v-if="phonetic" class="lesson-feedback__phonetic">{{ phonetic }}</span>
              <SpeakButton :text="word" />
            </p>
            <p v-if="!verdict.correct && meaning" class="lesson-feedback__meaning">
              <span v-if="partOfSpeech" class="lesson-feedback__pos">{{ partOfSpeech }}</span>
              {{ meaning }}
            </p>
          </div>
        </div>

        <button ref="continueButton" class="lesson-feedback__continue" type="button" :disabled="busy" @click="emit('continue')">
          {{ busy ? '记录中…' : '继续' }}
        </button>
      </div>
    </section>
  </Transition>
</template>

<style scoped>
/* A band, not a card. It belongs to the bottom edge of the run the way a
   game's result strip does — flat fill, square shoulders, full width.
   `shortcut: the band is in normal flow, so very long explanations push it
   down instead of overlaying the card; revisit if that ever happens.` */
.lesson-feedback {
  position: sticky;
  bottom: 0;
  margin-top: 1rem;
  border-radius: 18px;
  border: 0;
  padding: 1rem 1.15rem 1.1rem;
}

.lesson-feedback.is-correct {
  background: var(--g-green-soft, #ddf7e1);
  color: #174d21;
}

.lesson-feedback.is-wrong {
  background: var(--g-red-soft, #ffe4e0);
  color: #5d1b1b;
}

.lesson-feedback__inner {
  display: flex;
  align-items: center;
  gap: 1rem;
  flex-wrap: wrap;
}

.lesson-feedback__lead { display: flex; align-items: flex-start; gap: 0.8rem; flex: 1; min-width: 14rem; }

.lesson-feedback__mark {
  width: 2.4rem;
  height: 2.4rem;
  flex: none;
  display: grid;
  place-items: center;
  border-radius: 50%;
  background: rgb(255 255 255 / 62%);
}

.lesson-feedback__mark svg {
  width: 1.25rem;
  height: 1.25rem;
  fill: none;
  stroke: currentColor;
  stroke-width: 3;
  stroke-linecap: round;
  stroke-linejoin: round;
}

.lesson-feedback.is-wrong .lesson-feedback__mark svg { stroke-width: 2.6; }

.lesson-feedback__copy { min-width: 0; }

.lesson-feedback__headline {
  margin: 0;
  font-size: 1.05rem;
  font-weight: 800;
  letter-spacing: -0.01em;
  display: flex;
  align-items: center;
  gap: 0.5rem;
  flex-wrap: wrap;
}

.lesson-feedback__combo {
  font-size: 0.75rem;
  font-weight: 700;
  padding: 0.1rem 0.45rem;
  border-radius: 999px;
  background: rgb(255 255 255 / 60%);
  color: currentColor;
}

.lesson-feedback__answer {
  margin: 0.35rem 0 0;
  display: flex;
  align-items: baseline;
  gap: 0.5rem;
  flex-wrap: wrap;
  font-size: 0.95rem;
}

.lesson-feedback__answer-label { font-size: 0.78rem; font-weight: 700; opacity: 0.7; }
.lesson-feedback__answer strong { font-size: 1.15rem; letter-spacing: -0.01em; }
.lesson-feedback__phonetic { font-size: 0.85rem; opacity: 0.8; }

.lesson-feedback__meaning {
  margin: 0.25rem 0 0;
  font-size: 0.9rem;
  display: flex;
  align-items: baseline;
  gap: 0.4rem;
  flex-wrap: wrap;
}

.lesson-feedback__pos {
  font-size: 0.72rem;
  font-weight: 700;
  padding: 0.05rem 0.4rem;
  border-radius: 6px;
  background: rgb(255 255 255 / 55%);
}

.lesson-feedback__continue {
  flex: none;
  min-width: 8.5rem;
  height: 2.9rem;
  padding: 0 1.4rem;
  border: 2px solid;
  border-radius: 14px;
  font: inherit;
  font-size: 1rem;
  font-weight: 800;
  cursor: pointer;
  transition: transform 120ms ease, filter 120ms ease;
}

/* Deeper than the brand green: white on #2fb344 is 2.74:1, which fails for
   a 16px label. #1d7d2c carries the same hue at 5.2:1. */
.lesson-feedback.is-correct .lesson-feedback__continue {
  background: #1d7d2c;
  border-color: #166326;
  color: #fff;
  box-shadow: 0 4px 0 #166326;
}

.lesson-feedback.is-wrong .lesson-feedback__continue {
  background: #b83030;
  border-color: #8f2525;
  color: #fff;
  box-shadow: 0 4px 0 #8f2525;
}

.lesson-feedback__continue:hover { filter: brightness(1.05); }
.lesson-feedback__continue:active { transform: translateY(3px); box-shadow: none; }
.lesson-feedback__continue:disabled { filter: grayscale(0.3); opacity: 0.7; cursor: progress; }
.lesson-feedback__continue:focus-visible { outline: 3px solid var(--ui-ink, #35240f); outline-offset: 3px; }

.lesson-sheet-enter-active,.lesson-sheet-leave-active { transition: transform 240ms cubic-bezier(0.2,0.9,0.25,1.05), opacity 200ms ease; }
.lesson-sheet-enter-from,.lesson-sheet-leave-to { transform: translateY(28px); opacity: 0; }

@media (prefers-reduced-motion: reduce) {
  .lesson-sheet-enter-active, .lesson-sheet-leave-active { transition: none; }
}

@media (max-width: 560px) {
  .lesson-feedback__inner { flex-direction: column; align-items: stretch; }
  .lesson-feedback__continue { width: 100%; }
}
</style>
