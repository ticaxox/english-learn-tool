<script setup lang="ts">
import { computed } from 'vue'

const props = withDefaults(defineProps<{
  value: number
  max: number
  size?: number
  stroke?: number
  label?: string
  caption?: string
}>(), {
  size: 132,
  stroke: 12,
  label: '',
  caption: '',
})

const radius = computed(() => (props.size - props.stroke) / 2)
const circumference = computed(() => 2 * Math.PI * radius.value)
const ratio = computed(() => {
  if (props.max <= 0) return 0
  return Math.min(1, Math.max(0, props.value / props.max))
})
const dash = computed(() => `${circumference.value * ratio.value} ${circumference.value}`)
</script>

<template>
  <div class="goal-ring" :style="{ width: `${size}px`, height: `${size}px` }">
    <svg :width="size" :height="size" :viewBox="`0 0 ${size} ${size}`" role="img" :aria-label="`${label} ${value}/${max}`">
      <circle
        class="goal-ring__track"
        :cx="size / 2"
        :cy="size / 2"
        :r="radius"
        fill="none"
        :stroke-width="stroke"
      />
      <circle
        class="goal-ring__value"
        :cx="size / 2"
        :cy="size / 2"
        :r="radius"
        fill="none"
        :stroke-width="stroke"
        stroke-linecap="round"
        :stroke-dasharray="dash"
        :style="{ opacity: ratio > 0 ? 1 : 0 }"
        :transform="`rotate(-90 ${size / 2} ${size / 2})`"
      />
    </svg>
    <div class="goal-ring__center">
      <strong>{{ value }}<span>/{{ max }}</span></strong>
      <small v-if="caption">{{ caption }}</small>
    </div>
    <span v-if="label" class="goal-ring__label">{{ label }}</span>
  </div>
</template>
