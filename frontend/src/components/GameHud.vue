<script setup lang="ts">
/**
 * The player bar: level ring, XP fill, lamp oil, streak and today's ring.
 *
 * Everything animates from the server's progress numbers; the component never
 * invents a value. A level change plays one celebratory pulse.
 */
import { computed, onMounted, ref, watch } from 'vue'
import AppIcon from './AppIcon.vue'
import HobMark from './HobMark.vue'
import RewardMark from './RewardMark.vue'
import { useGamification } from '../composables/useGamification'
import { breathe, bump, countUp, popIn } from '../composables/useMotion'

const gamification = useGamification()
const progress = gamification.progress

const xpValue = ref<HTMLElement | null>(null)
const root = ref<HTMLElement | null>(null)
const levelBadge = ref<HTMLElement | null>(null)
const hobRef = ref<HTMLElement | null>(null)

const level = computed(() => progress.value?.level ?? null)
const xpPercent = computed(() => {
  const value = level.value
  if (!value || value.xpForNextLevel <= 0) return 0
  return Math.min(100, Math.round((value.xpIntoLevel / value.xpForNextLevel) * 100))
})
const questDone = computed(() =>
  (progress.value?.quests ?? []).filter((quest) => quest.completed).length,
)
const questTotal = computed(() => (progress.value?.quests ?? []).length)

onMounted(async () => {
  if (!progress.value) await gamification.load()
  // Count the XP inside this level: the bar and the denominator show the same thing.
  if (xpValue.value) countUp(xpValue.value, level.value?.xpIntoLevel ?? 0)
  const stats = root.value ? Array.from(root.value.querySelectorAll('.hud-stat')) : []
  popIn(stats, { y: 10, stagger: 0.07 })
  breathe(hobRef.value)
})

watch(
  () => progress.value?.level.level,
  (next, previous) => {
    if (next && previous && next > previous) bump(levelBadge.value, 1.35)
  },
)
</script>

<template>
  <section ref="root" class="game-hud" aria-label="学习进度">
    <div class="hud-player">
      <span ref="levelBadge" class="hud-level" :style="{ '--fill': `${xpPercent}%` }">
        <span class="hud-level__inner">
          <small>Lv</small>
          <strong>{{ level?.level ?? 1 }}</strong>
        </span>
      </span>
      <div class="hud-ident">
        <strong class="hud-title">{{ level?.title ?? '点灯人' }}</strong>
        <span class="hud-xp">
          <span class="hud-xp__track" aria-hidden="true">
            <span class="hud-xp__fill" :style="{ width: `${xpPercent}%` }"></span>
          </span>
          <em ref="xpValue">0</em>
          <i>/ {{ level?.xpForNextLevel ?? 0 }} XP</i>
        </span>
      </div>
    </div>

    <ul class="hud-stats" aria-label="今日状态">
      <li class="hud-stat hud-stat--crumbs">
        <RewardMark mark="oil" :size="15" />
        <strong>{{ progress?.crumbs ?? 0 }}</strong>
        <span>灯油</span>
      </li>
      <li class="hud-stat hud-stat--streak" :class="{ 'is-hot': (progress?.streak ?? 0) > 0 }">
        <svg class="hud-flame" viewBox="0 0 24 24" aria-hidden="true">
          <path class="hud-flame__body" d="M12 2.2c.5 2.8 2.2 4 3.4 5.8 1 1.4 1.6 2.9 1.6 4.6a5 5 0 0 1-10 0c0-1.4.4-2.6 1.1-3.7.3 1.3 1 2.2 2 2.6.1-3.3.5-6.3 1.9-9.3Z" />
          <path class="hud-flame__core" d="M12 10.4c.3 1.7 1.7 2.4 1.7 4.1a1.7 1.7 0 0 1-3.4 0c0-1.7 1.4-2.4 1.7-4.1Z" />
        </svg>
        <strong>{{ progress?.streak ?? 0 }}</strong>
        <span>天连续</span>
      </li>
      <li class="hud-stat hud-stat--quests">
        <AppIcon name="spark" />
        <strong>{{ questDone }}/{{ questTotal }}</strong>
        <span>今日任务</span>
      </li>
    </ul>

    <span ref="hobRef" class="hud-hob">
      <HobMark size="medium" :mood="gamification.hobMood.value" />
    </span>
  </section>
</template>
