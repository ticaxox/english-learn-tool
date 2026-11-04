<script setup lang="ts">
/**
 * Spelling trainer. Renders one input cell per letter position reported by the
 * server, then submits the concatenated answer. Keyboard behaviour handled here
 * is interaction only: auto-advance, backspace, left/right arrows.
 */
import { computed, nextTick, ref, watch } from 'vue'
import { useSpellingGrid } from '../composables/useSpellingGrid'
import { SPELLING_BLANK_LABELS, type SpellingQuestion } from '../types/learning'

const props = defineProps<{
  question: SpellingQuestion
  disabled?: boolean
}>()

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
  <section class="study-card" aria-labelledby="spelling-definition">
    <p class="study-card__meta">
      <span class="study-badge">拼写</span>
      <span>{{ blankLabel }}</span>
      <span>剩余 {{ props.question.remaining }} 张</span>
    </p>

    <h2 id="spelling-definition" class="study-card__prompt" tabindex="-1">{{ props.question.definition }}</h2>
    <p v-if="props.question.phonetic" class="study-card__phonetic">{{ props.question.phonetic }}</p>

    <div class="spelling-grid" role="group" aria-label="按字母顺序填写单词">
      <template v-for="blank in props.question.blanks" :key="blank.index">
        <span v-if="blank.prefilled" class="spelling-cell spelling-cell--prefilled" aria-label="已给出的字母">
          {{ blank.character }}
        </span>
        <input
          v-else
          :ref="(element) => setInputRef(element as Element | null, blank.index)"
          class="spelling-cell"
          :class="{ 'spelling-cell--active': grid.activeIndex.value === blank.index }"
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

    <div class="button-row">
      <DivButton class="button" type="button" :disabled="!canSubmit" @click="submit">提交拼写</DivButton>
    </div>
  </section>
</template>
