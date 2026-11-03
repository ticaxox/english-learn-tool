<script setup lang="ts">
import { RouterView } from 'vue-router'
import SvgStamp from '../components/SvgStamp.vue'
</script>

<template>
  <article class="ia-settings-hub workspace-page">
    <header class="ia-hub-header">
      <div>
        <h1>设置</h1>
        <p>学习目标、AI 配置和账户安全集中在一页管理。</p>
      </div>
      <SvgStamp label="仅自己可见" />
    </header>

    <RouterView />
  </article>
</template>
