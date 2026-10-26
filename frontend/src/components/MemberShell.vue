<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { RouterLink, useRoute } from 'vue-router'
import AppIcon from './AppIcon.vue'
import WhiskerCrumbMark from './WhiskerCrumbMark.vue'

const props = defineProps<{
  displayName: string
  username: string
}>()

const emit = defineEmits<{ signout: [] }>()
const route = useRoute()
const drawerOpen = ref(false)

const primaryLinks = [
  { label: '今日学习', to: '/overview', icon: 'today' as const },
  { label: '词书', to: '/wordbooks', icon: 'book' as const },
  { label: '记忆', to: '/memory', icon: 'spark' as const },
  { label: 'AI 练习', to: '/practice', icon: 'cards' as const },
  { label: '每日闯关', to: '/challenges', icon: 'trail' as const },
  { label: '学习管家', to: '/coach', icon: 'coach' as const },
]
const secondaryLinks = [
  { label: '通知', to: '/notifications', icon: 'bell' as const },
  { label: '设置', to: '/settings', icon: 'settings' as const },
]

const pageTitles: Record<string, string> = {
  overview: '今日学习',
  wordbooks: '我的词书',
  memory: '记忆训练',
  'memory-mistakes': '记忆错词',
  practice: 'AI 练习',
  'practice-records': '练习记录',
  'practice-mistakes': '练习错题',
  'practice-session': 'AI 练习',
  challenges: '每日闯关',
  'challenge-detail': '每日闯关',
  coach: '学习管家',
  notifications: '通知中心',
  'notification-preferences': '通知设置',
  settings: '学习设置',
}

const currentPageTitle = computed(() => pageTitles[String(route.name ?? '')] ?? '学习工作台')
const currentDate = computed(() =>
  new Intl.DateTimeFormat('zh-CN', {
    month: 'long',
    day: 'numeric',
    weekday: 'short',
  }).format(new Date()),
)

function closeDrawer(): void {
  drawerOpen.value = false
}

function onKeydown(event: KeyboardEvent): void {
  if (event.key === 'Escape') closeDrawer()
}

watch(() => route.fullPath, closeDrawer)
onMounted(() => document.addEventListener('keydown', onKeydown))
onBeforeUnmount(() => document.removeEventListener('keydown', onKeydown))
</script>

<template>
  <a class="skip-link" href="#main-content">跳到主要内容</a>

  <div class="app-shell app-shell--member workspace-shell">
    <aside class="workspace-sidebar" aria-label="成员端主导航">
      <RouterLink class="workspace-brand" to="/overview" aria-label="Whisker 今日学习">
        <span class="workspace-brand-mark"><WhiskerCrumbMark size="small" /></span>
        <span class="workspace-brand-copy">
          <strong>Whisker</strong>
          <small>英语学习</small>
        </span>
      </RouterLink>

      <nav class="workspace-nav" aria-label="学习导航">
        <div class="workspace-nav-group">
          <p class="workspace-nav-label">学习</p>
          <RouterLink
            v-for="link in primaryLinks"
            :key="link.to"
            class="workspace-nav-link member-nav-link"
            :to="link.to"
          >
            <AppIcon :name="link.icon" />
            <span>{{ link.label }}</span>
          </RouterLink>
        </div>

        <div class="workspace-nav-group workspace-nav-group--utility">
          <RouterLink
            v-for="link in secondaryLinks"
            :key="link.to"
            class="workspace-nav-link member-nav-link"
            :to="link.to"
          >
            <AppIcon :name="link.icon" />
            <span>{{ link.label }}</span>
          </RouterLink>
        </div>
      </nav>

      <div class="workspace-sidebar-footer">
        <button class="workspace-concierge-link member-concierge-link" type="button" @click="drawerOpen = true">
          <AppIcon name="coach" />
          <span>问问管家</span>
        </button>
        <RouterLink class="workspace-profile" to="/settings" :aria-label="displayName + ' 的设置'">
          <span class="workspace-avatar">{{ displayName.slice(0, 2).toUpperCase() }}</span>
          <span class="workspace-profile-copy">
            <strong>{{ displayName }}</strong>
            <small>@{{ username }}</small>
          </span>
        </RouterLink>
        <button class="workspace-signout" type="button" @click="emit('signout')">退出登录</button>
      </div>
    </aside>

    <div class="workspace-main">
      <header class="workspace-topbar member-topbar">
        <div class="workspace-topbar-heading">
          <strong>{{ currentPageTitle }}</strong>
          <span>{{ currentDate }}</span>
          <span class="sr-only">今天也学一点</span>
        </div>
        <div class="workspace-topbar-actions">
          <RouterLink class="workspace-icon-button member-notices-link" to="/notifications" aria-label="通知">
            <AppIcon name="bell" />
          </RouterLink>
          <button class="workspace-coach-button member-concierge-button" type="button" @click="drawerOpen = true">
            <AppIcon name="coach" />
            <span>学习管家</span>
          </button>
          <RouterLink class="workspace-avatar-button" to="/settings" :aria-label="displayName + ' 的设置'">
            {{ displayName.slice(0, 2).toUpperCase() }}
          </RouterLink>
        </div>
      </header>

      <main id="main-content" class="workspace-content" tabindex="-1">
        <slot />
      </main>
    </div>

    <nav class="workspace-mobile-nav member-mobile-nav" aria-label="成员端移动导航">
      <RouterLink v-for="link in primaryLinks" :key="link.to" :to="link.to">
        <AppIcon :name="link.icon" />
        <span>{{ link.label }}</span>
      </RouterLink>
    </nav>

    <div v-if="drawerOpen" class="workspace-drawer-backdrop" @click="closeDrawer"></div>
    <aside v-if="drawerOpen" class="workspace-drawer member-concierge-drawer" aria-labelledby="workspace-drawer-title">
      <div class="workspace-drawer-heading">
        <div>
          <p class="workspace-kicker">学习管家</p>
          <h2 id="workspace-drawer-title">需要时，先问一句</h2>
        </div>
        <button class="workspace-icon-button" type="button" aria-label="关闭学习管家" @click="closeDrawer">
          <AppIcon name="close" />
        </button>
      </div>
      <p>可以聊学习计划、复习顺序，也可以改一句英文。</p>
      <div class="workspace-drawer-actions member-drawer-actions">
        <RouterLink class="button workspace-primary-button" to="/coach">进入对话 <AppIcon name="arrow" /></RouterLink>
        <RouterLink class="button workspace-secondary-button" to="/overview">回到今日学习</RouterLink>
      </div>
      <p class="workspace-drawer-note">对话仅你可见。</p>
    </aside>
  </div>
</template>