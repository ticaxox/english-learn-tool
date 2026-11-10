<script setup lang="ts">
/**
 * Crumbo, the mascot. The drawn set is the product's Crumbo — one painting for
 * daylight, one for after dark — so the mascot is the same character the books
 * and the empty states use, not a second drawing of him.
 */
import ArtImage from './ArtImage.vue'
import { illustration } from '../assets/halloween'

withDefaults(defineProps<{
  size?: 'small' | 'medium' | 'large' | 'hero'
  /** Driven by the streak: tired after a break, glowing on a long run. */
  mood?: 'tired' | 'normal' | 'happy' | 'glowing'
}>(), {
  size: 'small',
  mood: 'normal',
})
</script>

<template>
  <span
    class="crumbo-mark"
    :class="[`crumbo-mark--${size}`, `crumbo-mark--${mood}`]"
    role="img"
    :aria-label="`Crumbo，${mood === 'tired' ? '有点累' : mood === 'glowing' ? '精神饱满' : '状态不错'}`"
  >
    <ArtImage :set="illustration.crumbo" />
  </span>
</template>

<style scoped>
.crumbo-mark {
  display: block;
  flex: 0 0 auto;
  line-height: 0;
}

.crumbo-mark :deep(.art-swap),
.crumbo-mark :deep(.art-swap__stack) {
  width: 100%;
  height: 100%;
}

.crumbo-mark :deep(.art-swap__frame) {
  width: 100%;
  height: 100%;
  object-fit: contain;
}

.crumbo-mark--small { width: 2rem; height: 2rem; }
.crumbo-mark--medium { width: 4rem; height: 4rem; }
.crumbo-mark--large { width: 7rem; height: 7rem; }
.crumbo-mark--hero { width: 11rem; height: 11rem; }

/* Mood rides on how the mascot carries himself, not on repainting him. */
.crumbo-mark--tired { opacity: 0.72; filter: saturate(0.7); transform: translateY(2px); }
.crumbo-mark--happy { filter: saturate(1.08); }
.crumbo-mark--glowing {
  filter: drop-shadow(0 0 6px rgb(233 180 59 / 70%)) saturate(1.15);
}
</style>
