<script setup lang="ts">
/**
 * The player bar: level ring, XP fill, crumbs, streak and today's ring.
 *
 * Everything animates from the server's progress numbers; the component never
 * invents a value. A level change plays one celebratory pulse.
 */
import { computed, onMounted, ref, watch } from 'vue'
import AppIcon from './AppIcon.vue'
import CrumboMark from './CrumboMark.vue'
import { useGamification } from '../composables/useGamification'
import { breathe, bump, countUp, popIn } from '../composables/useMotion'

const gamification = useGamification()
const progress = gamification.progress

const xpValue = ref<HTMLElement | null>(null)
const root = ref<HTMLElement | null>(null)
const levelBadge = ref<HTMLElement | null>(null)
const crumboRef = ref<HTMLElement | null>(null)

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
  if (xpValue.value) countUp(xpValue.value, progress.value?.xp ?? 0)
  const stats = root.value ? Array.from(root.value.querySelectorAll('.hud-stat')) : []
  popIn(stats, { y: 10, stagger: 0.07 })
  breathe(crumboRef.value)
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
        <strong class="hud-title">{{ level?.title ?? '拾屑人' }}</strong>
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
        <AppIcon name="star" />
        <strong>{{ progress?.crumbs ?? 0 }}</strong>
        <span>碎屑</span>
      </li>
      <li class="hud-stat hud-stat--streak" :class="{ 'is-hot': (progress?.streak ?? 0) > 0 }">
        <span class="hud-flame" aria-hidden="true">🔥</span>
        <strong>{{ progress?.streak ?? 0 }}</strong>
        <span>天连续</span>
      </li>
      <li class="hud-stat hud-stat--quests">
        <AppIcon name="spark" />
        <strong>{{ questDone }}/{{ questTotal }}</strong>
        <span>今日任务</span>
      </li>
    </ul>

    <span ref="crumboRef" class="hud-crumbo">
      <CrumboMark size="medium" :mood="gamification.crumboMood.value" />
    </span>
  </section>
</template>
