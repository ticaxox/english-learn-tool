<script setup lang="ts">
import { computed } from 'vue'
import { useRoute, useRouter, RouterLink, RouterView } from 'vue-router'
import { useAuthStore } from '../stores/auth'

const auth = useAuthStore()
const route = useRoute()
const router = useRouter()

const memberLinks = [
  { label: '学习概览', to: '/overview' },
  { label: '词书', to: '/wordbooks' },
  { label: '记忆练习', to: '/memory' },
  { label: 'AI 练习', to: '/practice' },
  { label: '每日闯关', to: '/challenges' },
  { label: 'AI 教练', to: '/coach' },
  { label: '通知', to: '/notifications' },
  { label: '学习设置', to: '/settings' },
]

const adminLinks = [
  { label: '组织看板', to: '/admin/dashboard' },
  { label: '成员管理', to: '/admin/users' },
  { label: 'AI 提供商', to: '/admin/ai/providers' },
  { label: 'AI 提示词', to: '/admin/ai/prompts' },
]

const accessDenied = computed(() => route.query.access === 'denied')
const roleLabel = computed(() => (auth.user?.role === 'admin' ? '组织管理员' : '成员'))

async function signOut(): Promise<void> {
  try {
    await auth.logout()
  } catch {
    // The store keeps the server error for the login screen while clearing in-memory credentials.
  }
  await router.replace({ name: 'login' })
}
</script>

<template>
  <a class="skip-link" href="#main-content">跳到主要内容</a>

  <div class="app-shell">
    <aside class="sidebar">
      <div class="brand-row">
        <span class="brand-mark" aria-hidden="true">EN</span>
        <div class="brand-copy">
          <strong>AI 英语学习平台</strong>
          <span>组织内部学习空间</span>
        </div>
      </div>

      <nav aria-label="主要导航">
        <div class="nav-group">
          <p class="nav-label">学习</p>
          <ul class="nav-list">
            <li v-for="link in memberLinks" :key="link.to">
              <RouterLink :to="link.to">{{ link.label }}</RouterLink>
            </li>
          </ul>
        </div>

        <div v-if="auth.isAdmin" class="nav-group">
          <p class="nav-label">组织管理</p>
          <ul class="nav-list">
            <li v-for="link in adminLinks" :key="link.to">
              <RouterLink :to="link.to">{{ link.label }}</RouterLink>
            </li>
          </ul>
        </div>
      </nav>

      <div class="sidebar-footer">
        <div class="user-summary">
          <strong>{{ auth.displayName }}</strong>
          <span>{{ auth.user?.username }} · {{ roleLabel }}</span>
        </div>
        <button class="button-secondary" type="button" @click="signOut">退出登录</button>
      </div>
    </aside>

    <div class="main-area">
      <header class="topbar">
        <p>以下页面只展示真实 API 响应或明确错误，不使用模拟业务数据。</p>
        <div class="topbar-actions">
          <span class="inline-note">真实账号与成员管理 · M2</span>
        </div>
      </header>

      <main id="main-content" class="page-content" tabindex="-1">
        <div v-if="accessDenied" class="alert alert-warning" role="alert">
          当前账号没有访问组织管理页面的权限。
        </div>
        <RouterView />
      </main>
    </div>
  </div>
</template>