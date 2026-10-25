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
  <section class="alert alert-error" role="alert" aria-live="polite">
    <strong>{{ presentation.title }}</strong>
    <p>{{ presentation.message }}</p>
    <ul v-if="issues.length > 0" class="field-issue-list">
      <li v-for="issue in issues" :key="`${issue.path}-${issue.message}`">
        <strong v-if="issue.path"><code>{{ issue.path }}</code></strong>
        {{ issue.message }}
      </li>
    </ul>
    <p v-if="presentation.requestId" class="request-id">
      问题编号：<code>{{ presentation.requestId }}</code>
    </p>
    <div v-if="canRetry" class="button-row">
      <button class="button-secondary" type="button" @click="emit('retry')">
        {{ props.retryLabel }}
      </button>
    </div>
  </section>
</template>
