<script setup lang="ts">
/**
 * A search field: the magnifier and the clear button are drawn, not the
 * browser's.
 *
 * The native search input gives a tiny grey cross that appears at 60% opacity
 * and sits hard against the text. Here the clear button only exists once there
 * is something to clear, and it is a real 44px target.
 */
import { computed, ref, watch } from 'vue'
import CrumbIcon from './CrumbIcon.vue'

const props = withDefaults(defineProps<{
  modelValue: string
  label: string
  placeholder?: string
  id?: string
  disabled?: boolean
}>(), {
  placeholder: undefined,
  id: undefined,
  disabled: false,
})

const emit = defineEmits<{ (event: 'update:modelValue', value: string): void }>()

const input = ref<HTMLInputElement | null>(null)
const hasValue = computed(() => props.modelValue.length > 0)

function onInput(event: Event): void {
  emit('update:modelValue', (event.target as HTMLInputElement).value)
}

function clear(): void {
  emit('update:modelValue', '')
  input.value?.focus()
}

// The field is uncontrolled while typing (the cursor must not jump), so an
// externally cleared model has to be pushed back into the DOM.
watch(() => props.modelValue, (value) => {
  if (input.value && input.value.value !== value) input.value.value = value
})
</script>

<template>
  <div class="crumb-search" :class="{ 'has-value': hasValue, 'is-disabled': disabled }">
    <CrumbIcon class="crumb-search__lens" name="search" :size="17" />
    <input
      :id="id"
      ref="input"
      class="crumb-search__input"
      type="search"
      :value="modelValue"
      :placeholder="placeholder"
      :disabled="disabled"
      :aria-label="label"
      @input="onInput"
    />
    <button
      class="crumb-search__clear"
      type="button"
      :disabled="disabled"
      aria-label="清空搜索"
      :tabindex="hasValue ? 0 : -1"
      @click="clear"
    >
      <CrumbIcon name="clear" :size="13" />
    </button>
  </div>
</template>
