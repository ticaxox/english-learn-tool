<script setup lang="ts">
/** A fixed-label ticket drawn as SVG, with the label kept as real text. */
defineProps<{ label: string }>()
</script>

<template>
  <span class="svg-stamp" role="note">
    <svg class="svg-stamp__art" viewBox="0 0 132 36" preserveAspectRatio="none" aria-hidden="true">
      <rect class="svg-stamp__face" x="1" y="1" width="130" height="34" rx="9" />
      <path class="svg-stamp__dash" d="M10 1v34M122 1v34" />
      <circle class="svg-stamp__hole" cx="10" cy="18" r="2.6" />
      <circle class="svg-stamp__hole" cx="122" cy="18" r="2.6" />
    </svg>
    <span class="svg-stamp__label">{{ label }}</span>
  </span>
</template>
