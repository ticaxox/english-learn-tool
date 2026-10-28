<script setup lang="ts">
import { RouterLink } from 'vue-router'
</script>

<template>
  <section class="panel">
    <p class="eyebrow">页面未找到</p>
    <h1>没有找到这个页面</h1>
    <p class="lead">这个地址不属于当前个人学习空间。</p>
    <RouterLink class="button" to="/overview">返回今日学习</RouterLink>
  </section>
</template>
