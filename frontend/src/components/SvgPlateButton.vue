<script setup lang="ts">
/**
 * Primary action drawn as an SVG plate instead of a plain rounded rectangle.
 * The label stays real DOM text so it remains selectable and testable.
 */
import { motion } from 'motion-v'

withDefaults(defineProps<{
  type?: 'button' | 'submit'
  variant?: 'primary' | 'secondary'
  disabled?: boolean
  block?: boolean
}>(), {
  type: 'button',
  variant: 'primary',
  disabled: false,
  block: false,
})
</script>

<template>
  <motion.button
    class="svg-plate-button"
    :class="[`svg-plate-button--${variant}`, { 'svg-plate-button--block': block }]"
    :type="type"
    :disabled="disabled"
    :while-hover="disabled ? undefined : { y: -1 }"
    :while-tap="disabled ? undefined : { scale: 0.985 }"
    :transition="{ type: 'spring', stiffness: 460, damping: 30 }"
  >
    <svg class="svg-plate-button__plate" viewBox="0 0 240 52" preserveAspectRatio="none" aria-hidden="true">
      <rect class="svg-plate-button__edge" x="2" y="5" width="236" height="46" rx="16" ry="16" />
      <rect class="svg-plate-button__face" x="2" y="2" width="236" height="44" rx="16" ry="16" />
    </svg>
    <span class="svg-plate-button__label"><slot /></span>
  </motion.button>
</template>
