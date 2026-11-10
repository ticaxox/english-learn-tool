<script setup lang="ts">
/**
 * The lesson HUD: where you are, how you're doing, and the way out.
 *
 * Duolingo's loop is a run of single questions with a bar that fills and a
 * combo that climbs. This renders only what the session already knows —
 * position comes from the server's `remaining`, the combo is counted locally
 * because it is a run of correct answers within this run, not a stored stat.
 */
import { computed } from 'vue'

const props = defineProps<{
  /** 1-based card number inside this run. */
  index: number
  total: number
  /** Cards finished, for the bar. */
  done: number
  combo: number
  hearts: number
  maxHearts: number
  label: string
}>()

const emit = defineEmits<{ (event: 'exit'): void }>()

const percent = computed(() => {
  if (props.total <= 0) return 0
  return Math.max(0, Math.min(100, Math.round((props.done / props.total) * 100)))
})
</script>

<template>
  <header class="lesson-hud">
    <button class="lesson-hud__exit" type="button" aria-label="退出本次训练" @click="emit('exit')">
      <svg viewBox="0 0 24 24" aria-hidden="true">
        <path d="M6.8 6.8 L17.2 17.2" />
        <path d="M17.2 6.8 L6.8 17.2" />
      </svg>
    </button>

    <div class="lesson-hud__bar" role="progressbar" :aria-valuenow="percent" aria-valuemin="0" aria-valuemax="100"
         :aria-label="`本轮进度 ${percent}%`">
      <span class="lesson-hud__fill" :style="{ width: `${percent}%` }"></span>
    </div>

    <div class="lesson-hud__meta">
      <span class="lesson-hud__count">{{ index }} / {{ total || '—' }}</span>

      <span v-if="combo >= 2" class="lesson-hud__combo" :class="{ 'is-hot': combo >= 5 }"
            :aria-label="`连对 ${combo} 个`">
        <svg viewBox="0 0 24 24" aria-hidden="true">
          <path d="M12 3c2.6 3 4.4 4.9 4.4 7.6a4.4 4.4 0 0 1-8.8 0c0-1.1.4-2 .9-2.9.6 1 1.5 1.6 2.4 1.6 1.4 0 2.2-1.2 2.2-2.9 0-1-.4-2-1.1-3.4Z" />
        </svg>
        <b>{{ combo }}</b>
      </span>

      <span class="lesson-hud__hearts" :aria-label="`剩余 ${hearts} 颗心`">
        <svg v-for="n in maxHearts" :key="n" viewBox="0 0 24 24" aria-hidden="true"
             :class="{ 'is-empty': n > hearts }">
          <path d="M12 20s-7-4.4-7-9.1A4 4 0 0 1 12 8a4 4 0 0 1 7 2.9C19 15.6 12 20 12 20Z" />
        </svg>
      </span>
    </div>
  </header>
</template>

<style scoped>
/* No plate, no pill, no shadow: the HUD is a thin strip of state that sits on
   the page like a game's top bar, not a card among cards. */
.lesson-hud {
  display: grid;
  grid-template-columns: auto 1fr auto;
  align-items: center;
  gap: 0.85rem;
  padding: 0.4rem 0 0.7rem;
}

.lesson-hud__exit {
  width: 2.1rem;
  height: 2.1rem;
  display: grid;
  place-items: center;
  border: 0;
  border-radius: 50%;
  background: transparent;
  color: var(--ui-muted, #7d6247);
  cursor: pointer;
  transition: background-color 140ms ease, color 140ms ease;
}

.lesson-hud__exit:hover { background: rgb(53 36 15 / 8%); color: var(--ui-ink, #35240f); }
.lesson-hud__exit:focus-visible { outline: 2.5px solid var(--g-orange, #ff9600); outline-offset: 2px; }
.lesson-hud__exit svg { width: 1rem; height: 1rem; fill: none; stroke: currentColor; stroke-width: 2.4; stroke-linecap: round; }

.lesson-hud__bar {
  position: relative;
  height: 0.85rem;
  border-radius: 999px;
  background: rgb(53 36 15 / 10%);
  overflow: hidden;
}

.lesson-hud__fill {
  display: block;
  height: 100%;
  border-radius: inherit;
  background: linear-gradient(90deg, var(--g-orange, #ff9600), var(--g-gold, #ffc800));
  transition: width 420ms cubic-bezier(0.3, 1.1, 0.4, 1);
}

.lesson-hud__meta { display: flex; align-items: center; gap: 0.7rem; }

.lesson-hud__count {
  font-size: 0.82rem;
  font-variant-numeric: tabular-nums;
  color: var(--ui-muted, #7d6247);
  white-space: nowrap;
}

.lesson-hud__combo {
  display: inline-flex;
  align-items: center;
  gap: 0.2rem;
  padding: 0.1rem 0.5rem 0.1rem 0.35rem;
  border-radius: 999px;
  background: var(--g-orange-soft, #ffeacd);
  color: var(--g-orange-edge, #cf7400);
  font-size: 0.8rem;
  animation: comboPop 320ms cubic-bezier(0.34, 1.6, 0.64, 1);
}

.lesson-hud__combo.is-hot { background: var(--g-red-soft, #ffe4e0); color: var(--g-red-edge, #a82e2e); }
.lesson-hud__combo svg { width: 0.95rem; height: 0.95rem; fill: none; stroke: currentColor; stroke-width: 1.9; stroke-linejoin: round; }
.lesson-hud__combo b { font-variant-numeric: tabular-nums; }

@keyframes comboPop {
  from { transform: scale(0.6); opacity: 0; }
  to { transform: scale(1); opacity: 1; }
}

.lesson-hud__hearts { display: inline-flex; gap: 0.15rem; }
.lesson-hud__hearts svg { width: 1rem; height: 1rem; stroke: var(--g-red, #d63c3c); stroke-width: 2; fill: var(--g-red, #d63c3c); transition: opacity 200ms ease; }
.lesson-hud__hearts svg.is-empty { fill: transparent; stroke: rgb(53 36 15 / 25%); }

@media (prefers-reduced-motion: reduce) {
  .lesson-hud__fill, .lesson-hud__combo { transition: none; animation: none; }
}

@media (max-width: 560px) {
  .lesson-hud { gap: 0.6rem; padding: 0.55rem 0.7rem; }
  .lesson-hud__count { display: none; }
}
</style>
