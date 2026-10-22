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
const blankLabel = computed(() => SPELLING_BLANK_LABELS[props.question.blankType])

function setInputRef(element: Element | null, index: number): void {
  if (element instanceof HTMLInputElement) {
    inputs.value[index] = element
  }
}

function focusActive(): void {
  inputs.value[grid.activeIndex.value]?.focus()
}

function handleInput(index: number, event: Event): void {
  const target = event.target as HTMLInputElement
  grid.typeCharacterAt(index, target.value)
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

function handleKeydown(event: KeyboardEvent): void {
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

    <h2 id="spelling-definition" class="study-card__prompt">{{ props.question.definition }}</h2>
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
          maxlength="1"
          :aria-label="`第 ${blank.index + 1} 个字母`"
          :value="grid.values.value[blank.index] ?? ''"
          :disabled="props.disabled"
          @input="handleInput(blank.index, $event)"
          @keydown="handleKeydown"
          @focus="handleFocus(blank.index)"
        />
      </template>
    </div>

    <div class="button-row">
      <button class="button" type="button" :disabled="!canSubmit" @click="submit">提交拼写</button>
    </div>
    <p class="inline-note">大小写不影响判分；正确性由服务端判定，本页不会预先比对答案。</p>
  </section>
</template>
