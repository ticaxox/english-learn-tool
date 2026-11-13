<script setup lang="ts">
/**
 * The coach's reply, written the way the model writes it.
 *
 * Models answer in markdown: bold, italics, inline code, fenced blocks, links,
 * headings, quotes, rules, tables, nested lists. A bubble that prints the
 * asterisks is a bubble that looks broken.
 *
 * Everything is escaped before a single tag is added, so model output can never
 * inject markup, and link targets are limited to http(s), mailto and plain
 * relative paths.
 *
 * The tap-a-word-to-hear-it behaviour of SpokenText survives: English words get
 * a `data-word` span, except inside code, where a click would be nonsense.
 */
import { computed } from 'vue'
import { speak } from '../composables/useSpeechSynthesis'

const props = defineProps<{ text: string }>()

const ESCAPES: Record<string, string> = { '&': '&amp;', '<': '&lt;', '>': '&gt;' }

function escapeHtml(value: string): string {
  return value.replace(/[&<>]/g, (char) => ESCAPES[char] ?? char)
}

/** Only these schemes may become a link; anything else stays as plain text. */
function safeHref(raw: string): string | null {
  const url = raw.trim().replace(/^<|>$/g, '')
  if (/^(https?:|mailto:)/i.test(url)) return url
  if (!url.includes(':')) return url
  return null
}

const CODE_MARK = '\u0000'
const PLACEHOLDER = /\u0000(\d+)\u0000/g

function inline(value: string): string {
  const codes: string[] = []

  const out = escapeHtml(value)
    // Inline code is lifted out first so markdown characters inside it survive.
    .replace(/`([^`]+)`/g, (_match, code: string) => {
      codes.push(`<code>${code}</code>`)
      return `${CODE_MARK}${codes.length - 1}${CODE_MARK}`
    })
    // Links before emphasis, so their brackets are gone by then.
    .replace(/\[([^\]]+)\]\(([^)\s]+)\)/g, (match, label: string, href: string) => {
      const url = safeHref(href)
      if (!url) return match
      return `<a href="${url}" target="_blank" rel="noopener noreferrer">${label}</a>`
    })
    .replace(/\*\*([\s\S]+?)\*\*/g, '<strong>$1</strong>')
    .replace(/__([\s\S]+?)__/g, '<strong>$1</strong>')
    .replace(/~~([\s\S]+?)~~/g, '<del>$1</del>')
    .replace(/(^|[^\w*\\])\*([^*\n]+?)\*/g, '$1<em>$2</em>')
    .replace(/(^|[^\w_\\])_([^_\n]+?)_/g, '$1<em>$2</em>')

  return out.replace(PLACEHOLDER, (_match, index: string) => codes[Number(index)] ?? '')
}

/* --------------------------------------------------------------- words */

// `(?<!&)` keeps the scanner out of entity names such as `&amp;`.
const EN_WORD = /(?<!&)[A-Za-z][A-Za-z'’-]*/g

/** Wrap English words for the tap-to-hear handler; never inside a tag or code. */
function wrapWords(source: string): string {
  return source
    .split(/(<pre[\s\S]*?<\/pre>|<code[\s\S]*?<\/code>|<[^>]+>)/g)
    .map((segment) => {
      if (!segment || segment.startsWith('<')) return segment
      return segment.replace(
        EN_WORD,
        (word) => `<span class="spoken-word" data-word="${word}" title="朗读 ${word}">${word}</span>`,
      )
    })
    .join('')
}

/* --------------------------------------------------------------- blocks */

const TABLE_SEPARATOR = /^\s*\|?[\s:|-]*-[\s:|-]*\|?\s*$/
const BULLET = /^(\s*)[-*+]\s+(.*)$/
const ORDERED = /^(\s*)\d+[.)]\s+(.*)$/
const FENCE = /^```/
const indentOf = (raw: string): number => Math.floor(raw.replace(/\t/g, '  ').length / 2)

function renderTable(rows: string[]): string {
  const cells = (row: string): string[] =>
    row.trim().replace(/^\||\|$/g, '').split('|').map((cell) => cell.trim())

  const head = cells(rows[0])
  const body = rows.slice(1).map(cells)
  const headHtml = head.map((cell) => `<th>${inline(cell)}</th>`).join('')
  const bodyHtml = body
    .map((row) => `<tr>${row.map((cell) => `<td>${inline(cell)}</td>`).join('')}</tr>`)
    .join('')
  return `<table><thead><tr>${headHtml}</tr></thead><tbody>${bodyHtml}</tbody></table>`
}

type ListItem = { indent: number; tag: 'ul' | 'ol'; text: string }

/** One pass over a run of list lines: a stack of open lists keeps the nesting. */
function renderList(items: ListItem[]): string {
  let out = ''
  const stack: Array<{ indent: number; tag: 'ul' | 'ol' }> = []
  for (const item of items) {
    while (stack.length && item.indent < stack[stack.length - 1].indent) {
      out += `</li></${stack.pop()!.tag}>`
    }
    if (!stack.length || item.indent > stack[stack.length - 1].indent) {
      out += `<${item.tag}><li>${inline(item.text)}`
      stack.push({ indent: item.indent, tag: item.tag })
      continue
    }
    out += `</li><li>${inline(item.text)}`
  }
  while (stack.length) out += `</li></${stack.pop()!.tag}>`
  return out
}

const html = computed(() => {
  const lines = props.text.replace(/\r\n/g, '\n').split('\n')
  const out: string[] = []

  for (let i = 0; i < lines.length; i += 1) {
    const line = lines[i]
    const trimmed = line.trim()

    // ---- fenced code
    if (FENCE.test(trimmed)) {
      const buffer: string[] = []
      i += 1
      while (i < lines.length && !FENCE.test(lines[i].trim())) {
        buffer.push(lines[i])
        i += 1
      }
      out.push(`<pre><code>${escapeHtml(buffer.join('\n'))}</code></pre>`)
      continue
    }

    // ---- table: a row of pipes above a separator row
    if (trimmed.includes('|') && i + 1 < lines.length && TABLE_SEPARATOR.test(lines[i + 1])) {
      const rows: string[] = [lines[i]]
      i += 2 // the separator row is markup, not content
      while (i < lines.length && lines[i].trim().includes('|')) {
        rows.push(lines[i])
        i += 1
      }
      i -= 1
      out.push(renderTable(rows))
      continue
    }

    const heading = /^(#{1,6})\s+(.*)$/.exec(trimmed)
    if (heading) {
      out.push(`<h4>${inline(heading[2])}</h4>`)
      continue
    }

    if (/^(-{3,}|\*{3,}|_{3,})$/.test(trimmed)) {
      out.push('<hr />')
      continue
    }

    if (/^>\s?/.test(trimmed)) {
      const quote: string[] = []
      while (i < lines.length && /^>\s?/.test(lines[i].trim())) {
        quote.push(lines[i].trim().replace(/^>\s?/, ''))
        i += 1
      }
      i -= 1
      out.push(`<blockquote>${inline(quote.join(' '))}</blockquote>`)
      continue
    }

    // ---- a run of list lines, rendered as one tree
    if (BULLET.test(line) || ORDERED.test(line)) {
      const items: ListItem[] = []
      while (i < lines.length && (BULLET.test(lines[i]) || ORDERED.test(lines[i]))) {
        const bullet = BULLET.exec(lines[i])
        const ordered = ORDERED.exec(lines[i])
        const match = (bullet ?? ordered)!
        items.push({ indent: indentOf(match[1]), tag: bullet ? 'ul' : 'ol', text: match[2] })
        i += 1
      }
      i -= 1
      out.push(renderList(items))
      continue
    }

    if (!trimmed) continue

    out.push(`<p>${inline(trimmed)}</p>`)
  }

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
