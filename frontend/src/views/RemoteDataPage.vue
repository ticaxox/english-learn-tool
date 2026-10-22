<script setup lang="ts">
import { computed, onMounted, ref, shallowRef, watch } from 'vue'
import { apiClient } from '../api/client'
import ErrorNotice from '../components/ErrorNotice.vue'
import LoadingState from '../components/LoadingState.vue'

const props = defineProps<{
  title: string
  description: string
  endpoint: string
}>()

const data = shallowRef<unknown>(null)
const error = ref<unknown>(null)
const loading = ref(false)
const successRequestId = ref<string | null>(null)

const payloadSummary = computed(() => {
  const value = data.value
  if (value === null) {
    return '空响应'
  }
  if (Array.isArray(value)) {
    return `真实列表响应，共 ${value.length} 项`
  }
  if (typeof value === 'object') {
    return `真实对象响应，共 ${Object.keys(value).length} 个字段`
  }
  return `真实${typeof value}响应`
})

async function load(): Promise<void> {
  loading.value = true
  error.value = null
  successRequestId.value = null

  try {
    data.value = await apiClient.get<unknown>(props.endpoint)
    successRequestId.value = apiClient.getLastRequestId()
  } catch (requestError) {
    data.value = null
    error.value = requestError
  } finally {
    loading.value = false
  }
}

onMounted(load)
watch(() => props.endpoint, load)
</script>

<template>
  <article>
    <header class="page-header">
      <div>
        <p class="eyebrow">真实 API 接入骨架</p>
        <h1>{{ props.title }}</h1>
        <p>{{ props.description }}</p>
      </div>
      <button class="button-secondary" type="button" :disabled="loading" @click="load">
        重新请求
      </button>
    </header>

    <section class="panel" aria-live="polite">
      <LoadingState v-if="loading" />

      <ErrorNotice
        v-else-if="error"
        :error="error"
        retry-label="重试真实请求"
        @retry="load"
      />

      <div v-else class="alert alert-success">
        <strong>真实接口已响应</strong>
        <p>{{ payloadSummary }}</p>
        <p>本任务只交付应用壳层与接入基线，完整业务界面将在后续任务实现。</p>
        <div class="status-strip">
          <span>接口：<code>{{ props.endpoint }}</code></span>
          <span v-if="successRequestId">
            Request ID：<code>{{ successRequestId }}</code>
          </span>
        </div>
      </div>

      <p class="inline-note">
        页面不会用静态词条、假题目、假进度或 localStorage 填充空状态。后端不可用时，会保留真实错误和重试入口。
      </p>
    </section>
  </article>
</template>