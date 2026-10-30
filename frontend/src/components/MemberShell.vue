<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { RouterLink, useRoute, useRouter } from 'vue-router'
import AppIcon from './AppIcon.vue'
import CoachView from '../views/CoachView.vue'
import CrumboMark from './CrumboMark.vue'

const props = defineProps<{
  displayName: string
  username: string
}>()

const emit = defineEmits<{ signout: [] }>()
const route = useRoute()
const router = useRouter()
const profileOpen = ref(false)
const coachOpen = ref(false)
const profileArea = ref<HTMLElement | null>(null)
const profileTrigger = ref<HTMLButtonElement | null>(null)
const coachPanel = ref<HTMLElement | null>(null)
const coachCloseButton = ref<HTMLButtonElement | null>(null)
let previousFocus: HTMLElement | null = null
let coachReturnPath = '/overview'


const primaryLinks = [
  { key: 'today', label: '今日学习', to: '/overview', icon: 'today' as const },
  { key: 'learning', label: '学习中心', to: '/challenges', icon: 'trail' as const },
  { key: 'wordbooks', label: '词书', to: '/wordbooks', icon: 'book' as const },
  { key: 'settings', label: '设置', to: '/settings', icon: 'settings' as const },
] as const

const pageTitles: Record<string, string> = {
  overview: '今日学习',
  wordbooks: '我的词书',
  memory: '记忆练习',
  'memory-mistakes': '记忆错词',
  practice: 'AI 练习',
  'practice-records': '练习记录',
  'practice-mistakes': '练习错题',
  'practice-session': 'AI 练习',
  challenges: '学习中心',
  'challenge-detail': '学习中心',
  coach: 'AI 教练',
  'settings-learning': '设置',
  'settings-ai': '设置',
  'settings-security': '设置',
}

const currentPageTitle = computed(() => pageTitles[String(route.name ?? '')] ?? '学习工作台')
const currentDate = computed(() =>
  new Intl.DateTimeFormat('zh-CN', {
    month: 'long',
    day: 'numeric',
    weekday: 'short',
  }).format(new Date()),
)
const userInitials = computed(() => props.displayName.trim().slice(0, 2).toUpperCase() || 'CT')

function isGroupActive(key: string): boolean {
  if (key === 'learning') {
    return ['/challenges', '/memory', '/practice', '/learning'].some((prefix) => route.path.startsWith(prefix))
  }
  if (key === 'settings') return route.path.startsWith('/settings')
  if (key === 'today') return route.path === '/overview'
  if (key === 'wordbooks') return route.path.startsWith('/wordbooks')
  return false
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
  // Old /coach deep links open the window over Today instead of a page.
  if (route.name === 'coach') {
    coachOpen.value = true
    void router.replace(coachReturnPath || '/overview')
  }
})

onMounted(() => {
  if (route.name === 'coach') {
    coachOpen.value = true
    void router.replace(coachReturnPath || '/overview')
  }
  document.addEventListener('click', onDocumentClick)
  document.addEventListener('keydown', onKeydown)
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
    :class="{ 'is-coach-open': coachOpen }"
  >
    <aside class="workspace-sidebar ia-sidebar" aria-label="主导航">
      <RouterLink class="workspace-brand" to="/overview" aria-label="CrumbTrail 今日学习">
        <span class="workspace-brand-mark"><CrumboMark size="small" /></span>
        <span class="workspace-brand-copy">
          <strong>CrumbTrail</strong>
          <small>英语学习路线</small>
        </span>
      </RouterLink>

      <nav class="workspace-nav ia-nav" aria-label="主导航">
        <section
          v-for="link in primaryLinks"
          :key="link.key"
          class="workspace-nav-group ia-nav-group"
          :data-nav-group="link.key"
        >
          <RouterLink
            :to="link.to"
            class="workspace-nav-link member-nav-link ia-nav-primary"
            :class="{ 'ia-nav-primary--section-active': isGroupActive(link.key) }"
          >
            <AppIcon :name="link.icon" />
            <span>{{ link.label }}</span>
          </RouterLink>
        </section>
      </nav>
    </aside>

    <div class="workspace-main">
      <header class="workspace-topbar member-topbar ia-topbar">
        <div class="workspace-topbar-heading">
          <strong>{{ currentPageTitle }}</strong>
          <span>{{ currentDate }}</span>
          <span class="sr-only">今天也学一点</span>
        </div>
        <div class="workspace-topbar-actions ia-topbar-actions">
          <button
            class="workspace-coach-button member-concierge-button ia-coach-toggle"
            type="button"
            aria-label="打开 AI 教练"
            :aria-expanded="coachOpen"
            aria-controls="global-coach-panel"
            @click="openCoach"
          >
            <AppIcon name="coach" />
            <span>AI 教练</span>
          </button>

          <div ref="profileArea" class="ia-profile-area">
            <button
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
            </button>
            <div v-if="profileOpen" id="member-profile-menu" class="ia-profile-menu" role="menu">
              <div class="ia-profile-summary">
                <span class="ia-profile-menu-label">个人资料</span>
                <strong>{{ displayName }}</strong>
                <span>@{{ username }}</span>
              </div>
              <RouterLink role="menuitem" to="/settings/learning" @click="closeProfile">学习设置</RouterLink>
              <RouterLink role="menuitem" to="/settings/security" @click="closeProfile">账户安全</RouterLink>
              <button type="button" role="menuitem" class="ia-profile-signout" @click="emit('signout')">退出登录</button>
            </div>
          </div>
        </div>
      </header>

      <main id="main-content" class="workspace-content ia-content" tabindex="-1">
        <slot />
      </main>
    </div>

    <nav class="workspace-mobile-nav member-mobile-nav ia-mobile-nav" aria-label="移动端主导航">
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
        <button
          ref="coachCloseButton"
          class="workspace-icon-button"
          type="button"
          aria-label="关闭 AI 教练"
          @click="closeCoach"
        >
          <AppIcon name="close" />
        </button>
      </header>
      <div class="ia-coach-panel-body">
        <CoachView />
      </div>
    </aside>
  </div>
</template>
