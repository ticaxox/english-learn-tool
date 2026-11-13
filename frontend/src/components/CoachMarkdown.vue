<script setup lang="ts">
/**
 * The coach's reply, written the way the model writes it.
 *
 * Models answer in markdown — `**bold**`, `- lists`, `## headings`, `code` —
 * and a bubble that prints the asterisks is a bubble that looks broken. This
 * renders the small subset a chat answer actually uses, and keeps the word
 * tap that `SpokenText` provides: any English word still reads itself aloud.
 *
 * Everything is escaped before a single tag is added, so model output can
 * never inject markup.
 */
import { computed } from 'vue'
import { speak } from '../composables/useSpeechSynthesis'

const props = defineProps<{ text: string }>()

const ESCAPES: Record<string, string> = { '&': '&amp;', '<': '&lt;', '>': '&gt;' }

function escapeHtml(value: string): string {
  return value.replace(/[&<>]/g, (char) => ESCAPES[char] ?? char)
}

// `(?<!&)` keeps the scanner out of entity names such as `&amp;`.
const EN_WORD = /(?<!&)[A-Za-z][A-Za-z'’-]*/g

/** Wrap English words for the tap-to-hear handler, never inside a tag. */
function wrapWords(html: string): string {
  return html
    .split(/(<[^>]+>)/g)
    .map((segment) =>
      segment.startsWith('<')
        ? segment
        : segment.replace(
            EN_WORD,
            (word) => `<span class="spoken-word" data-word="${word}" title="朗读 ${word}">${word}</span>`,
          ),
    )
    .join('')
}

function inline(value: string): string {
  return escapeHtml(value)
    .replace(/`([^`]+)`/g, '<code>$1</code>')
    .replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
    .replace(/(^|[^\w*])\*([^*\n]+)\*/g, '$1<em>$2</em>')
}

const html = computed(() => {
  const out: string[] = []
  let list: string[] | null = null
  let listTag = 'ul'

  const flush = (): void => {
    if (!list) return
    out.push(`<${listTag}>${list.join('')}</${listTag}>`)
    list = null
  }

  for (const raw of props.text.replace(/\r\n/g, '\n').split('\n')) {
    const line = raw.trim()
    const heading = /^(#{1,6})\s+(.*)$/.exec(line)
    const bullet = /^[-*+]\s+(.*)$/.exec(line)
    const ordered = /^\d+[.)]\s+(.*)$/.exec(line)

    if (heading) {
      flush()
      out.push(`<h4>${inline(heading[2])}</h4>`)
      continue
    }
    if (bullet) {
      if (!list || listTag !== 'ul') { flush(); listTag = 'ul'; list = [] }
      list.push(`<li>${inline(bullet[1])}</li>`)
      continue
    }
    if (ordered) {
      if (!list || listTag !== 'ol') { flush(); listTag = 'ol'; list = [] }
      list.push(`<li>${inline(ordered[1])}</li>`)
      continue
    }
    if (!line) { flush(); continue }
    flush()
    out.push(`<p>${inline(line)}</p>`)
  }
  flush()

  return wrapWords(out.join(''))
})

function onWordClick(event: MouseEvent): void {
  const target = (event.target as HTMLElement | null)?.closest('[data-word]')
  const word = target?.getAttribute('data-word')
  if (word) speak(word)
}
</script>

<template>
  <!-- eslint-disable-next-line vue/no-v-html -- escaped above; no model markup survives -->
  <div class="spoken-text coach-markdown" @click="onWordClick" v-html="html" />
</template>
