<script setup lang="ts">
/**
 * DEV ONLY — the mascot at every size it is actually drawn at.
 *
 * Not a product page and not linked from anywhere: it exists so the painted
 * Hob can be checked at 2rem / 4rem / 7rem / 11rem on the real canvas tokens,
 * in both themes, without a backend. The route is registered only when
 * `import.meta.env.DEV`, so it never reaches a build.
 */
import ArtImage from '../components/ArtImage.vue'
import HobMark from '../components/HobMark.vue'
import { illustration } from '../assets/halloween'
import { isNight, toggleTheme } from '../composables/useTheme'

const sizes = [
  { size: 'small' as const, label: '2rem', where: 'HUD、侧栏品牌位' },
  { size: 'medium' as const, label: '4rem', where: '今日页、词书架' },
  { size: 'large' as const, label: '7rem', where: '升级动画' },
  { size: 'hero' as const, label: '11rem', where: '主立绘位' },
]
</script>

<template>
  <div class="personal-workspace mascot-preview">
    <header class="mascot-preview__bar">
      <div>
        <p class="mascot-preview__eyebrow">DEV ONLY · 素材预览</p>
        <h1>Hob 在主界面里的实际尺寸</h1>
      </div>
      <button type="button" class="mascot-preview__toggle" @click="toggleTheme()">
        {{ isNight ? '切到白天' : '切到夜间' }}
      </button>
    </header>

    <section class="mascot-preview__sizes">
      <figure v-for="s in sizes" :key="s.size" class="mascot-preview__cell">
        <span class="mascot-preview__body">
          <HobMark :size="s.size" :mood="s.size === 'large' ? 'glowing' : 'normal'" />
        </span>
        <figcaption>
          <b>{{ s.label }}</b>
          <span>{{ s.where }}</span>
        </figcaption>
      </figure>
    </section>

    <section class="mascot-preview__panel">
      <span class="mascot-preview__body">
        <HobMark size="medium" mood="happy" />
      </span>
      <div>
        <p class="mascot-preview__eyebrow">今日</p>
        <h2>今天有 12 个词到期</h2>
        <p class="mascot-preview__copy">
          灯还亮着。先添一把油，把到期的词过一遍。
        </p>
      </div>
    </section>

    <section class="mascot-preview__panel mascot-preview__panel--tight">
      <span class="mascot-preview__body">
        <HobMark size="small" />
      </span>
      <p class="mascot-preview__copy">HUD 里它只有 2rem，跟灯油、连续天数挤在同一行。</p>
    </section>

    <h2 class="mascot-preview__section">这些位置的画还没换</h2>
    <section class="mascot-preview__sizes mascot-preview__sizes--two">
      <figure class="mascot-preview__cell">
        <span class="mascot-preview__art"><ArtImage :set="illustration.empty" /></span>
        <figcaption><b>空态</b><span>illustration.empty</span></figcaption>
      </figure>
      <figure class="mascot-preview__cell">
        <span class="mascot-preview__art"><ArtImage :set="illustration.result" /></span>
        <figcaption><b>练习结果页</b><span>illustration.result</span></figcaption>
      </figure>
    </section>
  </div>
</template>

<style scoped>
/* The class carries the day/night token set, but the app styles it as a
 * 232px-sidebar grid. A two-class selector beats that single-class rule, so this
 * page keeps the tokens and loses the shell layout. */
.personal-workspace.mascot-preview {
  display: block;
  grid-template-columns: none;
  min-height: 100vh;
  padding: 32px 40px 64px;
  color: var(--ui-ink);
  font-family: var(--font-display);
}

.mascot-preview__bar {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 24px;
  max-width: 1080px;
  margin-bottom: 26px;
}

.mascot-preview__bar h1 {
  margin: 2px 0 0;
  font-size: 1.5rem;
}

.mascot-preview__eyebrow {
  margin: 0;
  font-size: 0.68rem;
  letter-spacing: 0.16em;
  text-transform: uppercase;
  color: var(--ui-muted);
}

.mascot-preview__toggle {
  border: 1px solid var(--ui-line);
  border-radius: 999px;
  background: var(--ui-surface);
  color: var(--ui-ink);
  padding: 8px 18px;
  font: inherit;
  font-size: 0.82rem;
  cursor: pointer;
}

.mascot-preview__sizes {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 16px;
  max-width: 1080px;
}

.mascot-preview__cell {
  margin: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 10px;
  padding: 20px 14px 14px;
  background: var(--ui-surface);
  border: 1px solid var(--ui-line);
  border-radius: var(--ui-radius-md);
}

.mascot-preview__cell figcaption {
  text-align: center;
  font-size: 0.72rem;
  color: var(--ui-muted);
  line-height: 1.6;
}

.mascot-preview__cell b {
  display: block;
  color: var(--ui-ink);
  font-size: 0.8rem;
}

.mascot-preview__body {
  display: flex;
  align-items: flex-end;
  min-height: 11rem;
}

.mascot-preview__panel {
  display: flex;
  align-items: center;
  gap: 22px;
  max-width: 1080px;
  margin-top: 18px;
  padding: 20px 26px;
  background: var(--ui-surface);
  border: 1px solid var(--ui-line);
  border-radius: var(--ui-radius-lg);
}

.mascot-preview__panel .mascot-preview__body {
  min-height: 0;
}

.mascot-preview__panel h2 {
  margin: 2px 0 6px;
  font-size: 1.1rem;
}

.mascot-preview__copy {
  margin: 0;
  font-size: 0.8rem;
  color: var(--ui-muted);
  line-height: 1.7;
}

.mascot-preview__panel--tight {
  padding: 14px 22px;
}

.mascot-preview__section {
  max-width: 1080px;
  margin: 34px 0 12px;
  font-size: 0.78rem;
  letter-spacing: 0.14em;
  text-transform: uppercase;
  color: var(--ui-muted);
}

.mascot-preview__sizes--two {
  grid-template-columns: repeat(2, 1fr);
  max-width: 640px;
}

.mascot-preview__art {
  display: block;
  width: 100%;
  max-width: 190px;
}

.mascot-preview__art :deep(.art-swap),
.mascot-preview__art :deep(.art-swap__stack) {
  display: block;
  width: 100%;
}
</style>
