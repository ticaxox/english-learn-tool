<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { RouterLink, useRoute } from 'vue-router'
import AppIcon from './AppIcon.vue'
import ThemeSwitch from './ThemeSwitch.vue'
import CoachView from '../views/CoachView.vue'
import CrumboMark from './CrumboMark.vue'
import { getActivePinia } from 'pinia'
import { useAuthStore } from '../stores/auth'
import { useGamification } from '../composables/useGamification'

const props = defineProps<{
  displayName: string
  username: string
}>()

const emit = defineEmits<{ signout: [] }>()

const route = useRoute()
// Tests mount the shell without a Pinia; the admin link is simply absent there.
const auth = getActivePinia() ? useAuthStore() : null
const profileOpen = ref(false)
const coachOpen = ref(false)
const profileArea = ref<HTMLElement | null>(null)
const profileTrigger = ref<HTMLButtonElement | null>(null)
const coachPanel = ref<HTMLElement | null>(null)
const coachCloseButton = ref<HTMLButtonElement | null>(null)
let previousFocus: HTMLElement | null = null


const primaryLinks = [
  { key: 'today', label: '今日学习', to: '/overview', icon: 'today' as const },
  { key: 'practice', label: '练习', to: '/practice', icon: 'book' as const },
  { key: 'coach', label: 'AI 教练', to: '/coach', icon: 'coach' as const },
  { key: 'settings', label: '设置', to: '/settings', icon: 'settings' as const },
] as const

const pageTitles: Record<string, string> = {
  overview: '今日学习',
  memory: '练习',
  'memory-mistakes': '记忆错词',
  practice: '练习',
  'practice-records': '题目集',
  'practice-mistakes': '错题本',
  'practice-record': '练习记录',
  'practice-session': '练习',
  challenges: '学习地图',
  'challenge-detail': '学习地图',
  coach: 'AI 教练',
  'settings-learning': '设置',
  'settings-ai': '设置',
  'settings-security': '设置',
  'settings-knowledge': '设置',
}

// The rail is the player's status panel: the same numbers the HUD used to
// repeat at the top of every page, kept in one place the page cannot scroll away.
const gamification = useGamification()
const progress = gamification.progress
const level = computed(() => progress.value?.level ?? null)
const xpIntoLevel = computed(() => level.value?.xpIntoLevel ?? 0)
const xpForNextLevel = computed(() => level.value?.xpForNextLevel ?? 0)
/** Ten segments, so the plate reads as a tally rather than a smooth bar. */
const xpSegments = computed(() => {
  if (!level.value || xpForNextLevel.value <= 0) return 0
  return Math.round((xpIntoLevel.value / xpForNextLevel.value) * 10)
})

const currentPageTitle = computed(() => pageTitles[String(route.name ?? '')] ?? '学习工作台')
// Practice and memory are their own screens: no app sidebar or top bar there.
const immersive = computed(() => Boolean(route.meta.immersive))
const currentDate = computed(() =>
  new Intl.DateTimeFormat('zh-CN', {
    month: 'long',
    day: 'numeric',
    weekday: 'short',
  }).format(new Date()),
)
const userInitials = computed(() => props.displayName.trim().slice(0, 2).toUpperCase() || 'CT')

function isGroupActive(key: string): boolean {
  if (key === 'practice') return route.path.startsWith('/practice') || route.path.startsWith('/memory')
  if (key === 'coach') return route.path.startsWith('/coach')
  if (key === 'settings') return route.path.startsWith('/settings')
  if (key === 'today') return route.path === '/overview' || route.path.startsWith('/challenges')
  return false
}

/** Secondary navigation lives in the top bar: one set of tabs per section. */
const sectionTabs = computed(() => {
  const path = route.path
  if (path.startsWith('/settings')) {
    const tabs = [
      { label: '词书', to: '/settings/wordbooks', active: path.startsWith('/settings/wordbooks') },
      { label: '学习设置', to: '/settings/learning', active: path.startsWith('/settings/learning') },
      { label: 'AI 配置', to: '/settings/ai', active: path.startsWith('/settings/ai') },
      { label: '我的账户', to: '/settings/security', active: path.startsWith('/settings/security') },
    ]
    // The knowledge base is the exam corpus every learner's questions come
    // from, so only an administrator may change it.
    if (auth?.isAdmin) {
      tabs.push({
        label: '知识库',
        to: '/settings/knowledge',
        active: path.startsWith('/settings/knowledge'),
      })
    }
    return tabs
  }
  return []
})

const sidebarCollapsed = ref(false)

function toggleSidebar(): void {
  sidebarCollapsed.value = !sidebarCollapsed.value
}

function closeProfile(): void {
  profileOpen.value = false
}

function toggleProfile(): void {
  profileOpen.value = !profileOpen.value
}

async function openCoach(): Promise<void> {
  // The coach is a floating window, never a page: opening it leaves the URL be.
  closeProfile()
  previousFocus = document.activeElement instanceof HTMLElement ? document.activeElement : null
  coachOpen.value = true
}

function closeCoach(): void {
  coachOpen.value = false
}

function focusableElements(): HTMLElement[] {
  if (!coachPanel.value) return []
  return Array.from(coachPanel.value.querySelectorAll<HTMLElement>(
    'a[href], button:not([disabled]), textarea:not([disabled]), input:not([disabled]), select:not([disabled]), [tabindex]:not([tabindex="-1"])',
  )).filter((element) => !element.hidden && element.offsetParent !== null)
}

function trapCoachFocus(event: KeyboardEvent): void {
  const elements = focusableElements()
  if (elements.length === 0) return
  const first = elements[0]
  const last = elements[elements.length - 1]
  if (event.shiftKey && document.activeElement === first) {
    event.preventDefault()
    last.focus()
  } else if (!event.shiftKey && document.activeElement === last) {
    event.preventDefault()
    first.focus()
  }
}

function onDocumentClick(event: MouseEvent): void {
  if (!profileOpen.value || !profileArea.value) return
  if (event.target instanceof Node && !profileArea.value.contains(event.target)) closeProfile()
}

function onKeydown(event: KeyboardEvent): void {
  if (event.key === 'Escape') {
    if (profileOpen.value) {
      closeProfile()
      profileTrigger.value?.focus()
      return
    }
    if (coachOpen.value) {
      closeCoach()
      return
    }
  }

  if (event.key === 'Tab' && coachOpen.value) trapCoachFocus(event)
}

watch(coachOpen, async (open) => {
  if (open) {
    await nextTick()
    coachCloseButton.value?.focus()
  } else if (previousFocus) {
    await nextTick()
    previousFocus?.focus()
    previousFocus = null
  }
})

watch(() => route.fullPath, () => {
  closeProfile()
})

onMounted(() => {
  document.addEventListener('click', onDocumentClick)
  document.addEventListener('keydown', onKeydown)
  // One load for the whole app: the composable keeps a module-level copy, so
  // the first page that mounts the shell fills the plate for every other page.
  if (!progress.value) void gamification.load()
})

onBeforeUnmount(() => {
  document.removeEventListener('click', onDocumentClick)
  document.removeEventListener('keydown', onKeydown)
})
</script>

<template>
  <a class="skip-link" href="#main-content">跳到主要内容</a>

  <div
    class="app-shell app-shell--member workspace-shell ia-workspace personal-workspace"
    :class="{ 'is-coach-open': coachOpen, 'is-immersive': immersive, 'is-sidebar-collapsed': sidebarCollapsed }"
  >
    <aside v-if="!immersive" class="workspace-sidebar ia-sidebar" aria-label="主导航">
      <RouterLink class="workspace-brand" to="/overview" aria-label="CrumbTrail 今日学习">
        <span class="workspace-brand-mark"><CrumboMark size="small" /></span>
        <span class="workspace-brand-copy">
          <strong>CrumbTrail</strong>
          <small>英语学习路线</small>
        </span>
      </RouterLink>

      <section class="rail-plate" aria-label="等级进度">
        <p class="rail-plate__lv">
          <strong>LV {{ level?.level ?? 1 }}</strong>
          <span>{{ level?.title ?? '拾屑人' }}</span>
        </p>
        <div class="rail-plate__xp" aria-hidden="true">
          <i v-for="segment in 10" :key="segment" :class="{ 'is-on': segment <= xpSegments }"></i>
        </div>
        <p class="rail-plate__num">{{ xpIntoLevel }} / {{ xpForNextLevel }} XP</p>
      </section>

      <nav class="workspace-nav ia-nav" aria-label="主导航">
        <p class="rail-kicker">菜单</p>
        <section
          v-for="link in primaryLinks"
          :key="link.key"
          class="workspace-nav-group ia-nav-group"
          :data-nav-group="link.key"
        >
          <RouterLink
            :to="link.to"
            class="workspace-nav-link member-nav-link ia-nav-primary"
            :aria-label="link.label"
            :class="{ 'ia-nav-primary--section-active': isGroupActive(link.key) }"
          >
            <AppIcon :name="link.icon" />
            <span>{{ link.label }}</span>
          </RouterLink>
        </section>
      </nav>

      <div class="workspace-sidebar-footer">
        <div class="rail-daylight">
          <ThemeSwitch />
        </div>

        <DivButton
          class="rail-handle"
          type="button"
          :aria-label="sidebarCollapsed ? '展开导航栏' : '折叠导航栏'"
          :aria-expanded="!sidebarCollapsed"
          @click="toggleSidebar"
        >
          <svg class="rail-handle__chevron" viewBox="0 0 24 24" aria-hidden="true">
            <path
              d="M14.5 5.5 8 12l6.5 6.5"
              fill="none"
              stroke="currentColor"
              stroke-width="2.6"
              stroke-linecap="round"
              stroke-linejoin="round"
            />
          </svg>
        </DivButton>
      </div>
    </aside>

    <div class="workspace-main">
      <header v-if="!immersive" class="workspace-topbar member-topbar ia-topbar">
        <span class="sr-only">今天也学一点</span>
        <div class="workspace-topbar-heading">
          <strong>{{ currentPageTitle }}</strong>
          <span>{{ currentDate }}</span>
        </div>
        <nav v-if="sectionTabs.length" class="workspace-topbar-tabs" aria-label="二级导航">
          <RouterLink
            v-for="tab in sectionTabs"
            :key="tab.to"
            :to="tab.to"
            class="workspace-topbar-tab"
            :class="{ 'is-active': tab.active }"
            :aria-current="tab.active ? 'page' : undefined"
          >
            {{ tab.label }}
          </RouterLink>
        </nav>
        <div class="workspace-topbar-actions ia-topbar-actions">
          <DivButton
            class="workspace-coach-button member-concierge-button ia-coach-toggle"
            type="button"
            aria-label="打开 AI 教练"
            :aria-expanded="coachOpen"
            aria-controls="global-coach-panel"
            @click="openCoach"
          >
            <AppIcon name="coach" />
            <span>AI 教练</span>
          </DivButton>

          <div ref="profileArea" class="ia-profile-area">
            <DivButton
              ref="profileTrigger"
              class="workspace-avatar-button ia-profile-trigger"
              type="button"
              :aria-label="`${displayName} 的账户菜单`"
              :aria-expanded="profileOpen"
              aria-haspopup="menu"
              aria-controls="member-profile-menu"
              @click="toggleProfile"
            >
              {{ userInitials }}
            </DivButton>
            <div v-if="profileOpen" id="member-profile-menu" class="ia-profile-menu" role="menu">
              <div class="ia-profile-summary">
                <span class="ia-profile-menu-label">个人资料</span>
                <strong>{{ displayName }}</strong>
                <span>@{{ username }}</span>
              </div>
              <RouterLink
                v-if="auth?.isAdmin"
                role="menuitem"
                to="/admin/users"
                @click="closeProfile"
              >
                管理后台
              </RouterLink>
              <RouterLink role="menuitem" to="/settings/learning" @click="closeProfile">学习设置</RouterLink>
              <RouterLink role="menuitem" to="/settings/security" @click="closeProfile">账户安全</RouterLink>
              <DivButton type="button" role="menuitem" class="ia-profile-signout" @click="emit('signout')">退出登录</DivButton>
            </div>
          </div>
        </div>
      </header>

      <main id="main-content" class="workspace-content ia-content" tabindex="-1">
        <slot />
      </main>
    </div>

    <nav v-if="!immersive" class="workspace-mobile-nav member-mobile-nav ia-mobile-nav" aria-label="移动端主导航">
      <RouterLink v-for="link in primaryLinks" :key="link.key" :to="link.to">
        <AppIcon :name="link.icon" />
        <span>{{ link.label }}</span>
      </RouterLink>
    </nav>

    <div v-if="coachOpen" class="ia-coach-backdrop" @click="closeCoach"></div>
    <aside
      v-if="coachOpen"
      id="global-coach-panel"
      ref="coachPanel"
      class="ia-coach-panel"
      role="dialog"
      aria-modal="true"
      aria-labelledby="global-coach-title"
      @click.stop
    >
      <header class="ia-coach-panel-header">
        <div>
          <p>AI 教练</p>
          <h2 id="global-coach-title">随时问一句</h2>
        </div>
        <DivButton
          ref="coachCloseButton"
          class="workspace-icon-button"
          type="button"
          aria-label="关闭 AI 教练"
          @click="closeCoach"
        >
          <AppIcon name="close" />
        </DivButton>
      </header>
      <div class="ia-coach-panel-body">
        <CoachView />
      </div>
    </aside>
  </div>
</template>
