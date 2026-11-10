<script setup lang="ts">
/**
 * Day / night. A brass knob sliding between a sun and a moon — the same thing
 * the product does to the whole room, in the size of a button.
 */
import { computed } from 'vue'
import { isNight, toggleTheme } from '../composables/useTheme'

const label = computed(() => (isNight.value ? '切到白天' : '切到夜晚'))
</script>

<template>
  <button
    class="theme-switch"
    type="button"
    role="switch"
    :aria-checked="isNight"
    :aria-label="label"
    :title="label"
    @click="toggleTheme"
  >
    <span class="theme-switch__track" aria-hidden="true">
      <svg class="theme-switch__sun" viewBox="0 0 24 24">
        <circle cx="12" cy="12" r="4.2" />
        <path d="M12 2.6v2.2M12 19.2v2.2M2.6 12h2.2M19.2 12h2.2M5.4 5.4l1.6 1.6M17 17l1.6 1.6M18.6 5.4 17 7M7 17l-1.6 1.6" />
      </svg>
      <svg class="theme-switch__moon" viewBox="0 0 24 24">
        <path d="M15.6 3.6a8.6 8.6 0 1 0 4.8 15.2A9.6 9.6 0 0 1 15.6 3.6Z" />
      </svg>
      <span class="theme-switch__knob"></span>
    </span>
  </button>
</template>
