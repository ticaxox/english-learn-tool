<script setup lang="ts">
withDefaults(defineProps<{
  size?: 'small' | 'medium' | 'large' | 'hero'
}>(), {
  size: 'small',
})
</script>

<template>
  <svg
    class="crumbo-mark"
    :class="`crumbo-mark--${size}`"
    viewBox="0 0 100 100"
    role="img"
    aria-label="Crumbo"
  >
    <path
      d="M48 15c-18 0-32 14-32 33 0 20 14 34 33 34 8 0 15-2 20-7-5-3-7-8-5-13 2-5 7-7 12-6 2-5 2-10 1-15-4 5-10 7-15 4-6-3-8-10-5-16 2-4 5-7 9-8-5-4-11-6-18-6Z"
      fill="var(--crumbo-gold, #e9b43b)"
    />
    <path d="M30 27c3-13 17-19 28-12 5 3 8 8 9 13L30 27Z" fill="var(--crumbo-moss, #66753a)" />
    <path d="M26 29c11-4 27-5 43-1 3 1 4 4 3 7-1 2-4 3-7 2-10-3-21-3-34 0-3 1-6-1-7-3-1-2 0-4 2-5Z" fill="var(--crumbo-moss, #66753a)" />
    <circle cx="39" cy="53" r="14" fill="#fff8e8" />
    <circle cx="39" cy="53" r="7" fill="var(--crumbo-cocoa, #573022)" />
    <circle cx="62" cy="52" r="11" fill="#fff8e8" />
    <circle cx="62" cy="52" r="6" fill="var(--crumbo-cocoa, #573022)" />
    <path d="M41 70c6 5 13 5 19 0" fill="none" stroke="var(--crumbo-cocoa, #573022)" stroke-width="3.5" stroke-linecap="round" />
    <circle cx="85" cy="72" r="5" fill="var(--crumbo-gold, #e9b43b)" />
  </svg>
</template>

<style scoped>
.crumbo-mark {
  display: block;
  flex: 0 0 auto;
}
.crumbo-mark--small { width: 2rem; height: 2rem; }
.crumbo-mark--medium { width: 4rem; height: 4rem; }
.crumbo-mark--large { width: 7rem; height: 7rem; }
.crumbo-mark--hero { width: 11rem; height: 11rem; }
</style>