<script setup lang="ts">
/**
 * Hob, the mascot: the thing that lives on the shelf beside the fire. One
 * painting for daylight, one for after dark — the same character the books and
 * the empty states use, not a second drawing of him.
 */
import ArtImage from './ArtImage.vue'
import { illustration, type ThemeMode } from '../assets/halloween'

withDefaults(defineProps<{
  size?: 'small' | 'medium' | 'large' | 'hero'
  /** Driven by the streak: tired after a break, glowing on a long run. */
  mood?: 'tired' | 'normal' | 'happy' | 'glowing'
  /**
   * Which painting of the character to draw. Defaults to the lantern mark.
   * Most places should pass their own — the mark is the logo and is the only
   * drawing meant to repeat; everywhere else is a different moment.
   */
  set?: ThemeMode
}>(), {
  size: 'small',
  mood: 'normal',
  set: () => illustration.hob,
})
</script>

<template>
  <span
    class="hob-mark"
    :class="[`hob-mark--${size}`, `hob-mark--${mood}`]"
    role="img"
    :aria-label="`Hob，${mood === 'tired' ? '有点累' : mood === 'glowing' ? '精神饱满' : '状态不错'}`"
  >
    <ArtImage :set="set" />
  </span>
</template>

<style scoped>
.hob-mark {
  display: block;
  flex: 0 0 auto;
  line-height: 0;
}

.hob-mark :deep(.art-swap),
.hob-mark :deep(.art-swap__stack) {
  width: 100%;
  height: 100%;
}

.hob-mark :deep(.art-swap__frame) {
  width: 100%;
  height: 100%;
  object-fit: contain;
}

.hob-mark--small { width: 2rem; height: 2rem; }
.hob-mark--medium { width: 4rem; height: 4rem; }
.hob-mark--large { width: 7rem; height: 7rem; }
.hob-mark--hero { width: 11rem; height: 11rem; }

/* Mood rides on how the mascot carries himself, not on repainting him. */
.hob-mark--tired { opacity: 0.72; filter: saturate(0.7); transform: translateY(2px); }
.hob-mark--happy { filter: saturate(1.08); }
.hob-mark--glowing {
  filter: drop-shadow(0 0 6px rgb(233 180 59 / 70%)) saturate(1.15);
}
</style>
