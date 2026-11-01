<script setup lang="ts">
/** Letter marker for an option: a quiet ring that fills on selection. */
defineProps<{ letter: string }>()
</script>

<template>
  <span class="option-badge" aria-hidden="true">
    <span class="option-badge__letter">{{ letter }}</span>
  </span>
</template>
