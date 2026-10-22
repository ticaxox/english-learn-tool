<script setup lang="ts">
import { RouterLink } from 'vue-router'
</script>

<template>
  <section class="panel">
    <p class="eyebrow">404</p>
    <h1>没有找到这个页面</h1>
    <p class="lead">当前地址不属于 v1.1 已登记的前端路由。</p>
    <RouterLink class="button" to="/overview">返回学习概览</RouterLink>
  </section>
</template>