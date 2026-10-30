<script setup lang="ts">
withDefaults(
  defineProps<{
    label?: string
  }>(),
  {
    label: '正在读取真实数据…',
  },
)
</script>

<template>
  <div class="crumb-skeleton" role="status" aria-live="polite">
    <div class="crumb-skeleton__lines" aria-hidden="true">
      <span class="crumb-skeleton__bar crumb-skeleton__bar--lg"></span>
      <span class="crumb-skeleton__bar"></span>
      <span class="crumb-skeleton__bar crumb-skeleton__bar--sm"></span>
    </div>
    <p class="crumb-skeleton__label">
      <span class="spinner" aria-hidden="true"></span>
      {{ label }}
    </p>
  </div>
</template>
