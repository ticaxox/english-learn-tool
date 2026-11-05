<script setup lang="ts">
import { RouterLink } from 'vue-router'
import PracticeTaskList from '../components/PracticeTaskList.vue'
</script>

<template>
  <article class="practice-page practice-tasks-page workspace-page">
    <header class="workspace-page-header">
      <div>
        <p class="workspace-kicker">AI 练习</p>
        <h1>题目列表</h1>
        <p class="workspace-page-lead">所有生成过的题目和预生成套题都在这里，点击一条查看操作。</p>
      </div>
      <RouterLink class="button-secondary" to="/practice">新建练习</RouterLink>
    </header>
    <PracticeTaskList show-tabs :heading="false" />
  </article>
</template>
