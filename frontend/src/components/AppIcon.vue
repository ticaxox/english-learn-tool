<script setup lang="ts">
withDefaults(
  defineProps<{
    name:
      | 'today'
      | 'book'
      | 'cards'
      | 'trail'
      | 'coach'
      | 'bell'
      | 'settings'
      | 'admin'
      | 'arrow'
      | 'arrow-left'
      | 'close'
      | 'star'
      | 'spark'
      | 'lock'
      | 'plus'
      | 'send'
      | 'speaker'
      | 'image'
  }>(),
  { name: 'spark' },
)
</script>

<template>
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
    <template v-if="name === 'today'">
      <circle cx="12" cy="12" r="3.5" />
      <path d="M12 2v3M12 19v3M2 12h3M19 12h3M4.9 4.9 7 7M17 17l2.1 2.1M19.1 4.9 17 7M7 17l-2.1 2.1" />
    </template>
    <template v-else-if="name === 'book'">
      <path d="M4 5.5A3.5 3.5 0 0 1 7.5 2H11v17H7.5A3.5 3.5 0 0 0 4 22V5.5Z" />
      <path d="M20 5.5A3.5 3.5 0 0 0 16.5 2H13v17h3.5A3.5 3.5 0 0 1 20 22V5.5Z" />
    </template>
    <template v-else-if="name === 'cards'">
      <rect x="5" y="3" width="13" height="16" rx="2" />
      <path d="m9 7 5 3-5 3V7ZM9 22h8a3 3 0 0 0 3-3V8" />
    </template>
    <template v-else-if="name === 'trail'">
      <path d="m3 6 6-3 6 3 6-3v15l-6 3-6-3-6 3V6Z" />
      <path d="M9 3v15M15 6v15" />
    </template>
    <template v-else-if="name === 'coach'">
      <path d="M4 5h16v12H8l-4 4V5Z" />
      <path d="M8 9h8M8 13h5" />
    </template>
    <template v-else-if="name === 'bell'">
      <path d="M5 17h14l-2-3V9a5 5 0 0 0-10 0v5l-2 3ZM10 20h4" />
    </template>
    <template v-else-if="name === 'settings'">
      <circle cx="12" cy="12" r="3" />
      <path d="M19 12a7 7 0 0 0-.1-1l2-1.5-2-3.5-2.3 1a7 7 0 0 0-1.7-1L14.5 3h-5l-.4 3a7 7 0 0 0-1.7 1L5 6l-2 3.5L5.1 11a7 7 0 0 0 0 2L3 14.5 5 18l2.4-1a7 7 0 0 0 1.7 1l.4 3h5l.4-3a7 7 0 0 0 1.7-1l2.4 1 2-3.5-2.1-1.5a7 7 0 0 0 .1-1Z" />
    </template>
    <template v-else-if="name === 'admin'">
      <circle cx="9" cy="8" r="3" />
      <circle cx="17" cy="9" r="2.4" />
      <path d="M3.8 20a5.2 5.2 0 0 1 10.4 0M14.4 20a4.2 4.2 0 0 1 6.2-3.7" />
    </template>
    <template v-else-if="name === 'arrow'">
      <path d="M5 12h14M14 7l5 5-5 5" />
    </template>
    <template v-else-if="name === 'arrow-left'">
      <path d="M19 12H5M10 7l-5 5 5 5" />
    </template>
    <template v-else-if="name === 'close'">
      <path d="m5 5 14 14M19 5 5 19" />
    </template>
    <template v-else-if="name === 'star'">
      <path d="m12 2.8 2.8 5.6 6.2.9-4.5 4.4 1.1 6.2-5.6-3-5.6 3 1.1-6.2L3 9.3l6.2-.9L12 2.8Z" />
    </template>
    <template v-else-if="name === 'spark'">
      <path d="m12 2 2.2 7.8L22 12l-7.8 2.2L12 22l-2.2-7.8L2 12l7.8-2.2L12 2Z" />
    </template>
    <template v-else-if="name === 'lock'">
      <rect x="5" y="10" width="14" height="11" rx="2" />
      <path d="M8 10V7a4 4 0 0 1 8 0v3" />
    </template>
    <template v-else-if="name === 'plus'">
      <path d="M12 4v16M4 12h16" />
    </template>
    <template v-else-if="name === 'send'">
      <path d="m3 11 18-8-8 18-2-7-8-3ZM11 14l5-5" />
    </template>
    <template v-else-if="name === 'speaker'">
      <path d="M11 5 6 9H3v6h3l5 4V5Z" />
      <path d="M15 9a4 4 0 0 1 0 6M18 6a8 8 0 0 1 0 12" />
    </template>
    <template v-else-if="name === 'image'">
      <rect x="3" y="4" width="18" height="16" rx="2" />
      <circle cx="9" cy="10" r="1.6" />
      <path d="m4 18 5-5 4 4 3-3 4 4" />
    </template>
  </svg>
</template>

<style scoped>
svg {
  display: block;
  width: 1.2rem;
  height: 1.2rem;
}
</style>
