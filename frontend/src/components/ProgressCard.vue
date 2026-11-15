<script setup lang="ts">
/**
 * Level ring, streak and today's three quests.
 *
 * Everything is read from the server; the card never computes rewards itself.
 */
import { computed, onMounted, ref } from 'vue'
import LevelCrest from './LevelCrest.vue'
import RewardMark from './RewardMark.vue'
import ErrorNotice from './ErrorNotice.vue'
import { fetchProgress, QUEST_LABELS, type GamificationProgress } from '../api/progress'

const progress = ref<GamificationProgress | null>(null)
const error = ref<unknown>(null)

const percent = computed(() => {
  const level = progress.value?.level
  if (!level || level.xpForNextLevel <= 0) return 0
  return Math.min(100, Math.round((level.xpIntoLevel / level.xpForNextLevel) * 100))
})

const quests = computed(() =>
  (progress.value?.quests ?? []).map((quest) => ({
    ...quest,
    label: QUEST_LABELS[quest.key] ?? quest.key,
    percent: quest.target > 0 ? Math.min(100, Math.round((quest.progress / quest.target) * 100)) : 0,
  })),
)

async function load(): Promise<void> {
  error.value = null
  try {
    progress.value = await fetchProgress()
  } catch (loadError) {
    error.value = loadError
  }
}

onMounted(() => {
  void load()
})
</script>

<template>
  <section class="progress-card" aria-label="学习进度">
    <ErrorNotice v-if="error" :error="error" retry-label="重新读取进度" @retry="load" />

    <template v-else-if="progress">
      <header class="progress-card__head">
        <LevelCrest
          class="progress-card__crest"
          :level="progress.level.level"
          :size="54"
          role="img"
          :aria-label="`等级 ${progress.level.level}，距离下一级 ${progress.level.xpForNextLevel - progress.level.xpIntoLevel} 经验`"
        />
        <div class="progress-card__meta">
          <strong>{{ progress.level.title }}</strong>
          <span class="progress-card__xp">
            <span class="progress-card__xptrack" aria-hidden="true">
              <span :style="{ width: `${percent}%` }"></span>
            </span>
            {{ progress.level.xpIntoLevel }} / {{ progress.level.xpForNextLevel }} XP
          </span>
          <span class="progress-card__crumbs">
            <RewardMark mark="oil" :size="16" /> 灯油 {{ progress.crumbs }}
          </span>
        </div>
        <div class="progress-card__streak" :class="{ 'is-active': progress.activeToday }">
          <RewardMark mark="candle" :size="18" />
          <strong>{{ progress.streak }}</strong>
          <span>天连续</span>
          <small v-if="progress.freezeTokens > 0" class="progress-card__freeze" title="本月还有护身符，断一天也能保住连续">
            护身符 ×{{ progress.freezeTokens }}
          </small>
        </div>
      </header>

      <ul class="progress-card__quests" aria-label="今日任务">
        <li
          v-for="quest in quests"
          :key="quest.key"
          :class="{ 'is-done': quest.completed }"
        >
          <span class="progress-card__check" aria-hidden="true">{{ quest.completed ? '✓' : '' }}</span>
          <span class="progress-card__quest">
            <strong>{{ quest.label }}</strong>
            <span class="progress-card__bar" aria-hidden="true">
              <span :style="{ width: `${quest.percent}%` }"></span>
            </span>
          </span>
          <span class="progress-card__value">
            {{ quest.progress }} / {{ quest.target }}
          </span>
        </li>
      </ul>
    </template>
  </section>
</template>
