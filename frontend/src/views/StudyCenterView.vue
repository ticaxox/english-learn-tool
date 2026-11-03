<script setup lang="ts">
import PracticeChooser from '../components/PracticeChooser.vue'
</script>

<template>
  <article class="study-center workspace-page">
    <header class="workspace-page-header">
      <div>
        <p class="workspace-kicker">练习入口</p>
        <h1>学习中心</h1>
        <p class="workspace-page-lead">记忆练习和 AI 练习都在这里开始，计时与拼写挖空方式也在这里配置。</p>
      </div>
    </header>

    <PracticeChooser />
  </article>
</template>
