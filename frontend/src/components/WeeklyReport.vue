<script setup lang="ts">
/**
 * The last seven days at a glance: a row of candles, one per day.
 *
 * The flame is the point. A day you studied is lit and its candle stands as
 * tall as the XP earned; a day you did not stays cold wax. The row lights up
 * left to right the first time it is looked at, and the weekly goals stamp
 * themselves down after it.
 */
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from 'vue'
import ErrorNotice from './ErrorNotice.vue'
import { fetchWeekly, type GamificationWeekly } from '../api/progress'
import { countUp, gsap, motionAllowed } from '../composables/useMotion'
import { candles } from '../assets/halloween'
import { themeMode } from '../composables/useTheme'

const weekly = ref<GamificationWeekly | null>(null)
const error = ref<unknown>(null)
const reportRef = ref<HTMLElement | null>(null)
const daysRef = ref<HTMLElement | null>(null)
const xpRef = ref<HTMLElement | null>(null)
let observer: IntersectionObserver | null = null
let lit = false

const CANDLE_MIN = 10
const CANDLE_MAX = 76

const peak = computed(() => Math.max(1, ...(weekly.value?.days ?? []).map((day) => day.xp)))

/** Every day gets a candle; height is its XP share of the best day. */
/** The candle's height carries the day's XP; the art scales with it. */
function candleHeight(xp: number): number {
  if (xp <= 0) return CANDLE_MIN
  return CANDLE_MIN + (xp / peak.value) * (CANDLE_MAX - CANDLE_MIN)
}

function weekday(date: string): string {
  const parsed = new Date(`${date}T00:00:00`)
  if (Number.isNaN(parsed.getTime())) return ''
  return new Intl.DateTimeFormat('zh-CN', { weekday: 'narrow' }).format(parsed)
}

function dayNumber(date: string): string {
  const parsed = new Date(`${date}T00:00:00`)
  if (Number.isNaN(parsed.getTime())) return ''
  return String(parsed.getDate())
}

/** The last day in the window is today. */
function isToday(index: number): boolean {
  return index === (weekly.value?.days.length ?? 0) - 1
}

function numbers(): void {
  if (!weekly.value) return
  countUp(daysRef.value, weekly.value.activeDays, { duration: 0.9 })
  countUp(xpRef.value, weekly.value.xp, { duration: 1.2 })
}

function lightUp(): void {
  if (lit || !weekly.value) return
  lit = true
  numbers()

  const root = reportRef.value
  if (!root) return
  const candles = Array.from(root.querySelectorAll<HTMLElement>('.weekly-day__candle'))
  const holders = Array.from(root.querySelectorAll<HTMLElement>('.weekly-day'))
  const goals = Array.from(root.querySelectorAll<HTMLElement>('.weekly-goals li'))

  if (!motionAllowed()) {
    for (const candle of candles) candle.style.transform = 'scaleY(1)'
    return
  }

  const timeline = gsap.timeline({ delay: 0.12 })
  timeline.fromTo(
    candles,
    { scaleY: 0.04, opacity: 0.4 },
    { scaleY: 1, opacity: 1, duration: 0.62, ease: 'back.out(1.5)', stagger: 0.075 },
  )
  timeline.fromTo(
    holders.map((holder) => holder.querySelector('.weekly-day__art')).filter(Boolean),
    { scale: 0, opacity: 0, y: -6 },
    { scale: 1, opacity: 1, y: 0, duration: 0.42, ease: 'back.out(2.2)', stagger: 0.075 },
    '-=0.38',
  )
  timeline.from(
    goals,
    { x: -14, opacity: 0, duration: 0.36, ease: 'power2.out', stagger: 0.08 },
    '-=0.1',
  )
  timeline.add(() => {
    for (const goal of goals) {
      if (goal.classList.contains('is-done')) goal.classList.add('is-stamping')
    }
  }, '-=0.24')
}

let inView = false

/** Light the row only once it has data and someone is looking at it. */
function tryLight(): void {
  if (!inView || lit || !weekly.value) return
  observer?.disconnect()
  observer = null
  lightUp()
}

async function load(): Promise<void> {
  error.value = null
  try {
    weekly.value = await fetchWeekly()
    await nextTick()
    tryLight()
  } catch (loadError) {
    error.value = loadError
  }
}

onMounted(() => {
  void load()
  if (typeof IntersectionObserver === 'undefined' || !reportRef.value) {
    inView = true
    return
  }
  observer = new IntersectionObserver((entries) => {
    if (!entries.some((entry) => entry.isIntersecting)) return
    inView = true
    tryLight()
  }, { threshold: 0.2 })
  observer.observe(reportRef.value)
})

onBeforeUnmount(() => {
  observer?.disconnect()
  observer = null
})
</script>

<template>
  <section ref="reportRef" class="weekly-report" aria-labelledby="weekly-report-title">
    <header class="weekly-report__head">
      <div>
        <h3 id="weekly-report-title">本周学习</h3>
        <p class="field-hint">
          <template v-if="weekly">
            学习 <strong ref="daysRef">{{ weekly.activeDays }}</strong> 天 ·
            <strong ref="xpRef">{{ weekly.xp }}</strong> XP
          </template>
          <template v-else>最近 7 天</template>
        </p>
      </div>
      <span v-if="weekly && weekly.streak > 0" class="weekly-report__streak">
        <svg viewBox="0 0 24 24" aria-hidden="true">
          <path d="M12 2.6c3.4 4.4 6.4 6.8 6.4 10.8A6.4 6.4 0 0 1 12 20a6.4 6.4 0 0 1-6.4-6.6C5.6 9.4 8.6 7 12 2.6Z" />
        </svg>
        {{ weekly.streak }} 天连击
      </span>
    </header>

    <ErrorNotice v-if="error" :error="error" retry-label="重新读取" @retry="load" />

    <template v-else-if="weekly">
      <ol class="weekly-bars" aria-label="每天获得的经验">
        <li
          v-for="(day, index) in weekly.days"
          :key="day.date"
          class="weekly-day"
          :class="{ 'is-active': day.active, 'is-today': isToday(index) }"
          :title="`${day.date}：${day.xp} XP`"
        >
          <span class="weekly-day__slot">
            <span
              class="weekly-day__candle"
              :class="{ 'is-lit': day.active }"
              :style="{ height: `${candleHeight(day.xp)}px` }"
            >
              <img
                class="weekly-day__art"
                :src="candles[themeMode]"
                alt=""
                aria-hidden="true"
              />
            </span>
          </span>
          <span class="weekly-day__lamp">{{ weekday(day.date) }}</span>
          <small class="weekly-day__xp">{{ dayNumber(day.date) }}</small>
        </li>
      </ol>

      <ul class="weekly-goals" aria-label="周目标">
        <li v-for="goal in weekly.goals" :key="goal.key" :class="{ 'is-done': goal.completed }">
          <span class="weekly-goals__check" aria-hidden="true">
            <svg viewBox="0 0 24 24"><path d="m5 12.5 4.5 4.5L19 7.5" /></svg>
          </span>
          <span class="weekly-goals__label">{{ goal.label }}</span>
          <small>{{ Math.min(goal.progress, goal.target) }} / {{ goal.target }}</small>
        </li>
      </ul>
    </template>
  </section>
</template>
