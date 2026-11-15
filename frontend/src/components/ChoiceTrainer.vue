<script setup lang="ts">
/**
 * Multiple-choice trainer. Options come from the server with no correctness
 * marker, so there is nothing in the DOM or in local state that reveals the
 * answer. Submitting only sends the chosen option id; the server grades.
 */
import { computed, nextTick, ref, watch } from 'vue'
import type { ChoiceQuestion } from '../types/learning'
import { useRuneSurface } from '../composables/useRuneSurface'

const { surface } = useRuneSurface('choice')

const props = defineProps<{
  question: ChoiceQuestion
  disabled?: boolean
  /**
   * The server's verdict for the option just chosen. The chosen plate turns
   * green when it was right; when it was wrong it turns red and the plate that
   * carries the answer turns green, so the correction is read off the card
   * rather than announced in a sheet underneath it.
   */
  outcome?: 'correct' | 'wrong' | null
  /** The server's corrected word; only used to find the right plate. */
  correctLabel?: string | null
  /**
   * The pick was wrong and the card is waiting. It shakes, it keeps a red
   * halo, and the whole card becomes the way on — no sheet, no button.
   */
  missed?: boolean
  /** Right, and the card says so the same way a miss does, in green. */
  hit?: boolean
}>()

const emit = defineEmits<{
  (event: 'answer', optionId: string): void
  (event: 'continue'): void
}>()

const wordOptions = computed(() => props.question.options.length > 0
  && props.question.options.every((option) => {
    const text = (option.label ?? '').trim()
    return text.length > 0 && text.length <= 18 && !text.includes(' ')
  }))

const selected = ref<string | null>(null)
const promptHeading = ref<HTMLElement | null>(null)

/**
 * `option_count` is the server's authority. Small wordbooks can legitimately
 * return fewer than four options; the UI only verifies that the declared count
 * matches the rendered labels and that labels are non-empty and distinct.
 */
const optionsWellFormed = computed(() => {
  const options = props.question.options
  if (props.question.optionCount < 1 || options.length !== props.question.optionCount) {
    return false
  }
  const ids = new Set(options.map((option) => option.optionId))
  const labels = new Set(options.map((option) => option.label.trim()))
  return labels.size === options.length && !labels.has('') && ids.size === options.length
})

watch(
  () => props.question.questionId,
  () => {
    selected.value = null
    // Focus follows the new prompt; the radios of the old card are gone, so
    // leaving focus behind would strand keyboard users.
    void nextTick(() => promptHeading.value?.focus())
  },
)

/** Which plate carries which mark, once the server has graded. */
function plateState(option: { optionId: string; label: string }): 'right' | 'wrong' | null {
  if (!props.outcome) return null
  const chosen = selected.value === option.optionId
  if (props.outcome === 'correct') return chosen ? 'right' : null
  // The server only names the answer when the pick was wrong, so the pair of
  // marks is only ever drawn on a miss.
  const answer = props.correctLabel?.trim().toLowerCase()
  if (answer && option.label.trim().toLowerCase() === answer) return 'right'
  return chosen ? 'wrong' : null
}

function choose(optionId: string): void {
  if (props.disabled || !optionsWellFormed.value) {
    return
  }
  // Choosing is the answer: no separate submit step.
  selected.value = optionId
  emit('answer', optionId)
}
</script>

<template>
  <section
    class="study-card study-card--choice rune-surface"
    :class="{ 'is-missed': props.missed, 'is-hit': props.hit }"
    :style="surface"
    :role="props.missed ? 'button' : undefined"
    :tabindex="props.missed ? 0 : undefined"
    :aria-label="props.missed ? '回答错误，点一下进入下一题' : undefined"
    aria-labelledby="choice-prompt"
    @click="props.missed && emit('continue')"
    @keydown.enter.prevent="props.missed && emit('continue')"
    @keydown.space.prevent="props.missed && emit('continue')"
  >
    <div class="choice-head">
      <h2 id="choice-prompt" ref="promptHeading" class="choice-head__prompt" tabindex="-1">{{ props.question.prompt }}</h2>
      <p v-if="props.question.phonetic" class="choice-head__phonetic">{{ props.question.phonetic }}</p>
    </div>

    <p v-if="!optionsWellFormed" class="alert alert-warning" role="alert">
      选项暂时不可用，请稍后重试。
      本页不会按这份数据判分，请刷新或联系管理员；提交按钮保持不可用。
    </p>

    <fieldset
      v-else
      class="choice-list"
      :class="{ 'choice-list--words': wordOptions }"
      :disabled="props.disabled"
    >
      <legend class="visually-hidden">选择一个答案</legend>
      <label
        v-for="(option, index) in props.question.options"
        :key="option.optionId"
        class="choice-option"
        :class="{
          'choice-option--selected': selected === option.optionId,
          'choice-option--right': plateState(option) === 'right',
          'choice-option--wrong': plateState(option) === 'wrong',
        }"
      >
        <input
          type="radio"
          :name="`choice-${props.question.questionId}`"
          :value="option.optionId"
          :checked="selected === option.optionId"
          @change="choose(option.optionId)"
        />
        <span class="choice-option__face">
          <span class="choice-option__mark" aria-hidden="true">{{ String.fromCharCode(65 + index) }}</span>
          <span class="choice-option__label">{{ option.label }}</span>
          <span class="choice-option__tick" aria-hidden="true">
            <svg class="choice-option__yes" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3.4" stroke-linecap="round" stroke-linejoin="round">
              <path d="M5 13l4.5 4.5L19 7" />
            </svg>
            <svg class="choice-option__no" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3.4" stroke-linecap="round" stroke-linejoin="round">
              <path d="M6.5 6.5 17.5 17.5" />
              <path d="M17.5 6.5 6.5 17.5" />
            </svg>
          </span>
        </span>
      </label>
    </fieldset>
  </section>
</template>

<style scoped>
.study-card--choice {
  display: grid;
  gap: 1.2rem;
  max-width: 720px;
  margin: 0 auto;
  padding: 30px 26px;
  /* The slab is generated artwork used as a 9-slice source: the chipped edge
     and the carved groove sit in the border band, only the flat middle
     stretches. The filled colour is the stone under the image, so a slow load
     never flashes the page background. */
  border: 0;
  border-style: solid;
  border-width: 46px;
  border-color: transparent;
  border-image-source: url('../assets/halloween/card/slab-biscuit.png');
  border-image-slice: 12% fill;
  border-image-width: 46px;
  border-image-repeat: stretch;
  border-radius: 0;
  /* The colour is the stone under the image. Clipped to the padding box so it
     cannot show as a rectangle through the chipped edge. */
  background: #e8c58a;
  background-clip: padding-box;
  box-shadow: none;
  color: #5a3a16;
}

.choice-head {
  display: grid;
  gap: 0.4rem;
  justify-items: center;
  text-align: center;
}

.choice-head__prompt {
  margin: 0;
  font-family: Georgia, 'Times New Roman', serif;
  font-size: clamp(1.9rem, 5vw, 2.8rem);
  font-weight: 700;
  line-height: 1.15;
  letter-spacing: -0.02em;
  color: #5a3a16;
}

.choice-head__phonetic {
  margin: 0;
  font-family: ui-monospace, Consolas, monospace;
  font-size: 0.94rem;
  color: #6c573a;
}

/* Options are answer tiles on the table, not a vertical form list. */
.choice-list {
  display: grid;
  /* Columns are the plate's own width, so the pair sits together in the middle
     of the slab instead of each plate floating at its far end. */
  grid-template-columns: repeat(2, 280px);
  justify-content: center;
  gap: 0.9rem 1.6rem;
  margin: 0;
  padding: 0;
  border: 0;
  /* A fieldset's default min-inline-size is min-content, which in a grid
     collapses it to the width of its shortest word. The bars need the row. */
  min-inline-size: 0;
  width: 100%;
}

.choice-list--words { grid-template-columns: repeat(2, minmax(0, 1fr)); }

.choice-option {
  position: relative;
  display: block;
  cursor: pointer;
}

.choice-option input {
  position: absolute;
  width: 1px;
  height: 1px;
  opacity: 0;
  pointer-events: none;
}

/* Each option is a fixed-length stone plate. It used to be a bar stretched to
   whatever the column gave it, which made a four-letter word sit in a 370px
   slab and pushed the letter marker to the far left, out of the reading line.
   One length for every option: the word is the thing being read. */
.study-card--choice .choice-option {
  display: block;
  width: 280px;
  height: 84px;
  margin-inline: auto;
  border: 0 !important;
  border-radius: 0;
  background-color: transparent;
  background-image: url('../assets/halloween/card/option-plate-day.png');
  background-position: center;
  background-repeat: no-repeat;
  background-size: 100% 100%;
  box-shadow: none;
  filter: none;
}

html[data-theme='night'] .study-card--choice .choice-option {
  background-image: url('../assets/halloween/card/option-plate-night.png');
}

.choice-option__face {
  position: relative;
  display: grid;
  /* The letter is a small mark at the left; the word owns the middle. */
  grid-template-columns: auto minmax(0, 1fr) auto;
  gap: 0.55rem;
  align-items: center;
  height: 100%;
  width: 100%;
  padding: 0.4rem 0.9rem;
}

.study-card--choice .choice-option:hover { filter: brightness(1.06); }
.study-card--choice .choice-option:active { filter: brightness(0.95); }

/* Picked: the plate brightens and the ring appears; the plate itself is the
   artwork and is never repainted. */
.study-card--choice .choice-option--selected { filter: brightness(1.1); }
.study-card--choice .choice-option--selected .choice-option__face::after {
  content: '';
  position: absolute;
  inset: 6px;
  border-radius: 14px;
  box-shadow: 0 0 0 2px var(--g-orange, #ff9600);
  pointer-events: none;
}

.choice-option__label {
  grid-column: 2;
  font-size: 1.28rem;
  font-weight: 800;
  color: #5a3a16;
  line-height: 1.3;
  letter-spacing: 0.01em;
  text-align: center;
  overflow-wrap: anywhere;
}

html[data-theme='night'] .choice-option__label { color: #f3e9d2; }

/* The letter belongs to the plate: a stamped monogram at its left end,
   pressed into the paper rather than a badge laid on top. The word keeps the
   middle of the plate to itself. */
/* The letter is a stamp pressed into the plate's left end: a hairline seal
   with the letter cut into it, set well clear of the plate's rounded edge. */
.choice-option__mark {
  justify-self: start;
  display: grid;
  place-items: center;
  width: 30px;
  height: 30px;
  margin-left: 16px;
  border: 1.5px solid currentColor;
  border-radius: 8px;
  font-family: Georgia, 'Times New Roman', serif;
  font-size: 0.98rem;
  font-weight: 700;
  line-height: 1;
  color: #a9885a;
  box-shadow: inset 0 1px 0 rgb(255 255 255 / 55%), 0 1px 0 rgb(255 255 255 / 55%);
}

html[data-theme='night'] .choice-option__mark {
  color: #b9a4e6;
  box-shadow: inset 0 1px 0 rgb(255 255 255 / 12%), 0 1px 0 rgb(0 0 0 / 45%);
}

.choice-option--right .choice-option__mark { color: #2f6b2c; }
.choice-option--wrong .choice-option__mark { color: #9c2b22; }

.choice-option__tick {
  grid-column: 3;
  display: grid;
  place-items: center;
  width: 20px;
  height: 22px;
  border-radius: 999px;
  background: #c98a2e;
  color: #fff8e8;
  opacity: 0;
  transform: scale(0.5);
  transition: opacity 160ms ease, transform 200ms cubic-bezier(0.2, 0.9, 0.25, 1.4);
}

.choice-option__tick svg { width: 14px; height: 14px; }

.choice-option--selected .choice-option__face { filter: none; }

.choice-option--selected .choice-option__tick {
  opacity: 1;
  transform: scale(1);
}

.choice-option input:focus-visible + .choice-option__face {
  outline: 3px solid #1cb0f6;
  outline-offset: 3px;
}

.choice-list:disabled .choice-option { cursor: not-allowed; opacity: 0.6; }

/* The verdict is painted on the plates, not announced below the card: the
   answer's plate goes green, and a wrong pick goes red beside it. The colour
   is multiplied over the plate art so the carved edge and grain stay visible
   under it — a flat fill would read as a different, flatter object. */
.choice-option::after {
  content: '';
  position: absolute;
  inset: 6px;
  border-radius: 9px;
  opacity: 0;
  pointer-events: none;
  mix-blend-mode: multiply;
  transition: opacity 160ms ease;
}

.choice-option--right::after { background: #58b552; opacity: 0.58; }
.choice-option--wrong::after { background: #df4f42; opacity: 0.5; }

/* The mark on the plate is the verdict, not the selection: a right plate keeps
   the tick, a wrong one swaps it for a cross and closes on the same red. */
.choice-option--right .choice-option__tick {
  opacity: 1;
  transform: scale(1);
  background: #2f7a2f;
}

.choice-option__no { display: none; }

.choice-option--wrong .choice-option__tick {
  opacity: 1;
  transform: scale(1);
  background: #a83232;
}

.choice-option--wrong .choice-option__yes { display: none; }
.choice-option--wrong .choice-option__no { display: block; }

@media (prefers-reduced-motion: reduce) {
  .choice-option__face,
  .choice-option__tick { transition: none; }
}

@media (max-width: 620px) {
  .choice-list,
  .choice-list--words { grid-template-columns: 1fr; }
}
</style>
