<script setup lang="ts">
withDefaults(
  defineProps<{
    size?: 'small' | 'medium' | 'hero'
  }>(),
  {
    size: 'medium',
  },
)
</script>

<template>
  <span class="whisker-crumb-mark" :class="`whisker-crumb-mark--${size}`" aria-hidden="true">
    <svg viewBox="0 0 64 64" role="presentation" focusable="false">
      <circle class="whisker-crumb-mark__cookie" cx="32" cy="32" r="28" />
      <path class="whisker-crumb-mark__hat" d="M21 8h22l2 14H19l2-14Z" />
      <path class="whisker-crumb-mark__hat-brim" d="M15 21h34c2 0 3 2 2 4H13c-1-2 0-4 2-4Z" />
      <circle class="whisker-crumb-mark__eye" cx="24" cy="33" r="2.2" />
      <circle class="whisker-crumb-mark__eye" cx="40" cy="33" r="2.2" />
      <path class="whisker-crumb-mark__nose" d="M30.4 35.5h3.2l-1.6 3.2-1.6-3.2Z" />
      <path class="whisker-crumb-mark__moustache" d="M18.5 40.1c4.8-5.4 9.5-5.1 13.5 1 4-6.1 8.7-6.4 13.5-1-2.1 4.4-5.6 6.5-10.2 6.2L32 43.8l-3.3 2.5c-4.6.3-8.1-1.8-10.2-6.2Z" />
      <path class="whisker-crumb-mark__bow" d="M23 50.5 29 53l-3.1 5-5.8-5.1 2.9-2.4Zm18 0L35 53l3.1 5 5.8-5.1-2.9-2.4Z" />
      <circle class="whisker-crumb-mark__knot" cx="32" cy="53.3" r="2.2" />
      <g class="whisker-crumb-mark__crumbs">
        <circle cx="10" cy="34" r="1.1" />
        <circle cx="53" cy="27" r="1.4" />
        <circle cx="51" cy="39" r="0.9" />
        <circle cx="21" cy="14" r="0.9" />
      </g>
    </svg>
  </span>
</template>

<style scoped>
.whisker-crumb-mark {
  display: inline-grid;
  flex: 0 0 auto;
  place-items: center;
  color: var(--cocoa-900, #2b1c17);
}

.whisker-crumb-mark svg {
  display: block;
  width: 100%;
  height: auto;
  overflow: visible;
}

.whisker-crumb-mark--small {
  width: 2.25rem;
}

.whisker-crumb-mark--medium {
  width: 3.25rem;
}

.whisker-crumb-mark--hero {
  width: clamp(5.5rem, 12vw, 8rem);
}

.whisker-crumb-mark__cookie {
  fill: var(--cookie-200, #eed4a4);
  stroke: var(--cocoa-900, #2b1c17);
  stroke-width: 2.5;
}

.whisker-crumb-mark__hat,
.whisker-crumb-mark__hat-brim,
.whisker-crumb-mark__eye,
.whisker-crumb-mark__nose,
.whisker-crumb-mark__knot,
.whisker-crumb-mark__crumbs {
  fill: var(--cocoa-900, #2b1c17);
}

.whisker-crumb-mark__moustache {
  fill: var(--cocoa-900, #2b1c17);
}

.whisker-crumb-mark__bow {
  fill: var(--jam-500, #c8555a);
  stroke: var(--cocoa-900, #2b1c17);
  stroke-width: 1.5;
  stroke-linejoin: round;
}

.whisker-crumb-mark__crumbs {
  opacity: 0.72;
}
</style>
