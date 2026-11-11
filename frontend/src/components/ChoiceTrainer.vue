<script setup lang="ts">
/**
 * Multiple-choice trainer. Options come from the server with no correctness
 * marker, so there is nothing in the DOM or in local state that reveals the
 * answer. Submitting only sends the chosen option id; the server grades.
 */
import { computed, nextTick, ref, watch } from 'vue'
import type { ChoiceQuestion } from '../types/learning'
import OptionBadge from './OptionBadge.vue'

const props = defineProps<{
  question: ChoiceQuestion
  disabled?: boolean
}>()

const emit = defineEmits<{
  (event: 'answer', optionId: string): void
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
  <section class="study-card study-card--choice" aria-labelledby="choice-prompt">
    <div class="choice-head">
      <span class="choice-head__eyebrow">选出正确释义</span>
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
        :class="{ 'choice-option--selected': selected === option.optionId }"
      >
        <input
          type="radio"
          :name="`choice-${props.question.questionId}`"
          :value="option.optionId"
          :checked="selected === option.optionId"
          @change="choose(option.optionId)"
        />
        <span class="choice-option__face">
          <OptionBadge :letter="String.fromCharCode(65 + index)" />
          <span class="choice-option__label">{{ option.label }}</span>
          <span class="choice-option__tick" aria-hidden="true">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3.4" stroke-linecap="round" stroke-linejoin="round">
              <path d="M5 13l4.5 4.5L19 7" />
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
  border-image-source: url('../assets/halloween/card/rune-slab-day.png');
  border-image-slice: 12% fill;
  border-image-width: 46px;
  border-image-repeat: stretch;
  border-radius: 0;
  /* The colour is the stone under the image. Clipped to the padding box so it
     cannot show as a rectangle through the chipped edge. */
  background: #d9c7a4;
  background-clip: padding-box;
  box-shadow: none;
  color: #3a2819;
}

.choice-head {
  display: grid;
  gap: 0.4rem;
  justify-items: center;
  text-align: center;
}

.choice-head__eyebrow {
  font-size: 0.7rem;
  font-weight: 800;
  letter-spacing: 0.2em;
  text-transform: uppercase;
  color: #7a6647;
}

.choice-head__prompt {
  margin: 0;
  font-family: Georgia, 'Times New Roman', serif;
  font-size: clamp(1.9rem, 5vw, 2.8rem);
  font-weight: 700;
  line-height: 1.15;
  letter-spacing: -0.02em;
  color: #3a2819;
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
  grid-template-columns: minmax(0, 1fr);
  gap: 0.75rem;
  margin: 0;
  padding: 0;
  border: 0;
  /* A fieldset's default min-inline-size is min-content, which in a grid
     collapses it to the width of its shortest word. The bars need the row. */
  min-inline-size: 0;
  width: 100%;
}

.choice-list--words { grid-template-columns: minmax(0, 1fr); }

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

/* Each option is its own stone bar. The parent selector is here for
   specificity: game-ui.css sets the same properties on .choice-option and wins
   on load order otherwise.
   The option is a block, not the workspace's three-column grid — that grid
   would put the face in a 38px column instead of letting it fill the bar. */
.study-card--choice .choice-option {
  display: block;
  border-style: solid;
  border-width: 12px 20px;
  border-color: transparent;
  border-image-source: url('../assets/halloween/card/rune-bar-day.png');
  /* `fill` so the bar's own stone face shows through: the artwork is the
     whole object, not a frame around a colour. */
  border-image-slice: 8% 4% fill;
  border-image-width: 12px 20px;
  border-image-repeat: stretch;
  border-radius: 0;
  background: none;
  /* A real drop-shadow follows the chipped silhouette, which a box-shadow
     cannot — it would print a pale rectangle through the gaps. */
  filter: drop-shadow(0 2px 0 rgb(122 92 48 / 45%));
  box-shadow: none;
}

.study-card--choice .choice-option:has(input:checked) {
  border-image-source: url('../assets/halloween/card/rune-bar-on-day.png');
  filter: drop-shadow(0 3px 6px rgb(122 92 48 / 55%));
}

.choice-option__face {
  display: grid;
  grid-template-columns: auto auto minmax(0, 1fr);
  gap: 1.1rem;
  align-items: center;
  width: 100%;
  padding: 0.5rem 0.6rem;
  border: 0;
  border-radius: 0;
  background: none;
  box-shadow: none;
  transition: filter 140ms ease;
}

.study-card--choice .choice-option:hover { filter: brightness(1.08) drop-shadow(0 3px 6px rgb(122 92 48 / 50%)); }
.study-card--choice .choice-option:active { filter: brightness(0.96); }

.choice-option__label {
  font-size: 1.24rem;
  font-weight: 800;
  color: #3a2819;
  line-height: 1.35;
  letter-spacing: 0.01em;
}

.choice-option__tick {
  display: grid;
  place-items: center;
  justify-self: start;
  width: 22px;
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

@media (prefers-reduced-motion: reduce) {
  .choice-option__face,
  .choice-option__tick { transition: none; }
}

@media (max-width: 620px) {
  .choice-list,
  .choice-list--words { grid-template-columns: 1fr; }
}
</style>
