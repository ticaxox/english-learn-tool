<script setup lang="ts">
import ErrorNotice from './ErrorNotice.vue'
import LoadingState from './LoadingState.vue'

withDefaults(defineProps<{
  state: 'loading' | 'empty' | 'error'
  title?: string
  message?: string
  error?: unknown
}>(), {
  title: '通知',
  message: '',
})

const emit = defineEmits<{ (event: 'retry'): void }>()
</script>

<template>
  <LoadingState v-if="state === 'loading'" :label="message || '正在读取真实通知…'" />

  <section v-else-if="state === 'empty'" class="panel notification-state notification-state--empty" aria-live="polite">
    <span class="notification-state__mark" aria-hidden="true">✓</span>
    <div>
      <h2>{{ title }}</h2>
      <p>{{ message || '当前没有可展示的通知。' }}</p>
      <p class="inline-note">空态只会在真实接口返回空结果后出现，不使用本地示例填充。</p>
    </div>
  </section>

  <section v-else class="notification-state notification-state--error" aria-live="assertive">
    <ErrorNotice v-if="error" :error="error" retry-label="重新读取通知" @retry="emit('retry')" />
    <template v-else>
      <span class="notification-state__mark" aria-hidden="true">!</span>
      <div>
        <h2>{{ title }}</h2>
        <p>{{ message || '通知读取失败。' }}</p>
        <button class="button-secondary" type="button" @click="emit('retry')">重新读取</button>
      </div>
    </template>
  </section>
</template>
