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
 * keys, a <label for> — and draws the picker itself: two wheels, in the same
 * ink and paper as the select's own popover. The whole frame is the target;
 * the clock at its end is a mark, not a second button. The text is a readout,
 * not an editable box: a time is chosen by turning the wheels.
 */
import { computed, nextTick, onBeforeUnmount, ref, watch } from 'vue'
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
const hourColumn = ref<HTMLElement | null>(null)
const minuteColumn = ref<HTMLElement | null>(null)

const { bindHost, bindPanel, isOpen: open, open: openPanel, containsPanel } =
  useAnchoredPopover(() => inputEl.value?.focus())

/* The text is a readout, not a field: the wheels are how a time is chosen. */

function onKeydown(event: KeyboardEvent): void {
  if (event.key === 'Enter') {
    event.preventDefault()
    openPicker()
    return
  }
  if (event.key === 'ArrowDown') {
    event.preventDefault()
    openPicker()
  }
}

/* ------------------------------------------------------------------ picker */

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

/** The row nearest the middle of the dial is the one under the band, so the
 *  wheel picks a value when it stops: turning it is the interaction, not just
 *  a way to reach a row to click. */
function centredValue(list: HTMLElement): number | null {
  const rect = list.getBoundingClientRect()
  const middle = rect.top + rect.height / 2
  let best: { value: number; distance: number } | null = null
  for (const cell of list.querySelectorAll<HTMLElement>('[data-value]')) {
    const box = cell.getBoundingClientRect()
    const distance = Math.abs(box.top + box.height / 2 - middle)
    if (!best || distance < best.distance) best = { value: Number(cell.dataset.value), distance }
  }
  return best ? best.value : null
}

let settleTimer: ReturnType<typeof setTimeout> | null = null

function onDialScroll(dial: 'hour' | 'minute'): void {
  if (settleTimer !== null) clearTimeout(settleTimer)
  settleTimer = setTimeout(() => {
    settleTimer = null
    const list = dial === 'hour' ? hourColumn.value : minuteColumn.value
    if (!list) return
    const next = centredValue(list)
    if (next === null) return
    const current = dial === 'hour' ? value.value?.hour : value.value?.minute
    if (next === current) return
    if (dial === 'hour') setHour(next)
    else setMinute(next)
  }, 140)
}

onBeforeUnmount(() => {
  if (settleTimer !== null) clearTimeout(settleTimer)
})

// A value set from anywhere — a click, a typed time, the form — rolls the
// matching dial to it, so the band always sits over the truth.
watch(display, () => { void nextTick(scrollSelectionIntoView) })

function openPicker(): void {
  if (props.disabled) return
  openPanel()
  void nextTick(scrollSelectionIntoView)
}

/** The whole field is the target, not just the clock at its end: the digits
 *  are what a person aims at, and asking them to hit an 18px icon to change
 *  the time is the kind of thing only the native control does. */
function onFieldClick(event: MouseEvent): void {
  if (containsPanel(event.target as Node | null)) return
  openPicker()
}

function setHour(hour: number): void {
  const minute = value.value?.minute ?? 0
  emit('update:modelValue', `${pad(hour)}:${pad(minute)}`)
}

function setMinute(minute: number): void {
  const hour = value.value?.hour ?? 6
  emit('update:modelValue', `${pad(hour)}:${pad(minute)}`)
}
</script>

<template>
  <div
    :ref="bindHost"
    class="crumb-time"
    :class="{ 'is-disabled': disabled, 'is-invalid': invalid, 'is-open': open }"
    @click="onFieldClick"
  >
    <input
      :id="id"
      ref="inputEl"
      class="crumb-time__input"
      type="text"
      placeholder="--:--"
      :value="display"
      readonly
      :disabled="disabled"
      :aria-label="label"
      :aria-invalid="invalid || undefined"
      aria-haspopup="dialog"
      :aria-expanded="open"
      @keydown="onKeydown"
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

    <div :ref="bindPanel" class="crumb-time__picker" popover="manual" role="dialog" :aria-label="`${label}选择`">
      <p class="crumb-time__readout" aria-hidden="true">
        <span>{{ value ? pad(value.hour) : '--' }}</span>
        <em>:</em>
        <span>{{ value ? pad(value.minute) : '--' }}</span>
      </p>

      <div class="crumb-time__wheel">
        <span class="crumb-time__band" aria-hidden="true"></span>
        <div class="crumb-time__column" aria-label="小时">
          <div ref="hourColumn" class="crumb-time__list" @scroll="onDialScroll('hour')">
            <button
              v-for="hour in HOURS"
              :key="`h-${hour}`"
              class="crumb-time__cell"
              type="button"
              :data-value="hour"
              :aria-current="value?.hour === hour ? 'true' : undefined"
              :class="{ 'is-active': value?.hour === hour }"
              @click="setHour(hour)"
            >
              {{ pad(hour) }}
            </button>
          </div>
        </div>
        <div class="crumb-time__column" aria-label="分钟">
          <div ref="minuteColumn" class="crumb-time__list" @scroll="onDialScroll('minute')">
            <button
              v-for="minute in MINUTES"
              :key="`m-${minute}`"
              class="crumb-time__cell"
              type="button"
              :data-value="minute"
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
