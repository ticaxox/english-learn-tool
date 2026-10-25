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

  <div class="app-shell app-shell--member">
    <aside class="member-rail" aria-label="成员端主导航">
      <RouterLink class="member-brand" to="/overview" aria-label="Whisker Crumb 今日学习">
        <span class="member-brand-mark"><WhiskerCrumbMark size="small" /></span>
        <span class="member-brand-copy">
          <strong>WHISKER</strong>
          <em>AI 英语学习</em>
        </span>
      </RouterLink>

      <nav class="member-nav-groups">
        <div class="member-nav-group">
          <p class="member-nav-label">学习</p>
          <RouterLink v-for="link in primaryLinks" :key="link.to" class="member-nav-link" :to="link.to">
            <AppIcon :name="link.icon" />
            <span>{{ link.label }}</span>
            <i aria-hidden="true"></i>
          </RouterLink>
        </div>
        <div class="member-nav-group member-nav-group--quiet">
          <p class="member-nav-label">更多</p>
          <RouterLink v-for="link in secondaryLinks" :key="link.to" class="member-nav-link" :to="link.to">
            <AppIcon :name="link.icon" />
            <span>{{ link.label }}</span>
          </RouterLink>
        </div>
      </nav>

      <div class="member-rail-footer">
        <div class="member-profile">
          <span class="member-avatar">{{ props.displayName.slice(0, 2).toUpperCase() }}</span>
          <span><strong>{{ props.displayName }}</strong><small>@{{ props.username }}</small></span>
        </div>
        <button class="member-concierge-link" type="button" @click="drawerOpen = true">
          问问管家 <span>↗</span>
        </button>
        <button class="member-signout" type="button" @click="emit('signout')">退出登录</button>
      </div>
    </aside>

    <div class="member-main-area">
      <header class="member-topbar">
        <RouterLink class="member-mobile-brand" to="/overview">
          <span class="member-brand-mark"><WhiskerCrumbMark size="small" /></span>
          <strong>WHISKER</strong>
        </RouterLink>
        <div class="member-topbar-center">
          <span class="member-live-dot" aria-hidden="true"></span>
          <span>{{ currentDate }}</span>
          <span class="member-topbar-divider" aria-hidden="true"></span>
          <span>今天也学一点</span>
        </div>
        <div class="member-topbar-actions">
          <RouterLink class="member-icon-link member-notices-link" to="/notifications" aria-label="通知">
            <AppIcon name="bell" />
          </RouterLink>
          <button class="member-concierge-button" type="button" @click="drawerOpen = true">
            <WhiskerCrumbMark size="small" />
            <span>问问管家</span>
          </button>
          <RouterLink class="member-avatar-button" to="/settings" :aria-label="props.displayName + ' 的偏好设置'">
            {{ props.displayName.slice(0, 2).toUpperCase() }}
          </RouterLink>
        </div>
      </header>

      <main id="main-content" class="page-content member-page-content" tabindex="-1">
        <slot />
      </main>
    </div>

    <nav class="member-mobile-nav" aria-label="成员端移动导航">
      <RouterLink v-for="link in primaryLinks" :key="link.to" :to="link.to">
        <AppIcon :name="link.icon" />
        <span>{{ link.label }}</span>
      </RouterLink>
    </nav>

    <div v-if="drawerOpen" class="member-drawer-backdrop" @click="closeDrawer"></div>
    <aside v-if="drawerOpen" class="member-concierge-drawer" aria-labelledby="member-drawer-title">
      <div class="member-drawer-top">
        <div><p class="eyebrow">学习管家</p><h2 id="member-drawer-title">问问 Mr. Whisker</h2></div>
        <button class="member-drawer-close" type="button" aria-label="关闭学习管家" @click="closeDrawer">
          <AppIcon name="close" />
        </button>
      </div>
      <div class="member-drawer-mascot"><WhiskerCrumbMark size="hero" /></div>
      <p class="member-drawer-copy">
        “有问题，或有一句话想说，都可以先交给我。”
      </p>
      <div class="member-drawer-actions">
        <RouterLink class="button" to="/coach">进入对话 <AppIcon name="arrow" /></RouterLink>
        <RouterLink class="button-secondary" to="/overview">回到今日学习</RouterLink>
        <RouterLink class="button-secondary" to="/wordbooks">浏览词书</RouterLink>
      </div>
      <p class="member-drawer-note">
        对话仅你可见。
      </p>
    </aside>
  </div>
</template>
