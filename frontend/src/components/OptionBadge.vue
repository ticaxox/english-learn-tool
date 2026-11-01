<script setup lang="ts">
/**
 * The A/B/C/D plate: one SVG tag fused to the left edge of an option tile.
 * The letter is real text so it keeps the tile's font.
 */
defineProps<{ letter: string }>()
</script>

<template>
  <span class="option-badge" aria-hidden="true">
    <svg class="option-badge__plate" viewBox="0 0 52 48" preserveAspectRatio="none">
      <path class="option-badge__shape" d="M0 0H36L52 24L36 48H0Z" />
    </svg>
    <span class="option-badge__letter">{{ letter }}</span>
  </span>
</template>
