<script setup lang="ts">
/**
 * One row of a practice record list: pick it, or open it.
 *
 * The same row serves the flat list and both mistake groupings, so the
 * checkbox, the score and the way to open a record are written once. What the
 * row says about a record — the type, the time — is decided by the list that
 * drops it, because a date header already says part of it. No book icon: the
 * record lists are lists, not shelves.
 */
import { computed } from 'vue'
import AppIcon from './AppIcon.vue'
import { PRACTICE_TYPE_LABELS, type PracticeRecordSummary } from '../api/practice'

const props = withDefaults(defineProps<{
  record: PracticeRecordSummary
  checked: boolean
  title: string
  meta: string
}>(), {})

const emit = defineEmits<{
  (event: 'toggle'): void
  (event: 'open'): void
}>()

const score = computed(() => (props.record.score === null ? '—' : String(Math.round(props.record.score))))
const checkLabel = computed(() => `选择${PRACTICE_TYPE_LABELS[props.record.practiceType]}记录 ${props.title}`)
</script>

<template>
  <li class="records-row" :class="{ 'is-selected': checked }">
    <input
      class="records-row__check"
      type="checkbox"
      :checked="checked"
      :aria-label="checkLabel"
      @change="emit('toggle')"
    />
    <button class="records-row__open" type="button" @click="emit('open')">
      <span class="records-row__body">
        <span class="records-row__title">{{ title }}</span>
        <span class="records-row__meta">{{ meta }}</span>
      </span>
      <span class="records-row__marks">
        <span class="records-row__score">{{ score }}<small>分</small></span>
        <span v-if="record.wrongCount" class="records-row__wrong">{{ record.wrongCount }} 错</span>
        <span v-else class="records-row__clean">全对</span>
      </span>
      <span class="records-row__go" aria-hidden="true">
        <AppIcon name="arrow" />
      </span>
    </button>
  </li>
</template>
