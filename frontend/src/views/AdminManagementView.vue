<script setup lang="ts">
import { computed } from 'vue'
import { RouterLink, RouterView, useRoute } from 'vue-router'

const route = useRoute()
const tabs = [
  { label: '成员管理', to: '/admin/users', key: 'members' },
  { label: '组织看板', to: '/admin/dashboard', key: 'dashboard' },
  { label: 'AI 平台', to: '/admin/ai/providers', key: 'ai' },
]

const activeTab = computed(() => {
  if (route.path.startsWith('/admin/ai')) return 'ai'
  if (route.path.startsWith('/admin/dashboard')) return 'dashboard'
  return 'members'
})
</script>

<template>
  <article class="ia-admin-hub workspace-page">
    <header class="ia-hub-header">
      <div>
        <p class="eyebrow">组织管理</p>
        <h1>组织管理</h1>
        <p>成员、学习看板与 AI 平台都在这里管理。</p>
      </div>
      <span class="ia-hub-badge">管理员</span>
    </header>

    <nav class="ia-tabs ia-admin-tabs" aria-label="组织管理页签">
      <RouterLink
        v-for="tab in tabs"
        :key="tab.key"
        :to="tab.to"
        class="ia-tab"
        :class="{ 'ia-tab--active': activeTab === tab.key }"
        :aria-current="activeTab === tab.key ? 'page' : undefined"
      >
        {{ tab.label }}
      </RouterLink>
    </nav>

    <RouterView />
  </article>
</template>