<script setup lang="ts">
import { RouterLink } from 'vue-router'
import ArtImage from '../components/ArtImage.vue'
import { illustration } from '../assets/halloween'
</script>

<template>
  <section class="panel not-found">
    <ArtImage class="not-found__art" :set="illustration.notFound" />
    <div>
      <p class="eyebrow">页面未找到</p>
      <h1>没有找到这个页面</h1>
      <p class="lead">这个地址不属于当前个人学习空间。</p>
      <RouterLink class="button" to="/overview">返回今日学习</RouterLink>
    </div>
  </section>
</template>

<style scoped>
/* A wrong address is a small moment, so it gets a wink rather than a scolding. */
.not-found {
  display: flex;
  align-items: center;
  gap: 1.75rem;
}

.not-found__art {
  display: block;
  width: clamp(140px, 22vw, 220px);
  flex: 0 0 auto;
}

.not-found__art :deep(.art-swap),
.not-found__art :deep(.art-swap__stack) {
  display: block;
  width: 100%;
}

.not-found__art :deep(.art-swap__frame) {
  width: 100%;
  height: auto;
}

@media (max-width: 640px) {
  .not-found {
    flex-direction: column;
    align-items: flex-start;
  }
}
</style>
