<script setup lang="ts">
import { RouterLink, RouterView } from 'vue-router'
const tabs = [
  { label: '提供商', to: '/admin/ai/providers' },
  { label: '提示词', to: '/admin/ai/prompts' },
  { label: '用量', to: '/admin/ai/usage' },
]
</script>

<template>
  <section class="ia-ai-platform">
    <header class="ia-subsection-header">
      <div>
        <p class="eyebrow">AI 平台</p>
        <h2>平台配置</h2>
        <p>只展示真实 API 返回的提供商、提示词与用量数据。</p>
      </div>
    </header>

    <nav class="ia-tabs ia-subtabs" aria-label="AI 平台页签">
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
  </section>
</template>