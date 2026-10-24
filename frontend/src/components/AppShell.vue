<script setup lang="ts">
import { computed } from 'vue'
import { useRoute, useRouter, RouterLink, RouterView } from 'vue-router'
import { useAuthStore } from '../stores/auth'
import MemberShell from './MemberShell.vue'
import WhiskerCrumbMark from './WhiskerCrumbMark.vue'

const auth = useAuthStore()
const route = useRoute()
const router = useRouter()

const adminLinks = [
  { label: '组织看板', to: '/admin/dashboard' },
  { label: '成员管理', to: '/admin/users' },
  { label: 'AI 提供商', to: '/admin/ai/providers' },
  { label: 'AI 提示词', to: '/admin/ai/prompts' },
  { label: 'AI 用量', to: '/admin/ai/usage' },
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
  <MemberShell
    v-if="!auth.isAdmin"
    :display-name="auth.displayName"
    :username="auth.user?.username ?? ''"
    @signout="signOut"
  >
    <div v-if="accessDenied" class="alert alert-warning" role="alert">
      当前账号没有访问组织管理页面的权限。
    </div>
    <RouterView />
  </MemberShell>

  <template v-else>
    <a class="skip-link" href="#main-content">跳到主要内容</a>

    <div class="app-shell app-shell--admin">
      <aside class="sidebar">
        <div class="brand-row">
          <span class="brand-mark"><WhiskerCrumbMark size="small" /></span>
          <div class="brand-copy">
            <strong>AI 英语学习平台</strong>
            <span>组织内部学习空间</span>
          </div>
        </div>

        <nav aria-label="主要导航">
          <div class="nav-group">
            <p class="nav-label">学习</p>
            <ul class="nav-list">
              <li><RouterLink to="/overview">学习概览</RouterLink></li>
              <li><RouterLink to="/wordbooks">词书</RouterLink></li>
              <li><RouterLink to="/memory">记忆练习</RouterLink></li>
              <li><RouterLink to="/practice">AI 练习</RouterLink></li>
              <li><RouterLink to="/challenges">每日闯关</RouterLink></li>
              <li><RouterLink to="/coach">AI 教练</RouterLink></li>
              <li><RouterLink to="/notifications">通知</RouterLink></li>
              <li><RouterLink to="/settings">学习设置</RouterLink></li>
            </ul>
          </div>

          <div class="nav-group">
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
          <p><span class="topbar-kicker">WHISKER CRUMB</span> 管理端保持编辑化密度；所有数据均来自真实 API。</p>
          <div class="topbar-actions">
            <span class="inline-note">真实账号、学习与 AI 平台管理</span>
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
</template>
