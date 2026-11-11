<script setup lang="ts">
/**
 * The two small reward marks: a crumb coin and a streak candle.
 *
 * Same flat vector language as the crest — solid fills, one outline weight,
 * no gradients and no glow. The candle is the streak because a streak is days
 * on end, and the coin is the crumb because a crumb is what you collect.
 */
withDefaults(defineProps<{
  mark?: 'coin' | 'candle'
  size?: number
}>(), { mark: 'coin', size: 18 })
</script>

<template>
  <svg
    v-if="mark === 'coin'"
    class="mark"
    :width="size"
    :height="size"
    viewBox="0 0 24 24"
    fill="none"
    aria-hidden="true"
  >
    <circle cx="12" cy="12" r="9" fill="#FFC800" stroke="#B37E00" stroke-width="2" />
    <path d="M12 6.5 13.9 10l3.6.5-2.6 2.5.7 3.5-3.6-1.9-3.5 1.9.6-3.5L6.5 10l3.6-.5L12 6.5Z" fill="#FFE9A8" />
  </svg>

  <svg
    v-else
    class="mark"
    :width="size"
    :height="size"
    viewBox="0 0 24 24"
    fill="none"
    aria-hidden="true"
  >
    <path
      d="M12 3.5c1.9 2.4 3 4.1 3 6a3 3 0 0 1-6 0c0-1.9 1.1-3.6 3-6Z"
      fill="#FFC800"
      stroke="#B37E00"
      stroke-width="1.6"
      stroke-linejoin="round"
    />
    <rect x="10.2" y="12" width="3.6" height="8" rx="1.2" fill="#FFF3DC" stroke="#8A6A3A" stroke-width="1.6" />
    <path d="M8.4 20.5h7.2" stroke="#8A6A3A" stroke-width="1.8" stroke-linecap="round" />
  </svg>
</template>

<style scoped>
.mark {
  display: block;
  flex: 0 0 auto;
}
</style>
