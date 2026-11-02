<script setup lang="ts">
/**
 * Today's real study statistics from `GET /learning/stats`.
 */
import { computed, onMounted, ref } from 'vue'
import ErrorNotice from './ErrorNotice.vue'
import LoadingState from './LoadingState.vue'
import { fetchLearningStats } from '../api/learning'
import type { LearningStats } from '../types/learning'

const props = withDefaults(defineProps<{ compact?: boolean }>(), { compact: false })
const stats = ref<LearningStats | null>(null)
const loading = ref(false)
const error = ref<unknown>(null)

const streakStamps = computed(() => Math.min(stats.value?.streakDays ?? 0, 7))
const percent = computed(() => {
  if (!stats.value || stats.value.goalMinutes <= 0) return 0
  return Math.min(100, Math.round((stats.value.activeMinutes / stats.value.goalMinutes) * 100))
})

async function load(): Promise<void> {
  loading.value = true
  error.value = null
  try {
    stats.value = await fetchLearningStats()
  } catch (requestError) {
    stats.value = null
    error.value = requestError
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  void load()
})

defineExpose({ load })
</script>

<template>
  <section
    class="panel study-stats member-stats-panel"
    :class="{ 'study-stats--compact': props.compact }"
    aria-labelledby="study-stats-title"
  >
    <div class="study-stats__heading">
      <h2 id="study-stats-title">{{ props.compact ? '连续学习' : '今日统计' }}</h2>
      <DivButton v-if="!props.compact" class="button-secondary button-small" type="button" :disabled="loading" @click="load">
        {{ loading ? '读取中…' : '刷新统计' }}
      </DivButton>
    </div>

    <p v-if="!stats && !error && !loading" class="inline-note">尚未记录学习时间。</p>
    <LoadingState v-else-if="loading" label="正在读取今日统计…" />
    <ErrorNotice v-else-if="error" :error="error" retry-label="重新读取统计" @retry="load" />

    <template v-else-if="stats">
      <p class="study-stats__value">
        <strong>{{ stats.activeMinutes }}</strong>
        <span>/ {{ stats.goalMinutes }} 分钟</span>
        <span v-if="stats.goalReached" class="study-stats__badge">已达标</span>
      </p>
      <div
        class="progress"
        role="progressbar"
        :aria-valuenow="stats.activeMinutes"
        :aria-valuemin="0"
        :aria-valuemax="Math.max(stats.goalMinutes, 1)"
        :aria-label="`今日学习分钟 ${stats.activeMinutes} / ${stats.goalMinutes}`"
      >
        <span :style="{ width: `${percent}%` }"></span>
      </div>
      <div v-if="stats.streakDays !== null" class="member-streak-block">
        <div class="member-stamp-row" aria-hidden="true">
          <span
            v-for="index in 7"
            :key="index"
            :class="{ 'is-filled': index <= streakStamps, 'is-today': index === streakStamps }"
          >{{ index }}</span>
        </div>
        <p class="inline-note">连续学习 {{ stats.streakDays }} 天。</p>
      </div>
      <p v-if="!props.compact" class="inline-note">
        统计日期 {{ stats.localDate }} · 数据来源：
        <span v-if="stats.sources.length === 0">未标注</span>
        <span v-else>{{ stats.sources.join('、') }}</span>
      </p>
    </template>
  </section>
</template>