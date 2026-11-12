<script setup lang="ts">
/**
 * A file field drawn as a drop zone.
 *
 * The native control is a grey system button with the OS's own type: a wholly
 * different visual language sitting in the middle of this page. The drop zone
 * replaces its face; a real <input type="file"> is still underneath, keyboard
 * reachable and announced, so picking a file works exactly as the platform
 * intends - including the file picker itself, which stays native on purpose.
 */
import { computed, ref } from 'vue'
import CrumbIcon from './CrumbIcon.vue'

const props = withDefaults(defineProps<{
  accept?: string
  disabled?: boolean
  label: string
  hint?: string
  /** The chosen file's name, once there is one. */
  fileName?: string | null
  id?: string
}>(), {
  accept: undefined,
  disabled: false,
  hint: undefined,
  fileName: null,
  id: undefined,
})

const emit = defineEmits<{ (event: 'change', file: File | null): void }>()

const input = ref<HTMLInputElement | null>(null)
const dragging = ref(false)
const hasFile = computed(() => Boolean(props.fileName))

function pick(): void {
  if (props.disabled) return
  input.value?.click()
}

function onChange(event: Event): void {
  const file = (event.target as HTMLInputElement).files?.[0] ?? null
  emit('change', file)
}

/** Clear the internal input: picking the same file again must fire `change`. */
function reset(): void {
  if (input.value) input.value.value = ''
}

defineExpose({ reset })

function onDrop(event: DragEvent): void {
  dragging.value = false
  if (props.disabled) return
  const file = event.dataTransfer?.files?.[0]
  if (!file || !input.value) return
  // Hand the drop to the real input so form submission still sees the file.
  const transfer = new DataTransfer()
  transfer.items.add(file)
  input.value.files = transfer.files
  emit('change', file)
}
</script>

<template>
  <div
    class="crumb-file"
    :class="{ 'is-over': dragging, 'has-file': hasFile, 'is-disabled': disabled }"
    role="button"
    :tabindex="disabled ? -1 : 0"
    :aria-disabled="disabled || undefined"
    :aria-label="label"
    @click="pick"
    @keydown.enter.prevent="pick"
    @keydown.space.prevent="pick"
    @dragenter.prevent="dragging = true"
    @dragover.prevent="dragging = true"
    @dragleave.prevent="dragging = false"
    @dragend.prevent="dragging = false"
    @drop.prevent="onDrop"
  >
    <input
      :id="id"
      ref="input"
      class="crumb-file__input"
      type="file"
      :accept="accept"
      :disabled="disabled"
      tabindex="-1"
      aria-hidden="true"
      @change="onChange"
      @click.stop
    />
    <CrumbIcon class="crumb-file__icon" name="upload" :size="26" />
    <strong class="crumb-file__title">{{ fileName || '把词书文件拖进来，或点击选择' }}</strong>
    <small class="crumb-file__hint">{{ hasFile ? '已选择 · 点击可重新选择' : (hint || 'CSV / JSON / TXT') }}</small>
  </div>
</template>
