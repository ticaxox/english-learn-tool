<script setup lang="ts">
/**
 * The two cards under the learning map.
 *
 * Left: the month as a grid of days — a filled cell is a day that was studied,
 * a gold ring is today — with this week's candles and the weekly goals under it.
 * Right: one radar of the words being learned against the wordbook's own total,
 * beside a slim vertical bar that splits every word by where it sits in the
 * memory curve.
 *
 * Both read from the same two endpoints the page already trusts; nothing here
 * is computed on the client beyond pixels.
 */
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from 'vue'
import ErrorNotice from './ErrorNotice.vue'
import WordKindRadar from './WordKindRadar.vue'
import {
  fetchFootprint,
  fetchWeekly,
  type GamificationFootprint,
  type GamificationWeekly,
} from '../api/progress'
import { gsap, motionAllowed } from '../composables/useMotion'
import { candleStates, type CandleState } from '../assets/halloween'
import { themeMode } from '../composables/useTheme'

const weekly = ref<GamificationWeekly | null>(null)
const footprint = ref<GamificationFootprint | null>(null)
const error = ref<unknown>(null)
const rootRef = ref<HTMLElement | null>(null)

const WEEKDAYS = ['一', '二', '三', '四', '五', '六', '日']
/** A mastered word left the schedule on purpose; it still counts as in review. */
const STATE_KEYS = [
  { key: 'new', label: '新词', color: '#e8c58a' },
  { key: 'learning', label: '学习中', color: '#1cb0f6' },
  { key: 'review', label: '复习中', color: '#ff9600' },
  { key: 'relearning', label: '重学', color: '#a75cf0' },
] as const

const peakXp = computed(() => Math.max(1, ...(weekly.value?.days ?? []).map((day) => day.xp)))

/** The burn state picks its own drawing, and with it its own height. */
function candleState(xp: number): CandleState {
  if (xp <= 0) return 'cold'
  const ratio = xp / peakXp.value
  if (ratio <= 1 / 3) return 'low'
  if (ratio <= 2 / 3) return 'mid'
  return 'high'
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

/** The last day of the weekly window is today. */
const todayIso = computed(() => weekly.value?.days.at(-1)?.date ?? '')

/** Monday-first: how many blank cells the month starts with. */
const monthLead = computed(() => {
  const first = footprint.value?.days[0]?.date
  if (!first) return 0
  const parsed = new Date(`${first}T00:00:00`)
  return Number.isNaN(parsed.getTime()) ? 0 : (parsed.getDay() + 6) % 7
})

const monthLabel = computed(() => {
  const month = footprint.value?.month
  if (!month) return ''
  const [year, index] = month.split('-')
  return `${Number(year)} 年 ${Number(index)} 月`
})

function dayClass(date: string, active: boolean): Record<string, boolean> {
  if (active) return { 'is-lit': true }
  if (date === todayIso.value) return { 'is-today': true }
  return { 'is-past': date < todayIso.value }
}

/** The bar, bottom-up: new words sit on the floor, relearning on the top. */
const stateSegments = computed(() => {
  const states = footprint.value?.states
  if (!states || states.total <= 0) return []
  return STATE_KEYS.map((meta) => ({
    ...meta,
    count: states[meta.key],
    percent: (states[meta.key] / states.total) * 100,
  }))
})

/** Each label rides at the centre of its own slice, measured from the top. */
const stateLabels = computed(() => {
  let passed = 0
  return stateSegments.value.map((segment) => {
    const centre = passed + segment.percent / 2
    passed += segment.percent
    return { ...segment, top: 100 - centre }
  })
})

function tipText(label: string, count: number, percent: number): string {
  return `${label} · ${count} 个 · ${Math.round(percent)}%`
}

async function load(): Promise<void> {
  error.value = null
  try {
    const [week, month] = await Promise.all([fetchWeekly(), fetchFootprint()])
    weekly.value = week
    footprint.value = month
    await nextTick()
    play()
  } catch (loadError) {
    error.value = loadError
  }
}

let inView = false
let played = false
let observer: IntersectionObserver | null = null

function play(): void {
  if (played || !inView || !rootRef.value) return
  played = true
  observer?.disconnect()
  observer = null
  if (!motionAllowed()) return

  const root = rootRef.value
  const timeline = gsap.timeline({ delay: 0.08 })
  const cells = Array.from(root.querySelectorAll('.trail-month__day'))
  const lit = cells.filter((cell) => cell.classList.contains('is-lit'))
  timeline.fromTo(cells, { opacity: 0, y: 6 }, { opacity: 1, y: 0, duration: 0.28, stagger: 0.008 })
  if (lit.length) {
    timeline.fromTo(
      lit,
      { scale: 0.7 },
      { scale: 1, duration: 0.34, ease: 'back.out(2)', stagger: 0.05 },
      '-=0.2',
    )
  }
  const candleEls = Array.from(root.querySelectorAll<HTMLElement>('.weekly-day__candle'))
  if (candleEls.length) {
    timeline.fromTo(
      candleEls,
      { scaleY: 0.05, opacity: 0.4 },
      { scaleY: 1, opacity: 1, duration: 0.55, ease: 'back.out(1.5)', stagger: 0.07 },
      '-=0.25',
    )
  }
  const shape = root.querySelector<SVGPolygonElement>('.word-radar__studied')
  if (shape) {
    timeline.fromTo(
      shape,
      { scale: 0.02, opacity: 0, transformOrigin: '50% 50%' },
      { scale: 1, opacity: 1, duration: 0.75, ease: 'power3.out' },
      '-=0.4',
    )
  }
  const bar = Array.from(root.querySelectorAll<HTMLElement>('.state-scale__seg'))
  if (bar.length) {
    timeline.fromTo(
      bar,
      { scaleY: 0, transformOrigin: '50% 100%' },
      { scaleY: 1, duration: 0.5, ease: 'power2.out', stagger: 0.06 },
      '-=0.5',
    )
  }
}

onMounted(() => {
  void load()
  if (typeof IntersectionObserver === 'undefined' || !rootRef.value) {
    inView = true
    play()
    return
  }
  observer = new IntersectionObserver((entries) => {
    if (!entries.some((entry) => entry.isIntersecting)) return
    inView = true
    play()
  }, { threshold: 0.15 })
  observer.observe(rootRef.value)
})

onBeforeUnmount(() => {
  observer?.disconnect()
  observer = null
})
</script>

<template>
  <section ref="rootRef" class="today-insights" aria-label="学习足迹与词的状态">
    <ErrorNotice v-if="error" :error="error" retry-label="重新读取" @retry="load" />

    <template v-else>
      <article class="insight-card insight-card--trail">
        <header class="insight-card__head">
          <span class="insight-card__eyebrow">学习足迹</span>
        </header>

        <div class="insight-split">
          <div class="insight-col">
            <div class="trail-week">
              <ol v-if="weekly" class="weekly-bars" aria-label="每天获得的经验">
                <li
                  v-for="(day, index) in weekly.days"
                  :key="day.date"
                  class="weekly-day"
                  :class="{ 'is-active': day.active, 'is-today': index === weekly.days.length - 1 }"
                  :title="`${day.date}：${day.xp} XP`"
                >
                  <span class="weekly-day__slot">
                    <span
                      class="weekly-day__candle"
                      :class="{ 'is-lit': day.active }"
                      :data-state="candleState(day.xp)"
                    >
                      <img
                        class="weekly-day__art"
                        :src="candleStates[themeMode][candleState(day.xp)]"
                        alt=""
                        aria-hidden="true"
                      />
                    </span>
                  </span>
                  <span class="weekly-day__lamp">{{ weekday(day.date) }}</span>
                  <small class="weekly-day__xp">{{ dayNumber(day.date) }}</small>
                </li>
              </ol>
            </div>

            <ul v-if="weekly?.goals.length" class="weekly-goals" aria-label="周目标">
              <li v-for="goal in weekly.goals" :key="goal.key" :class="{ 'is-done': goal.completed }">
                <span class="weekly-goals__check" aria-hidden="true">
                  <svg viewBox="0 0 24 24"><path d="m5 12.5 4.5 4.5L19 7.5" /></svg>
                </span>
                <span class="weekly-goals__label">{{ goal.label }}</span>
                <small>{{ Math.min(goal.progress, goal.target) }} / {{ goal.target }}</small>
              </li>
            </ul>
          </div>

          <div class="insight-col">
            <div
              v-if="footprint"
              class="trail-month"
              role="list"
              :aria-label="`${monthLabel}的学习足迹：${footprint.activeDays} 天有记录`"
            >
              <span v-for="name in WEEKDAYS" :key="name" class="trail-month__dow" aria-hidden="true">
                {{ name }}
              </span>
              <span v-for="gap in monthLead" :key="`gap-${gap}`" class="trail-month__gap" aria-hidden="true"></span>
              <span
                v-for="day in footprint.days"
                :key="day.date"
                class="trail-month__day"
                :class="dayClass(day.date, day.active)"
                role="listitem"
                :aria-label="`${day.date}${day.active ? ' 学过' : ''}`"
              >
                {{ dayNumber(day.date) }}
              </span>
            </div>
          </div>
        </div>
      </article>

      <article class="insight-card insight-card--state">
        <div class="state-body">
          <WordKindRadar v-if="weekly?.radar.length" class="state-radar" :axes="weekly.radar" />

          <div v-if="stateSegments.length" class="state-scale">
            <div class="state-scale__track">
              <span
                v-for="segment in stateSegments"
                :key="segment.key"
                class="state-scale__seg"
                :style="{ height: `${segment.percent}%`, background: segment.color }"
                :data-tip="tipText(segment.label, segment.count, segment.percent)"
              ></span>
            </div>
            <div class="state-scale__labels" aria-hidden="true">
              <b v-for="segment in stateLabels" :key="segment.key" :style="{ top: `${segment.top}%` }">
                {{ segment.label }}
              </b>
            </div>
            <span class="sr-only">
              <template v-for="segment in stateSegments" :key="segment.key">
                {{ tipText(segment.label, segment.count, segment.percent) }}；
              </template>
            </span>
          </div>
        </div>
      </article>
    </template>
  </section>
</template>
