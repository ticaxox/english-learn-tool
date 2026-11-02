<script setup lang="ts">
import { ref } from 'vue'

/**
 * A div-based button. Keeps click, Enter/Space, disabled and form-submit
 * behaviour while leaving native inputs/links/forms untouched.
 */
const props = withDefaults(defineProps<{
  type?: 'button' | 'submit' | 'reset'
  disabled?: boolean
}>(), {
  type: 'button',
  disabled: false,
})

const emit = defineEmits<{ (event: 'click', payload: MouseEvent | KeyboardEvent): void }>()
const root = ref<HTMLElement | null>(null)

function activate(event: MouseEvent | KeyboardEvent): void {
  if (props.disabled) return
  emit('click', event)
  if (event.defaultPrevented) return
  const form = root.value?.closest('form')
  if (!form) return
  if (props.type === 'submit') {
    if (typeof form.requestSubmit === 'function') form.requestSubmit()
    else form.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }))
  } else if (props.type === 'reset') {
    form.reset()
  }
}

function onClick(event: MouseEvent): void {
  activate(event)
}

function onKeydown(event: KeyboardEvent): void {
  if (event.key === 'Enter' || event.key === ' ') {
    activate(event)
    event.preventDefault()
  }
}

defineExpose({ focus: () => root.value?.focus() })
</script>

<template>
  <div
    ref="root"
    class="div-button"
    role="button"
    :type="type"
    :tabindex="disabled ? -1 : 0"
    :aria-disabled="disabled || undefined"
    @click="onClick"
    @keydown="onKeydown"
  >
    <slot />
  </div>
</template>
