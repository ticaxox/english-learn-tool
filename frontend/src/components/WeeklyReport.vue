<script setup lang="ts">
/**
 * The last seven days at a glance: activity bars, weekly goals and the streak.
 */
import { computed, onMounted, ref } from 'vue'
import ErrorNotice from './ErrorNotice.vue'
import { fetchWeekly, type GamificationWeekly } from '../api/progress'

const weekly = ref<GamificationWeekly | null>(null)
const error = ref<unknown>(null)

const peak = computed(() => Math.max(1, ...(weekly.value?.days ?? []).map((day) => day.xp)))

function weekday(date: string): string {
  const parsed = new Date(`${date}T00:00:00`)
  if (Number.isNaN(parsed.getTime())) return ''
  return new Intl.DateTimeFormat('zh-CN', { weekday: 'narrow' }).format(parsed)
}

async function load(): Promise<void> {
  error.value = null
  try {
    weekly.value = await fetchWeekly()
  } catch (loadError) {
    error.value = loadError
  }
}

onMounted(() => {
  void load()
})
</script>

<template>
  <section class="weekly-report" aria-labelledby="weekly-report-title">
    <header class="weekly-report__head">
      <div>
        <h3 id="weekly-report-title">本周学习</h3>
        <p class="field-hint">
          <template v-if="weekly">学习 {{ weekly.activeDays }} 天 · {{ weekly.xp }} XP</template>
          <template v-else>最近 7 天</template>
        </p>
      </div>
    </header>

    <ErrorNotice v-if="error" :error="error" retry-label="重新读取" @retry="load" />

    <template v-else-if="weekly">
      <ol class="weekly-bars" aria-label="每天获得的经验">
        <li
          v-for="day in weekly.days"
          :key="day.date"
          :class="{ 'is-active': day.active }"
          :title="`${day.date}：${day.xp} XP`"
        >
          <span class="weekly-bars__bar" :style="{ height: `${Math.max(6, Math.round(day.xp / peak * 100))}%` }"></span>
          <small>{{ weekday(day.date) }}</small>
        </li>
      </ol>

      <ul class="weekly-goals" aria-label="周目标">
        <li v-for="goal in weekly.goals" :key="goal.key" :class="{ 'is-done': goal.completed }">
          <span class="weekly-goals__check" aria-hidden="true">{{ goal.completed ? '✓' : '' }}</span>
          <span>{{ goal.label }}</span>
          <small>{{ Math.min(goal.progress, goal.target) }} / {{ goal.target }}</small>
        </li>
      </ul>
    </template>
  </section>
</template>
