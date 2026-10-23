<script setup lang="ts">
withDefaults(defineProps<{ text: string; as?: 'p' | 'span' | 'div' }>(), { as: 'p' })
</script>

<template>
  <component :is="as" class="notification-plain-text">{{ text }}</component>
</template>