<script setup lang="ts">
/**
 * Text where any English word can be tapped to hear it.
 *
 * Words are plain spans with one delegated click handler rather than hundreds
 * of buttons, so a long passage does not flood the tab order. Readers who use
 * the keyboard get the page's own speaker buttons instead.
 */
import { computed } from 'vue'
import { speak } from '../composables/useSpeechSynthesis'

const props = withDefaults(defineProps<{ text: string; as?: string }>(), { as: 'p' })

const EN_WORD = /[A-Za-z][A-Za-z'’-]*/g

const parts = computed(() => {
  const result: Array<{ text: string; word: boolean }> = []
  let last = 0
  for (const match of props.text.matchAll(EN_WORD)) {
    const index = match.index ?? 0
    if (index > last) result.push({ text: props.text.slice(last, index), word: false })
    result.push({ text: match[0], word: true })
    last = index + match[0].length
  }
  if (last < props.text.length) result.push({ text: props.text.slice(last), word: false })
  return result
})

function onWordClick(event: MouseEvent): void {
  const target = (event.target as HTMLElement | null)?.closest('[data-word]')
  const word = target?.getAttribute('data-word')
  if (word) speak(word)
}
</script>

<template>
  <component :is="as" class="spoken-text" @click="onWordClick">
    <template v-for="(part, index) in parts" :key="index">
      <span v-if="part.word" class="spoken-word" :data-word="part.text" :title="`朗读 ${part.text}`">{{ part.text }}</span>
      <template v-else>{{ part.text }}</template>
    </template>
  </component>
</template>
