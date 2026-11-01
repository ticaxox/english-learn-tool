<script setup lang="ts">
import { computed } from 'vue'
import type { Wordbook } from '../api/wordbooks'

const props = withDefaults(defineProps<{
  book: Wordbook
  statusLabel: string
  statusDescription: string
  formattedDate: string
  canActivate: boolean
  canExport: boolean
  canDelete: boolean
  activating: boolean
  compact?: boolean
  sequence?: number
}>(), {
  compact: false,
  sequence: 0,
})

const emit = defineEmits<{
  detail: []
  activate: []
  export: []
  delete: []
}>()

const coverLetter = computed(() => {
  const name = props.book.name.trim()
  const lastToken = name.split(/\s+/).at(-1) ?? ''
  // Demo shelves often share a long prefix; the trailing number distinguishes them.
  if (/^\d{2,}$/.test(lastToken)) return lastToken.slice(-2)
  return name.slice(0, 1).toUpperCase() || 'W'
})
const coverTone = computed(() => {
  if (props.sequence > 0) return ['sage', 'ocean', 'clay', 'slate'][(props.sequence - 1) % 4]

  const total = Array.from(props.book.id).reduce((sum, char) => sum + char.charCodeAt(0), 0)
  return ['sage', 'ocean', 'clay', 'slate'][total % 4]
})
</script>

<template>
  <article
    class="wordbook-card"
    :class="[
      `wordbook-card--${book.visibility}`,
      { 'wordbook-card--compact': compact, 'wordbook-card--active': book.is_active },
    ]"
  >
    <div
      class="wordbook-cover"
      :class="`wordbook-cover--${coverTone}`"
      :style="book.visibility === 'private'
        ? 'background-color:#244b64; background-image:radial-gradient(circle at 100% 0%, rgb(211 204 255 / 40%), transparent 8rem)'
        : 'background-color:var(--forest); background-image:radial-gradient(circle at 100% 0%, rgb(247 216 75 / 38%), transparent 8rem)'"
    >
      <template v-if="!compact">
        <span class="wordbook-spine">WHISKER PRESS</span>
        <div class="wordbook-card-topline">
          <span class="wordbook-pill" :class="`wordbook-pill--${book.visibility}`">
            {{ book.visibility === 'organization' ? '组织' : '私有' }}
          </span>
          <span class="wordbook-status" :class="`wordbook-status--${book.status}`">{{ statusLabel }}</span>
          <span v-if="book.is_active" class="wordbook-status wordbook-status--active">当前主词书</span>
        </div>
      </template>
      <strong class="wordbook-cover-letter" aria-hidden="true">{{ coverLetter }}</strong>
      <template v-if="!compact">
        <h3>{{ book.name }}</h3>
        <span class="wordbook-cover-meta">{{ book.entry_count.toLocaleString('zh-CN') }} 词条 · v{{ book.version }}</span>
        <span class="wordbook-cover-stamp">{{ book.is_active ? '使用中' : '书架中' }}</span>
      </template>
    </div>

    <div class="wordbook-card-body">
      <template v-if="compact">
        <h3>{{ book.name }}</h3>
        <span class="wordbook-entry-count">{{ book.entry_count.toLocaleString('zh-CN') }} 词条 · v{{ book.version }}</span>
        <div class="wordbook-card-badges">
          <span class="wordbook-pill" :class="`wordbook-pill--${book.visibility}`">
            {{ book.visibility === 'organization' ? '组织' : '私有' }}
          </span>
          <span class="wordbook-status" :class="`wordbook-status--${book.status}`">{{ statusLabel }}</span>
          <span v-if="book.is_active" class="wordbook-status wordbook-status--active">当前主词书</span>
        </div>
      </template>
      <template v-if="!compact">
        <p class="wordbook-description">{{ book.description || '暂无描述' }}</p>
        <p class="wordbook-card-meta">
          {{ statusDescription }}<span>·</span>{{ formattedDate }}
        </p>
      </template>
      <div class="wordbook-card-actions">
        <button class="button-secondary button-small" type="button" :aria-label="`查看 ${book.name} 的词条`" @click="emit('detail')">查看词条</button>
        <button
          v-if="canActivate"
          type="button"
          class="button-small"
          :aria-label="`将 ${book.name} 设为当前主词书`"
          :disabled="activating"
          @click="emit('activate')"
        >{{ activating ? '激活中…' : '设为主词书' }}</button>
        <button v-else class="button-secondary button-small" type="button" disabled>已在使用</button>
        <button
          v-if="canExport"
          class="button-secondary button-small"
          type="button"
          :aria-label="`导出 ${book.name}`"
          @click="emit('export')"
        >导出</button>
        <button
          v-if="canDelete"
          class="button-danger button-small"
          type="button"
          :aria-label="`删除 ${book.name}`"
          @click="emit('delete')"
        >删除</button>
      </div>
    </div>
  </article>
</template>