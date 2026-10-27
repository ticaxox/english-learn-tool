<script setup lang="ts">
import { RouterLink, RouterView } from 'vue-router'

const tabs = [
  { label: '学习设置', to: '/settings/learning' },
  { label: '通知与免打扰', to: '/settings/notifications' },
  { label: '账户安全', to: '/settings/security' },
]
</script>

<template>
  <article class="ia-settings-hub workspace-page">
    <header class="ia-hub-header">
      <div>
        <p class="eyebrow">设置</p>
        <h1>设置</h1>
        <p>学习目标、通知偏好和账户安全集中在一页管理。</p>
      </div>
      <span class="ia-hub-badge">个人中心</span>
    </header>

    <nav class="ia-tabs ia-settings-tabs" aria-label="设置页签">
      <RouterLink
        v-for="tab in tabs"
        :key="tab.to"
        :to="tab.to"
        class="ia-tab"
        active-class="ia-tab--active"
      >
        {{ tab.label }}
      </RouterLink>
    </nav>

    <RouterView />
  </article>
</template>