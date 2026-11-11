<script setup lang="ts">
/**
 * Artwork that changes with the mode.
 *
 * Day and night are two separate drawings, so both are in the DOM and one is
 * faded out while the other fades in. Nothing is tinted and nothing is
 * filtered — at the midpoint the two pictures cross over.
 */
import { useMode } from '../composables/useMode'

defineProps<{
  day: string
  night: string
  alt?: string
}>()

const { isNight } = useMode()
</script>

<template>
  <span class="mode-art" :class="{ 'is-night': isNight }">
    <img class="mode-art__img mode-art__img--day" :src="day" :alt="alt ?? ''" />
    <img class="mode-art__img mode-art__img--night" :src="night" :alt="alt ?? ''" aria-hidden="true" />
  </span>
</template>

<style scoped>
.mode-art {
  position: relative;
  display: inline-block;
  line-height: 0;
}

.mode-art__img {
  display: block;
  width: 100%;
  height: 100%;
  object-fit: contain;
  transition: opacity 520ms ease;
}

.mode-art__img--night {
  position: absolute;
  inset: 0;
  opacity: 0;
}

.mode-art.is-night .mode-art__img--day { opacity: 0; }
.mode-art.is-night .mode-art__img--night { opacity: 1; }

@media (prefers-reduced-motion: reduce) {
  .mode-art__img { transition: none; }
}
</style>
