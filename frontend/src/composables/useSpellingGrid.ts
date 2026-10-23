/**
 * Letter-grid state for the spelling trainer (T-FE-004).
 *
 * Implements only interaction mechanics that the product contract assigns to
 * the frontend: auto-advance, backspace, left/right arrows, and mobile-friendly
 * single-character entry. Correctness is never evaluated here — the answer is
 * submitted to the server, which ignores case.
 */
import { computed, ref } from 'vue'
import { isSpellingComplete, normaliseSpellingInput } from '../lib/learning-validation'
import type { SpellingBlank } from '../types/learning'

export interface SpellingGridOptions {
  blankType: 'full' | 'partial' | 'first_letter'
  /** Server-provided blanks. `prefilled` positions are locked. */
  blanks: readonly SpellingBlank[]
}

export function useSpellingGrid() {
  const values = ref<string[]>([])
  const prefilled = ref<boolean[]>([])
  const activeIndex = ref(0)

  function initialise(blanks: readonly SpellingBlank[]): void {
    values.value = blanks.map((blank) => (blank.prefilled ? (blank.character ?? '') : ''))
    prefilled.value = blanks.map((blank) => blank.prefilled)
    activeIndex.value = nextEditableIndex(0)
  }

  function nextEditableIndex(from: number): number {
    for (let index = from; index < prefilled.value.length; index += 1) {
      if (!prefilled.value[index]) {
        return index
      }
    }
    // No editable cell left: park at the end for focus bookkeeping.
    return Math.max(0, prefilled.value.length - 1)
  }

  function previousEditableIndex(from: number): number {
    for (let index = from; index >= 0; index -= 1) {
      if (!prefilled.value[index]) {
        return index
      }
    }
    return 0
  }

  /**
   * Type characters into a specific cell, then advance.
   *
   * The target cell is explicit rather than "whatever is active": the DOM input
   * that fired the event is the truthful source, and using it keeps the grid
   * correct even if a pending focus change has not landed yet.
   */
  function typeCharacterAt(startIndex: number, raw: string): void {
    const characters = raw.replace(/[^A-Za-z]/g, '')
    if (characters.length === 0) {
      return
    }

    let index = Math.max(0, Math.min(startIndex, values.value.length - 1))
    if (prefilled.value[index]) {
      index = nextEditableIndex(index + 1)
    }

    for (const character of characters) {
      if (index >= values.value.length) {
        break
      }
      values.value[index] = character
      index = nextEditableIndex(index + 1)
    }
    activeIndex.value = Math.min(index, Math.max(0, values.value.length - 1))
  }

  /** Type into whichever cell currently holds focus. */
  function typeCharacter(raw: string): void {
    typeCharacterAt(activeIndex.value, raw)
  }

  /**
   * Backspace semantics users expect from a letter grid:
   *  - if the active cell has a letter, clear it and stay;
   *  - if it is already empty, walk back to the nearest filled editable cell,
   *    clear that one, and keep focus there.
   */
  function backspace(): void {
    const index = activeIndex.value
    if (!prefilled.value[index] && values.value[index]) {
      values.value[index] = ''
      return
    }

    for (let cursor = index - 1; cursor >= 0; cursor -= 1) {
      if (prefilled.value[cursor]) {
        continue
      }
      activeIndex.value = cursor
      if (values.value[cursor]) {
        values.value[cursor] = ''
      }
      return
    }
  }

  function moveLeft(): void {
    activeIndex.value = previousEditableIndex(activeIndex.value - 1)
  }

  function moveRight(): void {
    const next = nextEditableIndex(activeIndex.value + 1)
    if (next > activeIndex.value) {
      activeIndex.value = next
    }
  }

  function focusIndex(index: number): void {
    if (prefilled.value[index]) {
      return
    }
    activeIndex.value = index
  }

  function reset(): void {
    values.value = []
    prefilled.value = []
    activeIndex.value = 0
  }

  const complete = computed(() => isSpellingComplete(values.value))

  /**
   * The submitted string keeps the original slot order. The server compares
   * case-insensitively, so we send a normalised value rather than guessing
   * expected casing.
   */
  const answer = computed(() => normaliseSpellingInput(values.value.join('')))

  return {
    values,
    prefilled,
    activeIndex,
    complete,
    answer,
    initialise,
    typeCharacter,
    typeCharacterAt,
    backspace,
    moveLeft,
    moveRight,
    focusIndex,
    reset,
  }
}

export type SpellingGrid = ReturnType<typeof useSpellingGrid>
