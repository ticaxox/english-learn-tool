<script setup lang="ts">
/**
 * Multiple-choice trainer. Options come from the server with no correctness
 * marker, so there is nothing in the DOM or in local state that reveals the
 * answer. Submitting only sends the chosen option id; the server grades.
 */
import { computed, nextTick, ref, watch } from 'vue'
import type { ChoiceQuestion } from '../types/learning'
import { useRuneSurface } from '../composables/useRuneSurface'
import plateDayA from '../assets/halloween/card/option-day-a.webp'
import plateDayB from '../assets/halloween/card/option-day-b.webp'
import plateDayC from '../assets/halloween/card/option-day-c.webp'
import plateDayD from '../assets/halloween/card/option-day-d.webp'
import plateNightA from '../assets/halloween/card/option-night-a.webp'
import plateNightB from '../assets/halloween/card/option-night-b.webp'
import plateNightC from '../assets/halloween/card/option-night-c.webp'
import plateNightD from '../assets/halloween/card/option-night-d.webp'

/** One drawing per letter per theme: the letter is cut into the plate. */
const PLATE_ART = {
  day: [plateDayA, plateDayB, plateDayC, plateDayD],
  night: [plateNightA, plateNightB, plateNightC, plateNightD],
}

function plateArt(index: number): Record<string, string> {
  return {
    '--plate-day': `url(${PLATE_ART.day[index]})`,
    '--plate-night': `url(${PLATE_ART.night[index]})`,
  }
}

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
          'choice-option--art': index < 4,
        }"
        :style="index < 4 ? plateArt(index) : undefined"
      >
        <input
          type="radio"
          :name="`choice-${props.question.questionId}`"
          :value="option.optionId"
          :checked="selected === option.optionId"
          @change="choose(option.optionId)"
        />
        <span class="choice-option__face">
          <span class="choice-option__mark" aria-hidden="true">{{ index >= 4 ? String.fromCharCode(65 + index) : '' }}</span>
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
        <span v-if="plateState(option)" class="choice-option__stamp" aria-hidden="true"></span>
        <span v-if="props.hit && plateState(option) === 'right'" class="choice-option__burst" aria-hidden="true"></span>
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
  border-image-source: url('../assets/halloween/card/slab-biscuit.webp');
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
/* The plate itself is styled in controls.css, next to the rest of the drill
   surfaces; the option only carries its own inner layout. */
.choice-option__face {
  position: relative;
  display: grid;
  /* The letter is a small mark at the left; the word owns the middle. The left
     padding is the medallion's centre: 46px from the plate's edge. */
  grid-template-columns: auto minmax(0, 1fr) auto;
  gap: 0.55rem;
  align-items: center;
  height: 100%;
  width: 100%;
  padding: 0.3rem 1rem 0.3rem 18px;
}

.study-card--choice .choice-option:hover { filter: brightness(1.06); }
.study-card--choice .choice-option:active { filter: brightness(0.95); }

/* Picked: the plate brightens and the ring appears; the plate itself is the
   artwork and is never repainted. */
.study-card--choice .choice-option--selected { filter: brightness(1.1); }
.study-card--choice .choice-option--selected .choice-option__face::after {
  content: '';
  position: absolute;
  inset: 0;
  border-radius: 2px;
  box-shadow: inset 0 0 0 2.5px var(--g-orange, #ff9600);
  pointer-events: none;
}

.choice-option__label {
  grid-column: 2;
  font-size: 1.28rem;
  font-weight: 800;
  /* The word is the thing being read, so it is set bold by default and
     thickened a breath further than the face's own bold cut. */
  -webkit-text-stroke: 0.35px currentColor;
  color: #5a3a16;
  line-height: 1.3;
  letter-spacing: 0.01em;
  text-align: center;
  overflow-wrap: anywhere;
}

html[data-theme='night'] .choice-option__label { color: #f3e9d2; }

/* The letter is an engraved initial rather than a plain capital: a swashed
   display serif, struck into the coin with a light lip and a dark cut. */
.choice-option__mark {
  justify-self: start;
  display: grid;
  place-items: center;
  width: 40px;
  height: 40px;
  font-family: 'Almendra Display', 'Palatino Linotype', 'Book Antiqua', Georgia, serif;
  font-size: 2.35rem;
  font-weight: 700;
  line-height: 1;
  color: #211207;
  /* Almendra is drawn with hairlines; at this size the stem would read as
     a smudge of brown, so the ink is thickened to its own colour. */
  -webkit-text-stroke: 0.6px currentColor;
}

html[data-theme='night'] .choice-option__mark {
  color: #f0e5cf;
}

.choice-option--right .choice-option__mark { color: #2f6b2c; }
.choice-option--wrong .choice-option__mark { color: #9c2b22; }

/**
 * The verdict is stamped on rather than tinted on: an inked ring with a check
 * or a cross, pressed into the plate in one beat. It replaces the small picked
 * badge, so the pick is read from the stamp and not from two markers at once.
 */
.choice-option__stamp {
  position: absolute;
  right: 12px;
  top: 50%;
  width: 46px;
  height: 46px;
  margin-top: -23px;
  background: center / contain no-repeat;
  opacity: 0;
  pointer-events: none;
  /* Above the verdict wash, or the stamp reads through it as mud. */
  z-index: 2;
}

.choice-option--right .choice-option__stamp {
  background-image: url('../assets/halloween/card/verdict-right-day.webp');
  animation: choiceStamp 260ms cubic-bezier(0.22, 0.9, 0.3, 1.12) forwards;
}

.choice-option--wrong .choice-option__stamp {
  background-image: url('../assets/halloween/card/verdict-wrong-day.webp');
  animation: choiceStamp 260ms cubic-bezier(0.22, 0.9, 0.3, 1.12) forwards;
}

html[data-theme='night'] .choice-option--right .choice-option__stamp {
  background-image: url('../assets/halloween/card/verdict-right-night.webp');
}

html[data-theme='night'] .choice-option--wrong .choice-option__stamp {
  background-image: url('../assets/halloween/card/verdict-wrong-night.webp');
}

@keyframes choiceStamp {
  0% { opacity: 0; transform: rotate(-14deg) scale(1.7); }
  55% { opacity: 1; transform: rotate(-8deg) scale(0.95); }
  100% { opacity: 1; transform: rotate(-8deg) scale(1); }
}

/* Crumbs are what this product pays in, so a right answer scatters them
   around the stamp at the plate's right end, clear of the word. */
.choice-option__burst {
  position: absolute;
  right: 0;
  top: 50%;
  width: 112px;
  height: 112px;
  margin-top: -56px;
  background: url('../assets/halloween/card/burst-crumbs.webp') 0 0 / 896px 112px no-repeat;
  pointer-events: none;
  z-index: 1;
  /* Starts once the pieces have left the middle: the opening frame is a
     tight clump that would read as a smudge on the plate. */
  animation: choiceCrumbBurst 520ms steps(6) forwards;
}

@keyframes choiceCrumbBurst {
  from { background-position: -224px 0; }
  to { background-position: -896px 0; }
}

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

/* One marker at a time: once the server has spoken, the stamp carries the
   verdict and the little picked badge steps out of its way. */
.choice-option--right .choice-option__tick,
.choice-option--wrong .choice-option__tick {
  opacity: 0;
  transform: scale(0.5);
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
  inset: 0;
  border-radius: 2px;
  opacity: 0;
  pointer-events: none;
  mix-blend-mode: multiply;
  transition: opacity 160ms ease;
}

.choice-option--right::after { background: #58b552; opacity: 0.58; }
.choice-option--wrong::after { background: #df4f42; opacity: 0.5; }

/* On the dark plate a multiply wash only makes it darker; the verdict has to
   lighten instead, or the win and the loss read as the same shade. */
html[data-theme='night'] .choice-option--right::after {
  background: #4bc064;
  opacity: 0.34;
  mix-blend-mode: screen;
}

html[data-theme='night'] .choice-option--wrong::after {
  background: #b0433a;
  opacity: 0.4;
  mix-blend-mode: screen;
}

.choice-option--wrong .choice-option__no { display: block; }

@media (prefers-reduced-motion: reduce) {
  .choice-option__face,
  .choice-option__tick { transition: none; }
  /* The stamp lands without travel, and the crumbs do not fly at all. */
  .choice-option__stamp { animation: none; opacity: 1; transform: rotate(-8deg); }
  .choice-option__burst { display: none; }
}

@media (max-width: 620px) {
  .choice-list,
  .choice-list--words { grid-template-columns: 1fr; }
}
</style>
