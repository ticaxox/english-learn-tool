<script setup lang="ts">
/**
 * One illustration, both paintings.
 *
 * The day and night images are two independent renderings of the same
 * composition, so they sit stacked in one grid cell and cross-fade over 520ms.
 * Switching theme reads as the same scene relit — never a filter over the day
 * art, because the night version already paints its own light.
 */
import { computed } from 'vue'
import type { ThemeMode } from '../assets/halloween'
import { themeMode } from '../composables/useTheme'

const props = withDefaults(defineProps<{ set: ThemeMode; alt?: string }>(), { alt: '' })

const night = computed(() => themeMode.value === 'night')
</script>

<template>
  <span class="art-swap">
    <img
      class="art-swap__frame"
      :class="{ 'is-shown': !night }"
      :src="props.set.day"
      :alt="props.alt"
    />
    <img
      class="art-swap__frame"
      :class="{ 'is-shown': night }"
      :src="props.set.night"
      alt=""
      aria-hidden="true"
    />
  </span>
</template>
