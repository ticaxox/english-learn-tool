<script setup lang="ts">
/**
 * Every badge, earned or not, so progress is visible even before it unlocks.
 *
 * Each one is a struck medal: the unearned side is a stone-grey cut-out of the
 * emblem, the earned side is enamel. When the wall scrolls into view the earned
 * medals turn over one by one, so unlocking reads as a reveal instead of a list.
 */
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from 'vue'
import ErrorNotice from './ErrorNotice.vue'
import BadgeEmblem from './BadgeEmblem.vue'
import { fetchBadges, type Badge } from '../api/progress'
import { emblemSticker } from '../assets/halloween'
import { countUp, gsap, motionAllowed, popIn } from '../composables/useMotion'

withDefaults(defineProps<{ variant?: 'seal' | 'wax' | 'iron' | 'heraldry' | 'sticker' }>(), { variant: 'iron' })

const badges = ref<Badge[]>([])
const error = ref<unknown>(null)
const loading = ref(false)
const wallRef = ref<HTMLElement | null>(null)
const countRef = ref<HTMLElement | null>(null)
const revealed = ref(false)
let observer: IntersectionObserver | null = null
let revealTimeline: gsap.core.Timeline | null = null

const unlocked = computed(() => badges.value.filter((badge) => badge.unlocked).length)
const total = computed(() => badges.value.length)

/** Emblems drawn on the same 24×24 grid, stroked like the rest of the icon set. */
const GLYPHS: Record<string, string[]> = {
  first_lesson: ['M12 3.6c1.3 4.4 2.6 5.7 7 7-4.4 1.3-5.7 2.6-7 7-1.3-4.4-2.6-5.7-7-7 4.4-1.3 5.7-2.6 7-7Z'],
  streak_3: ['M12 3c3.2 4.2 6.2 6.6 6.2 10.4A6.2 6.2 0 0 1 12 20a6.2 6.2 0 0 1-6.2-6.6C5.8 9.6 8.8 7.2 12 3Z'],
  streak_7: [
    'M12 3c3.2 4.2 6.2 6.6 6.2 10.4A6.2 6.2 0 0 1 12 20a6.2 6.2 0 0 1-6.2-6.6C5.8 9.6 8.8 7.2 12 3Z',
    'M12 12c1.5 1.9 2.7 2.9 2.7 4.4A2.7 2.7 0 0 1 12 19a2.7 2.7 0 0 1-2.7-2.6c0-1.5 1.2-2.5 2.7-4.4Z',
  ],
  streak_30: [
    'M15.3 3.6a8.7 8.7 0 1 0 5 15.6A10 10 0 0 1 15.3 3.6Z',
    'M18.6 4.4l.9 2.2 2.2.9-2.2.9-.9 2.2-.9-2.2-2.2-.9 2.2-.9.9-2.2Z',
  ],
  level_5: ['M3.8 12h4.4', 'M15.8 12h4.4', 'M12 3.8v4.4', 'M12 15.8v4.4', 'M12 7 15.4 12 12 17 8.6 12 12 7Z'],
  level_10: ['M4.4 11.4h15.2v7.8H4.4z', 'M6.2 11.4V9.2a5.8 5.8 0 0 1 11.6 0v2.2', 'M10.4 14.6h3.2'],
  practice_10: ['M19.8 4.2c-7.4.4-11.2 4-11.2 8.8L6 18.6l1.4 1.4 5.6-5.6c4.8 0 8.4-3.8 8.8-10.2Z', 'M8 16.6 15.8 8.8'],
  practice_50: ['M4.6 19.4 19.4 4.6', 'M12.8 4.6h6.6V11.2', 'M19.4 19.4 4.6 4.6', 'M11.2 4.6H4.6V11.2'],
  perfect_5: ['M12 3.6l2.6 5.4 5.9.8-4.3 4.1 1.1 5.9L12 17l-5.3 2.8 1.1-5.9L3.5 9.8l5.9-.8L12 3.6Z'],
  boss_1: ['M3.8 18.6h16.4', 'M4.6 8.4l4.2 3.4L12 5.4l3.2 6.4 4.2-3.4-1.3 8.2H5.9L4.6 8.4Z'],
  review_100: [
    'M12 7.4C10.1 5.6 7.3 4.7 4.4 4.7V18c2.9 0 5.7.9 7.6 2.7 1.9-1.8 4.7-2.7 7.6-2.7V4.7c-2.9 0-5.7.9-7.6 2.7Z',
    'M12 7.4v13.3',
  ],
  quest_all: ['M12 3.6a8.4 8.4 0 1 0 0 16.8 8.4 8.4 0 0 0 0-16.8Z', 'M8.2 12.2l2.8 2.8 4.8-5.4'],
}
GLYPHS.streak_14 = [
  'M12 3c3.2 4.2 6.2 6.6 6.2 10.4A6.2 6.2 0 0 1 12 20a6.2 6.2 0 0 1-6.2-6.6C5.8 9.6 8.8 7 12 3Z',
]
GLYPHS.streak_100 = [
  'M12 3.2 14.4 9l6.2.6-4.7 4.1 1.4 6.1L12 16.8 6.7 19.8l1.4-6.1L3.4 9.6 9.6 9 12 3.2Z',
]
GLYPHS.level_3 = ['M4 19h16', 'M6 15l3-6 3 4 3-8 3 10']
GLYPHS.level_20 = ['M12 2.6 15 9l6.4.6-4.8 4.2 1.4 6.4L12 16.8 6 20.2l1.4-6.4L2.6 9.6 9 9 3-6.4Z']
GLYPHS.practice_100 = ['M5 4h11l3 3v13H5z', 'M8 9h8', 'M8 13h8', 'M8 17h5']
GLYPHS.perfect_20 = ['M12 3.2 14.4 9l6.2.6-4.7 4.1 1.4 6.1L12 16.8 6.7 19.8l1.4-6.1L3.4 9.6 9.6 9 12 3.2Z']
GLYPHS.boss_10 = ['M3.8 18.6h16.4', 'M4.6 8.4l4.2 3.4L12 5.4l3.2 6.4 4.2-3.4-1.3 8.2H5.9L4.6 8.4Z']
GLYPHS.review_1000 = [
  'M12 7.4C10.1 5.6 7.3 4.7 4.4 4.7V18c2.9 0 5.7.9 7.6 2.7 1.9-1.8 4.7-2.7 7.6-2.7V4.7c-2.9 0-5.7.9-7.6 2.7Z',
  'M12 7.4v13.3',
]
GLYPHS.first_boss_win = ['M5 12.5 10 17l9-9.5', 'M4 20h16']
GLYPHS.night_owl = ['M12 4a8 8 0 1 0 0 16 8 8 0 0 0 0-16Z', 'M9 10h.01', 'M15 10h.01', 'M10 15q2 1.6 4 0']
GLYPHS.early_bird = ['M4 14a8 8 0 1 1 16 0', 'M12 6v4', 'M4 14h16']

const FALLBACK_GLYPH = GLYPHS.first_lesson

/** One enamel colour per feat family, so the wall reads in clusters. */
const ACCENTS: Record<string, string> = {
  streak_14: '#f07a12',
  streak_100: '#7d3cc0',
  level_3: '#3a7bf5',
  level_20: '#2b1d5e',
  practice_100: '#177a3c',
  perfect_20: '#e0a800',
  boss_10: '#a82a2a',
  review_1000: '#5b46a8',
  first_boss_win: '#d63c3c',
  night_owl: '#3b3f8f',
  early_bird: '#ffb300',
  first_lesson: '#ffc800',
  streak_3: '#ff9600',
  streak_7: '#f07a12',
  streak_30: '#a75cf0',
  level_5: '#1cb0f6',
  level_10: '#3a7bf5',
  practice_10: '#2fb344',
  practice_50: '#177a3c',
  perfect_5: '#e0a800',
  boss_1: '#d63c3c',
  review_100: '#7d3cc0',
  quest_all: '#2f8a4c',
}

function glyph(key: string): string[] {
  return GLYPHS[key] ?? FALLBACK_GLYPH
}

/** Some achievements wear an emoji-style sticker instead of a drawn glyph. */
const STICKERS: Record<string, string> = {
  first_lesson: emblemSticker.flame,
  streak_3: emblemSticker.flame,
  streak_7: emblemSticker.moon,
  streak_14: emblemSticker.moon,
  streak_30: emblemSticker.owl,
  streak_100: emblemSticker.crown,
  level_3: emblemSticker.sparkle,
  level_5: emblemSticker.sparkle,
  level_10: emblemSticker.crown,
  level_20: emblemSticker.owl,
  practice_10: emblemSticker.book,
  practice_50: emblemSticker.book,
  practice_100: emblemSticker.key,
  perfect_5: emblemSticker.star,
  perfect_20: emblemSticker.crown,
  boss_1: emblemSticker.skull,
  boss_10: emblemSticker.crown,
  first_boss_win: emblemSticker.key,
  review_100: emblemSticker.book,
  review_1000: emblemSticker.book,
  quest_all: emblemSticker.sparkle,
  night_owl: emblemSticker.owl,
  early_bird: emblemSticker.sparkle,
}

function sticker(key: string): string | null {
  return STICKERS[key] ?? null
}

function accent(key: string): string {
  return ACCENTS[key] ?? '#ffc800'
}

function earnedOn(badge: Badge): string {
  if (!badge.unlockedAt) return ''
  const parsed = new Date(badge.unlockedAt)
  if (Number.isNaN(parsed.getTime())) return ''
  return new Intl.DateTimeFormat('zh-CN', { month: 'numeric', day: 'numeric' }).format(parsed)
}

/** Flip every earned medal once, in reading order. */
function reveal(): void {
  if (revealed.value) return
  revealed.value = true
  countUp(countRef.value, unlocked.value, { duration: 1.1 })

  const turns = Array.from(wallRef.value?.querySelectorAll<HTMLElement>('.badge.is-unlocked .badge__turn') ?? [])
  if (!motionAllowed()) {
    for (const turn of turns) {
      turn.style.transform = 'rotateY(180deg)'
      turn.closest('.badge')?.classList.add('is-flipped')
    }
    return
  }

  popIn(Array.from(wallRef.value?.querySelectorAll<HTMLElement>('.badge') ?? []), {
    y: 22,
    scale: 0.9,
    stagger: 0.045,
  })

  revealTimeline?.kill()
  revealTimeline = gsap.timeline({ delay: 0.25 })
  turns.forEach((turn, index) => {
    revealTimeline?.to(turn, {
      rotationY: 180,
      duration: 0.72,
      ease: 'power3.inOut',
      onComplete: () => turn.closest('.badge')?.classList.add('is-flipped'),
    }, index * 0.09)
  })
}

let inView = false

/** Flip only once the wall exists, has data, and is actually being looked at. */
function tryReveal(): void {
  if (!inView || revealed.value || !badges.value.length) return
  observer?.disconnect()
  observer = null
  reveal()
}

function watchWall(): void {
  if (typeof IntersectionObserver === 'undefined' || !wallRef.value) {
    inView = true
    tryReveal()
    return
  }
  observer?.disconnect()
  observer = new IntersectionObserver((entries) => {
    if (!entries.some((entry) => entry.isIntersecting)) return
    inView = true
    tryReveal()
  }, { threshold: 0.2 })
  observer.observe(wallRef.value)
}

async function load(): Promise<void> {
  loading.value = true
  error.value = null
  try {
    badges.value = await fetchBadges()
    await nextTick()
    watchWall()
  } catch (loadError) {
    error.value = loadError
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  void load()
})

onBeforeUnmount(() => {
  observer?.disconnect()
  observer = null
  revealTimeline?.kill()
  revealTimeline = null
})
</script>

<template>
  <section class="badge-wall" aria-labelledby="badge-wall-title">
    <header class="badge-wall__head">
      <div>
        <h3 id="badge-wall-title">成就徽章</h3>
        <p class="field-hint">
          已解锁 <strong ref="countRef">{{ unlocked }}</strong> / {{ total }}
        </p>
      </div>
      <span class="badge-wall__rail" aria-hidden="true">
        <span :style="{ width: `${total ? (unlocked / total) * 100 : 0}%` }"></span>
      </span>
    </header>

    <ErrorNotice v-if="error" :error="error" retry-label="重新读取" @retry="load" />

    <ul v-else-if="badges.length" ref="wallRef" class="badge-grid" aria-label="徽章">
      <li
        v-for="badge in badges"
        :key="badge.key"
        class="badge"
        :class="{ 'is-locked': !badge.unlocked, 'is-unlocked': badge.unlocked }"
        :style="{ '--badge-accent': accent(badge.key) }"
      >
        <span class="badge__medal">
          <span class="badge__turn">
            <span class="badge__face badge__face--stone">
              <BadgeEmblem :glyph="glyph(badge.key)" :accent="accent(badge.key)" :earned="false" :variant="variant" :sticker="sticker(badge.key)" />
            </span>
            <span class="badge__face badge__face--enamel">
              <BadgeEmblem :glyph="glyph(badge.key)" :accent="accent(badge.key)" :earned="true" :variant="variant" :sticker="sticker(badge.key)" />
              <span class="badge__shine" aria-hidden="true"></span>
            </span>
          </span>
          <svg v-if="!badge.unlocked" class="badge__lock" viewBox="0 0 24 24" aria-hidden="true">
            <path d="M7 10.5V8a5 5 0 0 1 10 0v2.5" />
            <rect x="4.5" y="10.5" width="15" height="9.5" rx="2.4" />
          </svg>
        </span>

        <strong class="badge__name">{{ badge.name }}</strong>
        <small class="badge__desc">{{ badge.description }}</small>
        <span class="badge__foot">
          <template v-if="badge.unlocked">★ {{ earnedOn(badge) || '已解锁' }}</template>
          <template v-else>待解锁</template>
        </span>
      </li>
    </ul>
    <p v-else-if="!loading" class="field-hint">还没有可展示的徽章。</p>
  </section>
</template>
