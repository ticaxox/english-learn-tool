<script setup lang="ts">
/**
 * A time field that belongs to this room.
 *
 * <input type="time"> looks like the page while it is at rest, but the moment
 * it is used the browser paints its own picker: a white system list of hours
 * and minutes, squared corners, the OS highlight. That panel is not in the DOM
 * and no selector reaches into it, so on a page built out of leather and brass
 * the field turns into a taskbar clock the first time someone clicks it.
 *
 * This keeps what the native field was good at — "HH:MM" as the value, arrow
 * keys and typed entry, `inputmode="numeric"` on a phone, a <label for> — and
 * draws the picker itself: two columns, in the same ink and paper as the
 * select's own popover.
 */
import { computed, nextTick, onBeforeUnmount, ref, watch } from 'vue'

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
  label: '时间',
})

const emit = defineEmits<{ (event: 'update:modelValue', value: string | null): void }>()

const HOURS = Array.from({ length: 24 }, (_, index) => index)
/** Five-minute steps: a生成时间 is a moment in the day, not a stopwatch. */
const MINUTE_STEP = 5
const MINUTES = Array.from({ length: 60 / MINUTE_STEP }, (_, index) => index * MINUTE_STEP)

const pad = (value: number): string => String(value).padStart(2, '0')

function parseTime(raw: string | null): { hour: number; minute: number } | null {
  if (!raw) return null
  const match = /^(\d{1,2}):(\d{1,2})$/.exec(raw.trim())
  if (!match) return null
  const hour = Number(match[1])
  const minute = Number(match[2])
  if (!Number.isFinite(hour) || !Number.isFinite(minute)) return null
  if (hour > 23 || minute > 59) return null
  return { hour, minute }
}

const value = computed(() => parseTime(props.modelValue))
const display = computed(() => (value.value ? `${pad(value.value.hour)}:${pad(value.value.minute)}` : ''))

const inputEl = ref<HTMLInputElement | null>(null)
const rootEl = ref<HTMLElement | null>(null)
const pickerEl = ref<HTMLElement | null>(null)
const hourColumn = ref<HTMLElement | null>(null)
const minuteColumn = ref<HTMLElement | null>(null)

const draft = ref(display.value)
const open = ref(false)

// The model is the source of truth; the box only holds what is being typed.
watch(display, (next) => {
  if (document.activeElement !== inputEl.value) draft.value = next
})

/* ------------------------------------------------------------------ typing */

function onInput(event: Event): void {
  const el = event.currentTarget as HTMLInputElement
  const raw = el.value
  const colonAt = raw.indexOf(':')
  const digits = raw.replace(/\D/g, '').slice(0, 4)

  let formatted = digits
  if (colonAt > 0) {
    // The colon the person typed is where the hour ends, not where 2 digits end.
    const split = Math.min(colonAt, digits.length)
    formatted = digits.slice(0, split) + ':' + digits.slice(split)
  } else if (digits.length > 2) {
    // Three digits are read as H:MM when "HH" cannot be an hour — 930 is 9:30,
    // not 93:0. Four digits are always HH:MM, so 1230 stays 12:30 as typed.
    const hourDigits = digits.length === 3 && Number(digits.slice(0, 2)) > 23 ? 1 : 2
    formatted = digits.slice(0, hourDigits) + ':' + digits.slice(hourDigits)
  }

  draft.value = formatted
  el.value = formatted
}

function commitDraft(): void {
  const trimmed = draft.value.trim()
  if (trimmed === '') {
    draft.value = ''
    if (props.modelValue !== null && props.modelValue !== '') emit('update:modelValue', null)
    return
  }
  const parsed = parseTime(trimmed)
  if (parsed) {
    draft.value = `${pad(parsed.hour)}:${pad(parsed.minute)}`
    emit('update:modelValue', draft.value)
  } else {
    // Half-typed text is not a time. Put the stored value back rather than
    // leaving a field that disagrees with the model.
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
    return
  }
  if (event.key === 'Escape' && open.value) {
    event.preventDefault()
    closePicker()
  }
}

/* ------------------------------------------------------------------ picker */

function positionPicker(): void {
  const host = rootEl.value
  const panel = pickerEl.value
  if (!host || !panel) return
  const rect = host.getBoundingClientRect()
  const margin = 10
  const width = panel.offsetWidth
  const height = panel.offsetHeight

  let left = rect.left
  if (left + width > window.innerWidth - margin) left = window.innerWidth - width - margin
  if (left < margin) left = margin

  // Below the field, unless the room below is too short — then above it.
  let top = rect.bottom + 8
  if (top + height > window.innerHeight - margin) {
    const above = rect.top - height - 8
    top = above >= margin ? above : Math.max(margin, window.innerHeight - height - margin)
  }

  panel.style.left = `${Math.round(left)}px`
  panel.style.top = `${Math.round(top)}px`
}

function scrollSelectionIntoView(): void {
  for (const column of [hourColumn.value, minuteColumn.value]) {
    const active = column?.querySelector('[aria-current="true"]')
    if (!(active instanceof HTMLElement) || !column) continue
    // Measured from the two rects, not from offsetTop: the list is not the
    // offset parent, so offsetTop is a distance from the field, not the list.
    const listRect = column.getBoundingClientRect()
    const cellRect = active.getBoundingClientRect()
    const delta = (cellRect.top - listRect.top) - (listRect.height - cellRect.height) / 2
    column.scrollTop += delta
  }
}

function onPointerDown(event: PointerEvent): void {
  const target = event.target as Node | null
  if (target && (rootEl.value?.contains(target) || pickerEl.value?.contains(target))) return
  closePicker()
}

function onWindowChange(): void {
  positionPicker()
}

/** The picker degrades to an inline panel where the Popover API is missing;
 *  only the placement it wants (top layer) is lost, not the control. */
function isPopoverOpen(panel: HTMLElement): boolean {
  try {
    return panel.matches(':popover-open')
  } catch {
    return false
  }
}

function openPicker(): void {
  if (props.disabled || open.value) return
  open.value = true
  void nextTick(() => {
    const panel = pickerEl.value
    if (!panel) return
    if (typeof panel.showPopover === 'function' && !isPopoverOpen(panel)) panel.showPopover()
    positionPicker()
    scrollSelectionIntoView()
    document.addEventListener('pointerdown', onPointerDown, true)
    document.addEventListener('keydown', onKeydownAtLarge, true)
    window.addEventListener('resize', onWindowChange)
    window.addEventListener('scroll', onWindowChange, true)
  })
}

function closePicker(): void {
  if (!open.value) return
  open.value = false
  const panel = pickerEl.value
  if (panel && typeof panel.hidePopover === 'function' && isPopoverOpen(panel)) panel.hidePopover()
  document.removeEventListener('pointerdown', onPointerDown, true)
  document.removeEventListener('keydown', onKeydownAtLarge, true)
  window.removeEventListener('resize', onWindowChange)
  window.removeEventListener('scroll', onWindowChange, true)
}

function onKeydownAtLarge(event: KeyboardEvent): void {
  if (event.key !== 'Escape') return
  event.preventDefault()
  closePicker()
  inputEl.value?.focus()
}

/** The whole field is the target, not just the clock at its end: the digits
 *  are what a person aims at, and asking them to hit an 18px icon to change
 *  the time is the kind of thing only the native control does.
 *  A click inside the panel must not count — it is a child of this element,
 *  so the event bubbles up here even though the panel sits in the top layer. */
function onFieldClick(event: MouseEvent): void {
  const target = event.target as Node | null
  if (target && pickerEl.value?.contains(target)) return
  openPicker()
}

function setHour(hour: number): void {
  const minute = value.value?.minute ?? 0
  draft.value = `${pad(hour)}:${pad(minute)}`
  emit('update:modelValue', draft.value)
}

function setMinute(minute: number): void {
  const hour = value.value?.hour ?? 6
  draft.value = `${pad(hour)}:${pad(minute)}`
  emit('update:modelValue', draft.value)
}

function onBlur(): void {
  commitDraft()
}

onBeforeUnmount(() => {
  closePicker()
})
</script>

<template>
  <div
    ref="rootEl"
    class="crumb-time"
    :class="{ 'is-disabled': disabled, 'is-invalid': invalid, 'is-open': open }"
    @click="onFieldClick"
  >
    <input
      :id="id"
      ref="inputEl"
      class="crumb-time__input"
      type="text"
      inputmode="numeric"
      autocomplete="off"
      maxlength="5"
      placeholder="--:--"
      :value="draft"
      :disabled="disabled"
      :aria-label="label"
      :aria-invalid="invalid || undefined"
      aria-haspopup="dialog"
      :aria-expanded="open"
      @input="onInput"
      @keydown="onKeydown"
      @blur="onBlur"
    />

    <svg
      class="crumb-time__glyph"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      stroke-width="2"
      stroke-linecap="round"
      stroke-linejoin="round"
      aria-hidden="true"
    >
      <circle cx="12" cy="12" r="9" />
      <path d="M12 7.4V12l3.1 1.9" />
    </svg>

    <div ref="pickerEl" class="crumb-time__picker" popover="manual" role="dialog" :aria-label="`${label}选择`">
      <div class="crumb-time__wheel">
        <div class="crumb-time__column">
          <p class="crumb-time__caption">时</p>
          <div ref="hourColumn" class="crumb-time__list">
            <button
              v-for="hour in HOURS"
              :key="`h-${hour}`"
              class="crumb-time__cell"
              type="button"
              :aria-current="value?.hour === hour ? 'true' : undefined"
              :class="{ 'is-active': value?.hour === hour }"
              @click="setHour(hour)"
            >
              {{ pad(hour) }}
            </button>
          </div>
        </div>
        <div class="crumb-time__seam" aria-hidden="true">:</div>
        <div class="crumb-time__column">
          <p class="crumb-time__caption">分</p>
          <div ref="minuteColumn" class="crumb-time__list">
            <button
              v-for="minute in MINUTES"
              :key="`m-${minute}`"
              class="crumb-time__cell"
              type="button"
              :aria-current="value?.minute === minute ? 'true' : undefined"
              :class="{ 'is-active': value?.minute === minute }"
              @click="setMinute(minute)"
            >
              {{ pad(minute) }}
            </button>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>
