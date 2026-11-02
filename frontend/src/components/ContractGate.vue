<script setup lang="ts">
import { computed } from 'vue'
import { contractCoordinateLabel, isContractFrozen } from '../api/contract-adapter'

const props = withDefaults(
  defineProps<{
    /** Endpoints this page will read once the contract is frozen. */
    endpoints: string[]
    title?: string
  }>(),
  {
    title: '等待接口契约冻结',
  },
)

const coordinate = computed(() => contractCoordinateLabel())
const frozen = computed(() => isContractFrozen())
const showDiagnostics = import.meta.env.DEV
</script>

<template>
  <section class="contract-gate" aria-live="polite">
    <div class="contract-gate__mark" aria-hidden="true">✒</div>
    <div class="contract-gate__body">
      <h2>{{ props.title }}</h2>
      <p>这项功能暂时不可用，请稍后再试。学习记录不会因此丢失。</p>
      <details v-if="showDiagnostics">
        <summary>开发诊断</summary>
        <p class="contract-gate__coordinate">{{ coordinate }}</p>
        <div class="contract-gate__endpoints">
          <span class="contract-gate__label">待校准端点</span>
          <div role="list">
            <div role="listitem" v-for="endpoint in props.endpoints" :key="endpoint">
              <code>{{ endpoint }}</code>
            </div>
          </div>
        </div>
        <p v-if="frozen" class="inline-note">契约坐标已写入，解析器仍需逐字段校准。</p>
        <p v-else class="inline-note">等待契约冻结后校准唯一解析入口。</p>
      </details>
    </div>
  </section>
</template>
