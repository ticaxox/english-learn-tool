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
  <div class="alert" role="status" aria-live="polite">
    <div class="button-row">
      <span class="spinner" aria-hidden="true"></span>
      <span>{{ label }}</span>
    </div>
  </div>
</template>