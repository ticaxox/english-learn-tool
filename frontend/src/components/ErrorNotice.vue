<script setup lang="ts">
import { computed } from 'vue'
import { fieldIssues, toErrorPresentation } from '../api/errors'

const props = withDefaults(
  defineProps<{
    error: unknown
    retryLabel?: string
    showRetry?: boolean
  }>(),
  {
    retryLabel: '重试',
    showRetry: undefined,
  },
)

const emit = defineEmits<{
  retry: []
}>()

const presentation = computed(() => toErrorPresentation(props.error))
const issues = computed(() => fieldIssues(props.error))
const canRetry = computed(() => props.showRetry ?? presentation.value.retryable)
</script>

<template>
  <section class="alert alert-error error-notice" role="alert" aria-live="polite">
    <div class="error-notice__heading">
      <span class="error-notice__mark" aria-hidden="true">!</span>
      <strong>{{ presentation.title }}</strong>
    </div>
    <p>{{ presentation.message }}</p>
    <details v-if="issues.length > 0 || presentation.requestId">
      <summary>查看问题详情</summary>
      <div role="list" v-if="issues.length > 0" class="field-issue-list">
        <div role="listitem" v-for="issue in issues" :key="`${issue.path}-${issue.message}`">
          <strong v-if="issue.path"><code>{{ issue.path }}</code></strong>
          {{ issue.message }}
        </div>
      </div>
      <p v-if="presentation.requestId" class="request-id">
        服务编号：<code>{{ presentation.requestId }}</code>
      </p>
    </details>
    <div v-if="canRetry" class="button-row">
      <DivButton class="button-secondary" type="button" @click="emit('retry')">
        {{ props.retryLabel }}
      </DivButton>
    </div>
  </section>
</template>
