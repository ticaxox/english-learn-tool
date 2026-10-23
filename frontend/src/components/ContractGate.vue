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
</script>

<template>
  <section class="contract-gate" aria-live="polite">
    <div class="contract-gate__mark" aria-hidden="true">✒</div>
    <div class="contract-gate__body">
      <h2>{{ props.title }}</h2>
      <p>
        后端 <code>T-BE-004</code> 尚未发布冻结的 OpenAPI。本页已就绪的路由、校验与交互骨架当前
        <strong>不会</strong>读取任何数据，也不会用示例卡片、假评分或假计时占位。
      </p>
      <p class="contract-gate__coordinate">{{ coordinate }}</p>
      <div class="contract-gate__endpoints">
        <span class="contract-gate__label">待校准端点</span>
        <ul>
          <li v-for="endpoint in props.endpoints" :key="endpoint">
            <code>{{ endpoint }}</code>
          </li>
        </ul>
      </div>
      <p v-if="frozen" class="inline-note">
        契约坐标已写入，但解析器仍需按 OpenAPI 逐字段实现后才能展示数据。
      </p>
      <p v-else class="inline-note">
        A01 给出唯一 <code>contract_sha</code> 与 <code>openapi_sha256</code> 后，本项目只需修改
        <code>src/api/contract-adapter.ts</code> 一处即可完成校准。
      </p>
    </div>
  </section>
</template>
