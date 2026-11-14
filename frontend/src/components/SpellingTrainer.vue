<script setup lang="ts">
/**
 * Spelling trainer. Renders one input cell per letter position reported by the
 * server, then submits the concatenated answer. Keyboard behaviour handled here
 * is interaction only: auto-advance, backspace, left/right arrows.
 */
import { computed, nextTick, ref, watch } from 'vue'
import { useSpellingGrid } from '../composables/useSpellingGrid'
import { SPELLING_BLANK_LABELS, type SpellingBlank, type SpellingQuestion } from '../types/learning'
import { useRuneSurface } from '../composables/useRuneSurface'

const { surface } = useRuneSurface('spelling')

const props = defineProps<{
  question: SpellingQuestion
  disabled?: boolean
  /** The graded word once the server has answered; null while still answering. */
  result?: string | null
}>()

/** Per-letter mark, only ever after grading — the word is never sent earlier. */
function letterState(blank: SpellingBlank): 'right' | 'wrong' | null {
  if (!props.result) return null
  const expected = props.result[blank.index]
  if (expected === undefined) return null
  const entered = (blank.prefilled ? blank.character : grid.values.value[blank.index]) ?? ''
  return entered.toLowerCase() === expected.toLowerCase() ? 'right' : 'wrong'
}

const emit = defineEmits<{
  (event: 'answer', value: string): void
}>()

const grid = useSpellingGrid()
const inputs = ref<HTMLInputElement[]>([])

watch(
  () => props.question.questionId,
  () => {
    grid.initialise(props.question.blanks)
    void nextTick(() => focusActive())
  },
  { immediate: true },
)

const canSubmit = computed(() => grid.complete.value && !props.disabled)

// Filling the last letter is the answer: no separate submit button.
watch(
  () => grid.complete.value,
  (done) => {
    if (done && !props.disabled) submit()
  },
)

/** Inside the card: spelling needs to say which letters the server gave away. */
const blankLabel = computed(() =>
  props.question.blankType ? SPELLING_BLANK_LABELS[props.question.blankType] : '按提示拼写',
)

function setInputRef(element: Element | null, index: number): void {
  if (element instanceof HTMLInputElement) {
    inputs.value[index] = element
  }
}

function focusActive(): void {
  inputs.value[grid.activeIndex.value]?.focus()
}

const composingAt = ref<Record<number, boolean>>({})
/**
 * On a mouse/keyboard device the cells are read-only and keys are handled by
 * `keydown`: a read-only field never opens the Chinese IME candidate window.
 * Touch keyboards type through `input`, so they keep the editable fields.
 */
const touchTyping = typeof window !== 'undefined'
  && typeof window.matchMedia === 'function'
  && window.matchMedia('(pointer: coarse)').matches

/** Keep only Latin letters: an IME candidate never becomes the answer. */
function latinOnly(value: string): string {
  return value.replace(/[^a-zA-Z]/g, '')
}

function handleCompositionStart(index: number): void {
  composingAt.value[index] = true
}

function handleCompositionEnd(index: number, event: CompositionEvent): void {
  composingAt.value[index] = false
  const letters = latinOnly(event.data ?? '')
  if (letters) {
    grid.typeCharacterAt(index, letters.slice(0, 1))
    syncDomValues()
    focusActive()
  }
}

function handleInput(index: number, event: Event): void {
  if (composingAt.value[index] || (event as InputEvent).isComposing) {
    return
  }
  const target = event.target as HTMLInputElement
  const letters = latinOnly(target.value)
  grid.typeCharacterAt(index, letters.slice(0, 1))
  // Sync immediately: the grid already holds the authoritative characters, and
  // deferring to nextTick lets a fast keystroke read a stale cell.
  syncDomValues()
  focusActive()
}

function syncDomValues(): void {
  inputs.value.forEach((input, position) => {
    if (!input) {
      return
    }
    const value = grid.values.value[position] ?? ''
    if (input.value !== value) {
      input.value = value
    }
  })
}

function handleKeydown(event: KeyboardEvent, index: number): void {
  if (/^[a-zA-Z]$/.test(event.key) && !touchTyping) {
    event.preventDefault()
    grid.typeCharacterAt(index, event.key)
    syncDomValues()
    focusActive()
    return
  }
  if (event.key === 'Backspace') {
    event.preventDefault()
    grid.backspace()
    syncDomValues()
    focusActive()
    return
  }
  if (event.key === 'ArrowLeft') {
    event.preventDefault()
    grid.moveLeft()
    focusActive()
    return
  }
  if (event.key === 'ArrowRight') {
    event.preventDefault()
    grid.moveRight()
    focusActive()
    return
  }
  if (event.key === 'Enter' && canSubmit.value) {
    event.preventDefault()
    submit()
  }
}

function handleFocus(index: number): void {
  grid.focusIndex(index)
}

function submit(): void {
  if (!canSubmit.value) {
    return
  }
  emit('answer', grid.answer.value)
}
</script>

<template>
  <section class="study-card study-card--spelling rune-surface" :style="surface" aria-labelledby="spelling-definition">
    <div class="spell-head">
      <span class="spell-head__eyebrow">拼写</span>
      <h2 id="spelling-definition" class="spell-head__prompt" tabindex="-1">{{ props.question.definition }}</h2>
      <p v-if="props.question.phonetic" class="spell-head__phonetic">{{ props.question.phonetic }}</p>
      <p class="spell-head__hint">{{ blankLabel }}</p>
    </div>

    <div class="spelling-grid" role="group" aria-label="按字母顺序填写单词">
      <template v-for="blank in props.question.blanks" :key="blank.index">
        <span v-if="blank.prefilled" class="spelling-cell spelling-cell--prefilled" aria-label="已给出的字母">
          {{ blank.character }}
        </span>
        <input
          v-else
          :ref="(element) => setInputRef(element as Element | null, blank.index)"
          class="spelling-cell"
          :class="{
            'spelling-cell--active': grid.activeIndex.value === blank.index,
            'is-filled': Boolean(grid.values.value[blank.index]),
            'spelling-cell--right': letterState(blank) === 'right',
            'spelling-cell--wrong': letterState(blank) === 'wrong',
          }"

          type="text"
          inputmode="text"
          autocomplete="off"
          autocapitalize="off"
          spellcheck="false"
          lang="en"
          maxlength="1"
          :aria-label="`第 ${blank.index + 1} 个字母`"
          :value="grid.values.value[blank.index] ?? ''"
          :readonly="!touchTyping"
          :disabled="props.disabled"
          @input="handleInput(blank.index, $event)"
          @compositionstart="handleCompositionStart(blank.index)"
          @compositionend="handleCompositionEnd(blank.index, $event)"
          @keydown="handleKeydown($event, blank.index)"
          @focus="handleFocus(blank.index)"
        />
      </template>
    </div>
  </section>
</template>

<style scoped>
.study-card--spelling {
  display: grid;
  gap: 1.2rem;
  max-width: 720px;
  margin: 0 auto;
  padding: 30px 26px;
  /* Same carved stone as the choice card: 9-slice artwork, flat middle. */
  border: 0;
  border-style: solid;
  border-width: 46px;
  border-color: transparent;
  border-image-source: url('../assets/halloween/card/slab-biscuit.png');
  border-image-slice: 12% fill;
  border-image-width: 46px;
  border-image-repeat: stretch;
  border-radius: 0;
  background: #e8c58a;
  background-clip: padding-box;
  box-shadow: none;
  color: #5a3a16;
}

.spell-head {
  display: grid;
  gap: 0.4rem;
  justify-items: center;
  text-align: center;
}

.spell-head__eyebrow {
  font-size: 0.7rem;
  font-weight: 800;
  letter-spacing: 0.2em;
  text-transform: uppercase;
  color: #7a6647;
}

.spell-head__prompt {
  margin: 0;
  font-family: Georgia, 'Times New Roman', serif;
  font-size: clamp(1.4rem, 3.6vw, 2rem);
  font-weight: 700;
  line-height: 1.3;
  color: #5a3a16;
  max-width: 34ch;
}

.spell-head__phonetic {
  margin: 0;
  font-family: ui-monospace, Consolas, monospace;
  font-size: 0.94rem;
  color: #6c573a;
}

.spell-head__hint {
  margin: 0;
  font-size: 0.82rem;
  font-weight: 700;
  color: #6c573a;
}

/* Letter slots sit on the table like tiles, so each one reads as a cell to fill. */
.spelling-grid {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
  justify-content: center;
}

.spelling-cell {
  display: grid;
  place-items: center;
  width: clamp(2.6rem, 6.4vw, 3.3rem);
  height: clamp(3rem, 7.2vw, 3.8rem);
  padding: 0;
  /* Each letter sits on its own tile: baked by day, cut by night. */
  border: 0;
  border-radius: 0;
  background-color: transparent;
  background-color: transparent;
  background-image: url('../assets/halloween/card/letter-tile-day.png');
  background-position: center;
  background-repeat: no-repeat;
  background-size: 100% 100%;
  box-shadow: none;
  font-family: Georgia, 'Times New Roman', serif;
  font-size: clamp(1.2rem, 3vw, 1.55rem);
  font-weight: 700;
  color: #5a3a16;
  text-align: center;
  text-transform: lowercase;
  transition: filter 120ms ease;
}

/* The given letters are marked, not recoloured: the tile they sit on stays
 * the tile, and a wash over it says "already here". */
/* The given letters are marked by their colour alone. A wash over the tile
 * turned the wood grey, which read as a disabled control rather than a hint. */
.spelling-cell--prefilled {
  color: #8a6a3e;
}

.spelling-cell--active {
  color: #fff8e8;
  box-shadow: inset 0 0 0 999px rgb(150 90 10 / 42%);
}

.spelling-cell:focus-visible {
  outline: 2px solid #8f5f18;
  outline-offset: 2px;
}

.spelling-cell:disabled { opacity: 0.6; }

@media (prefers-reduced-motion: reduce) {
  .spelling-cell { transition: none; }
}
</style>
