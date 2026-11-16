<script setup lang="ts">
/**
 * Text where the wordbook's own words can be pressed to see what they mean.
 *
 * Only the wordbook's own words become spans; everything else stays plain
 * text, so the passage has exactly as many pressable things as it has words to
 * learn. The spans share one delegated click handler rather than a listener
 * each, so a long passage does not flood the tab order.
 */
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import AppIcon from './AppIcon.vue'
import { speak } from '../composables/useSpeechSynthesis'
import { useWordGlossary } from '../composables/useWordGlossary'

const props = withDefaults(
  defineProps<{ text: string; as?: string; highlight?: string[] }>(),
  { as: 'p', highlight: () => [] },
)

const EN_WORD = /[A-Za-z][A-Za-z'’-]*/g

/** Words taken from the learner's wordbook, marked so they stand out while reading. */
const targets = computed(() => new Set(props.highlight.map((word) => word.trim().toLowerCase()).filter(Boolean)))

const glosses = useWordGlossary()

const parts = computed(() => {
  const result: Array<{ text: string; word: boolean; target?: boolean }> = []
  let last = 0
  for (const match of props.text.matchAll(EN_WORD)) {
    const index = match.index ?? 0
    if (index > last) result.push({ text: props.text.slice(last, index), word: false })
    result.push({ text: match[0], word: true, target: targets.value.has(match[0].toLowerCase()) })
    last = index + match[0].length
  }
  if (last < props.text.length) result.push({ text: props.text.slice(last), word: false })
  return result
})

/** The little card beside a pressed word: word, sound, meaning. */
const tip = ref<{ word: string; phonetic: string | null; meaning: string; left: number; top: number } | null>(null)
const TIP_WIDTH = 236

function closeTip(): void {
  tip.value = null
}

function openTip(word: string, anchor: HTMLElement, gloss: { phonetic: string | null; meaning: string }): void {
  const rect = anchor.getBoundingClientRect()
  const left = Math.min(
    Math.max(8, rect.left + rect.width / 2 - TIP_WIDTH / 2),
    Math.max(8, window.innerWidth - TIP_WIDTH - 8),
  )
  tip.value = { word, phonetic: gloss.phonetic, meaning: gloss.meaning, left, top: rect.bottom + 8 }
}

function onWordClick(event: MouseEvent): void {
  const anchor = (event.target as HTMLElement | null)?.closest('[data-word]') as HTMLElement | null
  const word = anchor?.getAttribute('data-word')
  if (!word || !anchor) return
  const gloss = anchor.classList.contains('spoken-word--target') ? glosses.value[word.toLowerCase()] : null
  if (gloss) {
    openTip(word, anchor, gloss)
    return
  }
  closeTip()
  speak(word)
}

function onDocumentClick(event: MouseEvent): void {
  if (!tip.value) return
  const target = event.target as HTMLElement | null
  if (target?.closest('.word-tip') || target?.closest('[data-word]')) return
  closeTip()
}

function onKeydown(event: KeyboardEvent): void {
  if (event.key === 'Escape') closeTip()
}

onMounted(() => {
  document.addEventListener('click', onDocumentClick)
  document.addEventListener('keydown', onKeydown)
})

onBeforeUnmount(() => {
  document.removeEventListener('click', onDocumentClick)
  document.removeEventListener('keydown', onKeydown)
})
</script>

<template>
  <component :is="as" class="spoken-text" @click="onWordClick">
    <template v-for="(part, index) in parts" :key="index">
      <span
        v-if="part.target"
        class="spoken-word spoken-word--target"
        :data-word="part.text"
        :title="`查看 ${part.text} 的释义`"
      >{{ part.text }}</span>
      <template v-else>{{ part.text }}</template>
    </template>
    <Teleport to="body">
      <div
        v-if="tip"
        class="word-tip"
        role="dialog"
        :aria-label="`${tip.word} 的释义`"
        :style="{ left: `${tip.left}px`, top: `${tip.top}px`, width: `${TIP_WIDTH}px` }"
      >
        <p class="word-tip__word">{{ tip.word }}</p>
        <p v-if="tip.phonetic" class="word-tip__sound">
          <span class="word-tip__phonetic">{{ tip.phonetic }}</span>
          <button
            class="word-tip__speak"
            type="button"
            :aria-label="`朗读 ${tip.word}`"
            @click.stop="speak(tip.word)"
          >
            <AppIcon name="speaker" />
          </button>
        </p>
        <p class="word-tip__meaning">{{ tip.meaning }}</p>
      </div>
    </Teleport>
  </component>

</template>

<style scoped>
.word-tip {
  position: fixed;
  z-index: 60;
  display: grid;
  gap: 6px;
  padding: 12px 14px;
  border: 2px solid #ecd9bb;
  border-radius: 14px;
  background: #fffdf6;
  box-shadow: 0 8px 20px rgb(59 42 26 / 18%);
  color: #35240f;
}

.word-tip__sound {
  display: flex;
  gap: 8px;
  align-items: center;
  margin: 0;
}

.word-tip__word {
  margin: 0;
  font-family: Georgia, 'Times New Roman', serif;
  font-size: 1.08rem;
  font-weight: 700;
}

.word-tip__phonetic {
  flex: 1 1 auto;
  min-width: 0;
  color: #7d6247;
  font-family: ui-monospace, Consolas, monospace;
  font-size: 0.74rem;
  overflow-wrap: anywhere;
}

.word-tip__speak {
  display: grid;
  flex: 0 0 auto;
  width: 22px;
  height: 22px;
  padding: 0;
  place-items: center;
  border: 1px solid #ecd9bb;
  border-radius: 999px;
  background: #fffdf6;
  color: #7d6247;
  cursor: pointer;
}

.word-tip__speak :deep(svg) { width: 13px; height: 13px; }

.word-tip__meaning {
  margin: 0;
  font-size: 0.9rem;
  line-height: 1.5;
}

html[data-theme='night'] .word-tip {
  border-color: #3a3160;
  background: #221b3a;
  box-shadow: 0 8px 20px rgb(6 3 16 / 45%);
  color: #f3e9d2;
}

html[data-theme='night'] .word-tip__phonetic { color: #b9a4e6; }
html[data-theme='night'] .word-tip__speak { border-color: #3a3160; background: #221b3a; color: #b9a4e6; }
</style>
