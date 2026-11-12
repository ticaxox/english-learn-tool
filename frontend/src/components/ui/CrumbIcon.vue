<script setup lang="ts">
/**
 * The drawn icons the control kit uses, in place of glyphs.
 *
 * A `×`, `←`, `→` borrowed from a font brings the font's weight, baseline and
 * optical size with it: they sit a pixel low next to real icons, thin out at
 * large sizes and thicken at small ones, and a screen reader announces the
 * character's name rather than the action. These are one set — 24 grid, round
 * caps, same stroke weight — so a close button in a dialog and a next arrow in
 * a paginator are the same drawing at the same weight.
 *
 * Decorative by default (`aria-hidden`): the button around them carries the
 * label. Pass `label` only when the icon is the sole content of something that
 * is not a button.
 *
 * Icons: close · remove · prev · next · arrow · avatar · search · clear · plus
 * minus · upload · check · chevron
 */
import { computed } from 'vue'

type IconName =
  | 'close' | 'remove' | 'prev' | 'next' | 'arrow' | 'avatar'
  | 'search' | 'clear' | 'plus' | 'minus' | 'upload' | 'check' | 'chevron'

const props = withDefaults(defineProps<{
  name: IconName
  /** Rendered size in px. 24 is the grid the paths were drawn on. */
  size?: number
  /** Accessible name. Omit for decorative icons inside a labelled button. */
  label?: string
}>(), {
  size: 20,
  label: undefined,
})

const decorative = computed(() => !props.label)
</script>

<template>
  <svg
    class="crumb-icon"
    :class="`crumb-icon--${name}`"
    :width="size"
    :height="size"
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    stroke-width="1.9"
    stroke-linecap="round"
    stroke-linejoin="round"
    :aria-hidden="decorative ? 'true' : undefined"
    :role="decorative ? undefined : 'img'"
    :aria-label="label"
  >
    <!-- close: two equal strokes, 90° apart, optically centred -->
    <template v-if="name === 'close'">
      <path d="M6.8 6.8 L17.2 17.2" />
      <path d="M17.2 6.8 L6.8 17.2" />
    </template>

    <!-- remove: a smaller × inside a ring, so a destructive × reads differently
         from a dialog's close -->
    <template v-else-if="name === 'remove'">
      <circle class="crumb-icon__ring" cx="12" cy="12" r="10.2" stroke-width="1.2" opacity="0" />
      <path d="M8.6 8.6 L15.4 15.4" />
      <path d="M15.4 8.6 L8.6 15.4" />
    </template>

    <template v-else-if="name === 'prev'">
      <path d="M14.4 6.4 L8.8 12 L14.4 17.6" />
      <path class="crumb-icon__shaft" d="M9 12 H18.4" opacity="0" />
    </template>

    <template v-else-if="name === 'next'">
      <path d="M9.6 6.4 L15.2 12 L9.6 17.6" />
      <path class="crumb-icon__shaft" d="M15 12 H5.6" opacity="0" />
    </template>

    <template v-else-if="name === 'arrow'">
      <path d="M4.6 12 H18.2" />
      <path d="M13.4 7.2 L18.2 12 L13.4 16.8" />
    </template>

    <template v-else-if="name === 'avatar'">
      <circle class="crumb-icon__avatar-body" cx="12" cy="12" r="9" fill="currentColor" stroke="none" opacity=".18" />
      <circle cx="12" cy="12" r="9" />
      <circle cx="9.4" cy="10.4" r="1.1" fill="currentColor" stroke="none" />
      <circle cx="14.6" cy="10.4" r="1.1" fill="currentColor" stroke="none" />
      <path d="M9.2 14.2 Q12 16.4 14.8 14.2" />
    </template>

    <template v-else-if="name === 'search'">
      <circle cx="11" cy="11" r="7" />
      <path d="M16.5 16.5 L21 21" />
    </template>

    <template v-else-if="name === 'clear'">
      <path d="M7 7 L17 17" />
      <path d="M17 7 L7 17" />
    </template>

    <template v-else-if="name === 'plus'">
      <path d="M12 6 V18" />
      <path d="M6 12 H18" />
    </template>

    <template v-else-if="name === 'minus'">
      <path d="M6 12 H18" />
    </template>

    <template v-else-if="name === 'upload'">
      <path d="M12 16 V5" />
      <path d="M7.5 9.5 L12 5 L16.5 9.5" />
      <path d="M4 16 v2.5 A1.5 1.5 0 0 0 5.5 20 h13 a1.5 1.5 0 0 0 1.5 -1.5 V16" />
    </template>

    <template v-else-if="name === 'check'">
      <path d="M5 12.5 L9.5 17 L19 6.5" />
    </template>

    <template v-else-if="name === 'chevron'">
      <path d="M6 9.5 L12 15.5 L18 9.5" />
    </template>
  </svg>
</template>
