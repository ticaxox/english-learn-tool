<script setup lang="ts">
/**
 * Motion lab: the three gamification surfaces mounted with sample payloads so
 * the animations can be judged by eye, without a backend.
 */
import { computed, ref } from 'vue'
import ChallengeDslMap from '../src/components/ChallengeDslMap.vue'
import WeeklyReport from '../src/components/WeeklyReport.vue'
import BadgeWall from '../src/components/BadgeWall.vue'
import ShelfPicker from '../src/components/ShelfPicker.vue'
import ThemeSwitch from '../src/components/ThemeSwitch.vue'
import WordbookShelfCard from '../src/components/WordbookShelfCard.vue'
import ArtImage from '../src/components/ArtImage.vue'
import WordbookDetailDialog from '../src/components/WordbookDetailDialog.vue'
import { illustration } from '../src/assets/halloween'
import { gsap } from '../src/composables/useMotion'
import { SHELF, mapDsl } from './data'

const MODULES = ['flashcard', 'choice', 'spelling'] as const
const LABELS = { flashcard: '翻卡', choice: '选择', spelling: '拼写' }

const round = ref(0)
const cleared = ref(3)
const slow = ref(false)
const detailId = ref<string | null>(null)
const selectedBook = computed(() => (detailId.value ? (SHELF as Array<{ id: string }>).find((item) => item.id === detailId.value) ?? null : null))

function replay(): void {
  round.value += 1
}

function step(): void {
  cleared.value = Math.min(4, cleared.value + 1)
}

function reset(): void {
  cleared.value = 3
  round.value += 1
}

/** Quarter speed, so a 0.8s move can actually be watched frame by frame. */
function toggleSlow(): void {
  slow.value = !slow.value
  gsap.globalTimeline.timeScale(slow.value ? 0.25 : 1)
}
</script>

<template>
  <div class="app-shell app-shell--member workspace-shell ia-workspace personal-workspace lab">
    <header class="lab-bar">
      <div class="lab-bar__title">
        <strong>动效试衣间</strong>
        <span>徽章翻转 · 周报点亮 · 地图走位</span>
      </div>
      <div class="lab-bar__actions">
        <ThemeSwitch />
        <button type="button" class="lab-button" @click="replay">重播入场</button>
        <button type="button" class="lab-button" @click="step">走一步</button>
        <button type="button" class="lab-button" :class="{ 'lab-button--on': slow }" @click="toggleSlow">
          {{ slow ? '慢放 ×0.25' : '正常速度' }}
        </button>
        <button type="button" class="lab-button lab-button--ghost" @click="reset">回到起点</button>
      </div>
    </header>

    <main class="lab-body">
      <section class="lab-block">
        <p class="lab-caption">书架 · 三种练法是三本书（悬停/聚焦时封面翻出来）</p>
        <ShelfPicker :modules="MODULES" :enabled="MODULES" :labels="LABELS" @pick="() => {}" />
      </section>

      <section class="lab-block">
        <p class="lab-caption">词书书架 · 立起来的封面</p>
        <div class="wordbooks-page member-wordbooks-page crumb-wordbooks lab-probe">
          <div class="wordbook-grid">
            <WordbookShelfCard
              v-for="book in SHELF"
              :key="book.id"
              :book="book"
              @detail="detailId = book.id"
            />
          </div>
        </div>
      </section>

      <WordbookDetailDialog
        v-if="selectedBook"
        :wordbook-id="selectedBook.id"
        :book="selectedBook as never"
        :can-activate="true"
        :can-export="true"
        :can-delete="true"
        :activating="false"
        @close="detailId = null"
      />

      <section class="lab-block">
        <p class="lab-caption">插画 · 同一构图的两次生成，切换时交叉淡出</p>
        <div class="lab-art-row">
          <ArtImage v-for="(set, key) in illustration" :key="key" class="lab-art" :set="set" />
        </div>
      </section>

      <section class="lab-block">
        <p class="lab-caption">地图 · 当前节点脉冲 + 走一步</p>
        <ChallengeDslMap :key="`map-${round}`" :dsl="mapDsl(cleared)" @select="() => {}" />
      </section>

      <section :key="`extras-${round}`" class="today-extras lab-extras">
        <WeeklyReport />
        <BadgeWall />
      </section>
    </main>
  </div>
</template>

<style scoped>
.lab {
  display: block;
  min-height: 100vh;
  padding: 18px clamp(14px, 4vw, 42px) 60px;
}

.lab-bar {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  align-items: center;
  justify-content: space-between;
  margin: 0 auto 18px;
  max-width: 1120px;
}

.lab-bar__title {
  display: grid;
  gap: 2px;
}

.lab-bar__title strong {
  font-size: 1.15rem;
  font-weight: 900;
}

.lab-bar__title span {
  color: var(--ui-muted);
  font-size: 0.78rem;
}

.lab-bar__actions {
  display: flex;
  gap: 8px;
}

.lab-button {
  padding: 8px 16px;
  border: 0;
  border-radius: 12px;
  background: var(--g-green);
  box-shadow: 0 4px 0 var(--g-green-edge);
  color: #fff;
  font: inherit;
  font-size: 0.85rem;
  font-weight: 900;
  cursor: pointer;
}

.lab-button:active {
  transform: translateY(3px);
  box-shadow: 0 1px 0 var(--g-green-edge);
}

.lab-button--ghost {
  background: var(--ui-surface);
  box-shadow: 0 4px 0 var(--ui-line);
  color: var(--ui-ink);
}

.lab-button--on {
  background: var(--g-orange);
  box-shadow: 0 4px 0 var(--g-orange-edge);
}

.lab-body {
  display: grid;
  gap: 18px;
  margin: 0 auto;
  max-width: 1120px;
}

.lab-block {
  display: grid;
  gap: 8px;
}

.lab-caption {
  margin: 0;
  color: var(--ui-muted);
  font-size: 0.78rem;
  font-weight: 800;
}

.lab-extras {
  margin-top: 0;
}

.lab-shelf-books {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(220px, 280px));
  gap: 16px;
}

.lab-art-row {
  display: flex;
  gap: 14px;
  align-items: flex-end;
  flex-wrap: wrap;
  padding: 14px;
  border: 2px solid var(--ui-line);
  border-radius: 16px;
  background: var(--ui-surface);
}

.lab-art {
  width: 84px;
}

@media (max-width: 820px) {
  .lab-extras {
    grid-template-columns: minmax(0, 1fr);
  }
}
</style>
