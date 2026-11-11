<script setup lang="ts">
/**
 * The reward marks: a level crest, a crumb coin and a streak candle.
 *
 * Drawn as SVG rather than cut from the `badges-*` sheet: that sheet is a
 * design reference whose margins differ every time it is generated, so there
 * are no reliable coordinates to slice. The shapes follow it.
 *
 * Flat fill, one outline weight, no gradients and no glow — the same language
 * as the rest of the art.
 */
defineProps<{
  /** 1 to 5; each step changes the crest's colour and its mark. */
  level?: number
  size?: number
}>()
</script>

<template>
  <span class="crest-wrap">
    <svg
      class="crest"
      :class="`crest--level-${Math.min(5, Math.max(1, level ?? 1))}`"
      :width="size ?? 56"
      :height="size ?? 56"
      viewBox="0 0 64 64"
      fill="none"
      aria-hidden="true"
    >
    <!-- The shield: a bitten biscuit edge that deepens with the level. -->
    <path
      d="M32 3 58 11v22c0 14-11 24-26 28C17 57 6 47 6 33V11L32 3Z"
      fill="var(--crest-face)"
      stroke="var(--crest-edge)"
      stroke-width="3.4"
      stroke-linejoin="round"
    />
    <!-- The pressed rim. -->
    <path
      d="M32 8.5 52.5 15v18c0 10.5-8.5 18.5-20.5 21.5C20 51.5 11.5 43.5 11.5 33V15L32 8.5Z"
      stroke="var(--crest-rim)"
      stroke-width="2"
      stroke-linejoin="round"
    />
    <!-- The level, cut into the crest. -->
    <text
      x="32"
      y="41"
      text-anchor="middle"
      font-family="Georgia, 'Times New Roman', serif"
      font-size="23"
      font-weight="700"
      fill="var(--crest-ink)"
    >{{ Math.min(5, Math.max(1, level ?? 1)) }}</text>
    </svg>
    <!-- The level as text too: the number must survive without the drawing. -->
    <span class="crest-level-text">Lv.{{ Math.min(5, Math.max(1, level ?? 1)) }}</span>
  </span>
</template>

<style scoped>
.crest-wrap {
  display: inline-flex;
  flex: 0 0 auto;
}

.crest {
  display: block;
}

/* The level survives without the drawing, so it is in the DOM too. */
.crest-level-text {
  position: absolute;
  width: 1px;
  height: 1px;
  overflow: hidden;
  clip-path: inset(50%);
  white-space: nowrap;
}

.crest--level-1 { --crest-face: #E8C58A; --crest-edge: #784A22; --crest-rim: #C49A5C; --crest-ink: #5A3A16; }
.crest--level-2 { --crest-face: #DFB067; --crest-edge: #6B3E19; --crest-rim: #B98A4C; --crest-ink: #4A2C0E; }
.crest--level-3 { --crest-face: #D2964A; --crest-edge: #5E3414; --crest-rim: #A8743A; --crest-ink: #3E220A; }
.crest--level-4 { --crest-face: #C57C36; --crest-edge: #52290E; --crest-rim: #9A5C2A; --crest-ink: #331906; }
.crest--level-5 { --crest-face: #B85F2A; --crest-edge: #471F0A; --crest-rim: #8A4A1E; --crest-ink: #FFF3DC; }
</style>
