<script setup lang="ts">
/**
 * A date field that belongs to this room.
 *
 * <input type="date"> has the same problem the time field had: it looks like
 * the page until it is used, and then the browser paints its own calendar —
 * a white system grid with the OS highlight, unreachable from CSS. This draws
 * the month itself, in the same frame and ink as the time picker beside it.
 *
 * The value is still "YYYY-MM-DD", so it drops in wherever a native date field
 * was, and typing still works: digits land as 2026-11-13 with the dashes put
 * in as you go.
 */
import { computed, ref, watch } from 'vue'
import { useAnchoredPopover } from '../../composables/useAnchoredPopover'

const props = withDefaults(defineProps<{
  modelValue: string | null
  id?: string
  disabled?: boolean
  invalid?: boolean
  label?: string
}>(), {
  id: undefined,
  disabled: false,
  invalid: false,
  label: '日期',
})

const emit = defineEmits<{ (event: 'update:modelValue', value: string | null): void }>()

/** Monday first: the week in this product's own reports starts on Monday. */
const WEEKDAYS = ['一', '二', '三', '四', '五', '六', '日']
const CELLS_PER_VIEW = 42

const pad = (value: number): string => String(value).padStart(2, '0')

interface DateParts { year: number; month: number; day: number }

function parseIso(raw: string | null): DateParts | null {
  if (!raw) return null
  const match = /^(\d{4})-(\d{1,2})-(\d{1,2})$/.exec(raw.trim())
  if (!match) return null
  const year = Number(match[1])
  const month = Number(match[2])
  const day = Number(match[3])
  if (month < 1 || month > 12 || day < 1 || day > 31) return null
  // A day that rolled over is not a date: 2026-02-30 is 2026-03-02 to Date.
  const probe = new Date(year, month - 1, day)
  if (probe.getFullYear() !== year || probe.getMonth() !== month - 1 || probe.getDate() !== day) return null
  return { year, month, day }
}

const toIso = (year: number, month: number, day: number): string => `${year}-${pad(month)}-${pad(day)}`

function partsOf(date: Date): DateParts {
  return { year: date.getFullYear(), month: date.getMonth() + 1, day: date.getDate() }
}

const value = computed(() => parseIso(props.modelValue))
const display = computed(() => (value.value ? toIso(value.value.year, value.value.month, value.value.day) : ''))

const today = partsOf(new Date())
const todayIso = toIso(today.year, today.month, today.day)

const inputEl = ref<HTMLInputElement | null>(null)
const draft = ref(display.value)

const viewYear = ref(value.value?.year ?? today.year)
/** Zero-based, the way Date counts months. */
const viewMonth = ref((value.value?.month ?? today.month) - 1)

const { bindHost, bindPanel, isOpen: open, open: openPanel, close: closePanel, containsPanel } =
  useAnchoredPopover(() => inputEl.value?.focus())

watch(display, (next) => {
  if (document.activeElement !== inputEl.value) draft.value = next
})

/* ------------------------------------------------------------------ grid */

const monthLabel = computed(() => `${viewYear.value} 年 ${viewMonth.value + 1} 月`)

/** Always six rows, so the panel keeps its height as months change. */
const cells = computed(() => {
  const first = new Date(viewYear.value, viewMonth.value, 1)
  const lead = (first.getDay() + 6) % 7
  const start = new Date(viewYear.value, viewMonth.value, 1 - lead)
  return Array.from({ length: CELLS_PER_VIEW }, (_, index) => {
    const date = new Date(start.getFullYear(), start.getMonth(), start.getDate() + index)
    const iso = toIso(date.getFullYear(), date.getMonth() + 1, date.getDate())
    return {
      iso,
      day: date.getDate(),
      outside: date.getMonth() !== viewMonth.value,
      isToday: iso === todayIso,
      isSelected: iso === display.value,
    }
  })
})

function showMonth(offset: number): void {
  const next = new Date(viewYear.value, viewMonth.value + offset, 1)
  viewYear.value = next.getFullYear()
  viewMonth.value = next.getMonth()
}

function focusMonthOf(parts: DateParts): void {
  viewYear.value = parts.year
  viewMonth.value = parts.month - 1
}

/* ------------------------------------------------------------------ typing */

function onInput(event: Event): void {
  const el = event.currentTarget as HTMLInputElement
  const digits = el.value.replace(/\D/g, '').slice(0, 8)
  let formatted = digits
  if (digits.length > 4) formatted = `${digits.slice(0, 4)}-${digits.slice(4)}`
  if (digits.length > 6) formatted = `${digits.slice(0, 4)}-${digits.slice(4, 6)}-${digits.slice(6)}`
  draft.value = formatted
  el.value = formatted

  // A complete date is announced straight away: the form's own state should
  // not wait for the blur that a submit button never gives it.
  const parsed = parseIso(formatted)
  if (parsed) {
    const iso = toIso(parsed.year, parsed.month, parsed.day)
    if (iso !== props.modelValue) emit('update:modelValue', iso)
  }
}

function commitDraft(): void {
  const trimmed = draft.value.trim()
  if (trimmed === '') {
    draft.value = ''
    if (props.modelValue !== null && props.modelValue !== '') emit('update:modelValue', null)
    return
  }
  const parsed = parseIso(trimmed)
  if (parsed) {
    draft.value = toIso(parsed.year, parsed.month, parsed.day)
    focusMonthOf(parsed)
    emit('update:modelValue', draft.value)
  } else {
    draft.value = display.value
  }
}

function onKeydown(event: KeyboardEvent): void {
  if (event.key === 'Enter') {
    event.preventDefault()
    commitDraft()
    return
  }
  if (event.key === 'ArrowDown') {
    event.preventDefault()
    openPicker()
  }
}

/* ------------------------------------------------------------------ picker */

function openPicker(): void {
  if (props.disabled) return
  focusMonthOf(value.value ?? partsOf(new Date()))
  openPanel()
}

function onFieldClick(event: MouseEvent): void {
  if (containsPanel(event.target as Node | null)) return
  openPicker()
}

function select(iso: string): void {
  const parsed = parseIso(iso)
  if (!parsed) return
  draft.value = toIso(parsed.year, parsed.month, parsed.day)
  focusMonthOf(parsed)
  emit('update:modelValue', draft.value)
}

function selectToday(): void {
  select(todayIso)
  closePanel()
}

function clear(): void {
  draft.value = ''
  emit('update:modelValue', null)
  closePanel()
}
</script>

<template>
  <div
    :ref="bindHost"
    class="crumb-date"
    :class="{ 'is-disabled': disabled, 'is-invalid': invalid, 'is-open': open }"
    @click="onFieldClick"
  >
    <input
      :id="id"
      ref="inputEl"
      class="crumb-date__input"
      type="text"
      inputmode="numeric"
      autocomplete="off"
      maxlength="10"
      placeholder="年-月-日"
      :value="draft"
      :disabled="disabled"
      :aria-label="label"
      :aria-invalid="invalid || undefined"
      aria-haspopup="dialog"
      :aria-expanded="open"
      @input="onInput"
      @keydown="onKeydown"
      @blur="commitDraft"
    />

    <svg
      class="crumb-date__glyph"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      stroke-width="2"
      stroke-linecap="round"
      stroke-linejoin="round"
      aria-hidden="true"
    >
      <rect x="3.5" y="5" width="17" height="15" rx="3" />
      <path d="M3.5 10h17M8 3.5v3M16 3.5v3" />
    </svg>

    <div
      :ref="bindPanel"
      class="crumb-date__picker"
      popover="manual"
      role="dialog"
      :aria-label="`${label}选择`"
    >
      <div class="crumb-date__head">
        <button class="crumb-date__step" type="button" :aria-label="`上个月`" @click="showMonth(-1)">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
            <path d="m14 6-6 6 6 6" />
          </svg>
        </button>
        <span class="crumb-date__month" aria-live="polite">{{ monthLabel }}</span>
        <button class="crumb-date__step" type="button" :aria-label="`下个月`" @click="showMonth(1)">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
            <path d="m10 6 6 6-6 6" />
          </svg>
        </button>
      </div>

      <div class="crumb-date__weekdays" aria-hidden="true">
        <span v-for="label in WEEKDAYS" :key="label">{{ label }}</span>
      </div>

      <div class="crumb-date__grid">
        <button
          v-for="cell in cells"
          :key="cell.iso"
          class="crumb-date__cell"
          :class="{
            'is-outside': cell.outside,
            'is-today': cell.isToday,
            'is-selected': cell.isSelected,
          }"
          type="button"
          :aria-current="cell.isSelected ? 'date' : undefined"
          @click="select(cell.iso)"
        >
          {{ cell.day }}
        </button>
      </div>

      <div class="crumb-date__foot">
        <button class="crumb-date__action" type="button" @click="selectToday">今天</button>
        <button class="crumb-date__action crumb-date__action--quiet" type="button" @click="clear">清除</button>
      </div>
    </div>
  </div>
</template>
