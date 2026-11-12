<script setup lang="ts">
/**
 * A number field drawn as a stepper: the same native input, flanked by two
 * 44px targets instead of the browser's 4px spinners.
 *
 * The native arrows are 12px tall, sit half outside the field and cannot be
 * reached with a thumb. These are two real buttons with a 44px hit area, a
 * press-and-hold repeat, and a boundary that stops rather than wrapping.
 *
 * Still a real <input type="number">: keyboard entry, arrow keys, form
 * submission and the number keyboard on a phone all behave as before.
 */
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import CrumbIcon from './CrumbIcon.vue'

const props = withDefaults(defineProps<{
  modelValue: number
  min?: number
  max?: number
  step?: number
  disabled?: boolean
  label: string
  id?: string
  invalid?: boolean
}>(), {
  min: -Infinity,
  max: Infinity,
  step: 1,
  disabled: false,
  id: undefined,
  invalid: false,
})

const emit = defineEmits<{ (event: 'update:modelValue', value: number): void }>()

const input = ref<HTMLInputElement | null>(null)
const repeatTimer = ref<ReturnType<typeof setTimeout> | null>(null)
const repeatInterval = ref<ReturnType<typeof setInterval> | null>(null)

const atMin = computed(() => props.modelValue <= props.min)
const atMax = computed(() => props.modelValue >= props.max)

function stopRepeat(): void {
  if (repeatTimer.value !== null) { clearTimeout(repeatTimer.value); repeatTimer.value = null }
  if (repeatInterval.value !== null) { clearInterval(repeatInterval.value); repeatInterval.value = null }
}

function commit(next: number): void {
  if (props.disabled) return
  const clamped = Math.min(props.max, Math.max(props.min, next))
  if (clamped === props.modelValue) return
  emit('update:modelValue', clamped)
}

function nudge(direction: 1 | -1): void {
  commit(props.modelValue + direction * props.step)
}

function startRepeat(direction: 1 | -1, event: PointerEvent): void {
  if (props.disabled) return
  event.preventDefault()
  nudge(direction)
  // Hold to keep stepping, the way every other number field on the platform does.
  repeatTimer.value = setTimeout(() => {
    repeatInterval.value = setInterval(() => nudge(direction), 90)
  }, 430)
}

function onInput(event: Event): void {
  const target = event.target as HTMLInputElement
  const raw = target.value
  // An empty box is a field being retyped, not a value of zero. Hold the model
  // where it is; `restore` puts the number back when focus leaves.
  if (raw === '') return
  const parsed = Number(raw)
  if (Number.isFinite(parsed)) emit('update:modelValue', parsed)
}

function restore(): void {
  stopRepeat()
  if (input.value && input.value.value !== String(props.modelValue)) {
    input.value.value = String(props.modelValue)
  }
}

// A value clamped in code has to reach the DOM too, or the field and the model
// disagree after the first boundary hit.
watch(() => props.modelValue, (value) => {
  if (!input.value) return
  const shown = String(value)
  if (input.value.value !== shown && document.activeElement !== input.value) {
    input.value.value = shown
  }
})

onBeforeUnmount(stopRepeat)
</script>

<template>
  <div class="crumb-stepper" :class="{ 'is-disabled': disabled, 'is-invalid': invalid }">
    <button
      class="crumb-stepper__step"
      type="button"
      :disabled="disabled || atMin"
      :aria-label="`减少${label}`"
      tabindex="-1"
      @pointerdown="startRepeat(-1, $event)"
      @pointerup="stopRepeat"
      @pointerleave="stopRepeat"
      @pointercancel="stopRepeat"
    >
      <CrumbIcon name="minus" :size="16" />
    </button>

    <input
      :id="id"
      ref="input"
      class="crumb-stepper__input"
      type="number"
      :value="modelValue"
      :min="min === -Infinity ? undefined : min"
      :max="max === Infinity ? undefined : max"
      :step="step"
      :disabled="disabled"
      :aria-label="label"
      :aria-invalid="invalid || undefined"
      inputmode="numeric"
      @input="onInput"
      @blur="restore"
    />

    <button
      class="crumb-stepper__step"
      type="button"
      :disabled="disabled || atMax"
      :aria-label="`增加${label}`"
      tabindex="-1"
      @pointerdown="startRepeat(1, $event)"
      @pointerup="stopRepeat"
      @pointerleave="stopRepeat"
      @pointercancel="stopRepeat"
    >
      <CrumbIcon name="plus" :size="16" />
    </button>
  </div>
</template>
