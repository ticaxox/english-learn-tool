<script setup lang="ts">
/**
 * A three-piece frame: painted ends, plain middle.
 *
 * The ends keep their aspect ratio (a rod stays round, a chipped edge stays
 * chipped) while the middle stretches to whatever width the content needs, so
 * a wide panel never smears its ornament. The art carries no background — it
 * sits on the page as an object.
 */
import type { Frame3Part } from '../assets/halloween'

withDefaults(defineProps<{ frame: Frame3Part; ratio?: number; tone?: 'paper' | 'stone' }>(), {
  ratio: 193 / 1024,
  tone: 'paper',
})
</script>

<template>
  <div
    class="frame3"
    :class="`frame3--${tone}`"
    :style="{
      '--frame-left': `url(${frame.left})`,
      '--frame-mid': `url(${frame.middle})`,
      '--frame-right': `url(${frame.right})`,
      '--frame-cap-ratio': String(ratio),
    }"
  >
    <span class="frame3__band" aria-hidden="true"></span>
    <span class="frame3__cap frame3__cap--left" aria-hidden="true"></span>
    <span class="frame3__cap frame3__cap--right" aria-hidden="true"></span>
    <div class="frame3__body">
      <slot />
    </div>
  </div>
</template>
