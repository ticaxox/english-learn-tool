<script setup lang="ts">
/**
 * 学习中心的练习选择：表头切换记忆/AI，内容在下方展开，不跳转页面。
 */
import { computed, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import AppIcon from './AppIcon.vue'
import ErrorNotice from './ErrorNotice.vue'
import { fetchMemoryConfig } from '../api/learning'
import {
  createPracticeSession,
  PRACTICE_TYPE_LABELS,
  type PracticeCreateInput,
  type PracticeType,
} from '../api/practice'
import {
  MEMORY_MODULES,
  MEMORY_MODULE_LABELS,
  type MemoryConfig,
  type MemoryModule,
} from '../types/learning'

const router = useRouter()
const active = ref<'memory' | 'practice'>('memory')
const memoryConfig = ref<MemoryConfig | null>(null)
const configError = ref<unknown>(null)
const starting = ref(false)
const startError = ref<unknown>(null)
const practiceType = ref<PracticeType>('fill_blank')
const count = ref(5)

const memoryModes = computed<MemoryModule[]>(() => MEMORY_MODULES.filter((module) => memoryConfig.value?.[module].enabled))
const counts = computed(() => (practiceType.value === 'writing' ? [1] : [3, 5, 10, 15, 20]))

const descriptions: Record<MemoryModule, string> = {
  flashcard: '看词回忆释义',
  choice: '选出正确释义',
  spelling: '按提示拼写',
}
const typeDescriptions: Record<PracticeType, string> = {
  fill_blank: '词义与语境',
  reading: '文章理解',
  translation: '英译中 / 中译英',
  writing: 'AI 评分作文',
}

watch(practiceType, (type) => {
  count.value = type === 'writing' ? 1 : 5
})

onMounted(() => {
  void loadConfig()
})

async function loadConfig(): Promise<void> {
  try {
    memoryConfig.value = await fetchMemoryConfig()
  } catch (error) {
    configError.value = error
  }
}

function startMemory(module: MemoryModule): void {
  void router.push({ name: 'memory', query: { module } })
}

function newKey(): string {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') return crypto.randomUUID()
  return `practice-${Date.now()}-${Math.random().toString(16).slice(2)}`
}

async function startPractice(): Promise<void> {
  if (starting.value) return
  const input: PracticeCreateInput = {
    practiceType: practiceType.value,
    source: 'today_new',
    count: count.value,
    difficulty: null,
    wordbookId: null,
  }
  starting.value = true
  startError.value = null
  try {
    const session = await createPracticeSession(input, newKey())
    await router.push({ name: 'practice-session', params: { sessionId: session.id } })
  } catch (error) {
    startError.value = error
  } finally {
    starting.value = false
  }
}
</script>

<template>
  <section class="practice-chooser" aria-label="选择练习方式">
    <div class="practice-chooser__tabs" role="tablist" aria-label="练习类型">
      <button
        class="practice-chooser__tab"
        :class="{ 'is-active': active === 'memory' }"
        type="button"
        role="tab"
        :aria-selected="active === 'memory'"
        @click="active = 'memory'"
      >记忆练习</button>
      <button
        class="practice-chooser__tab"
        :class="{ 'is-active': active === 'practice' }"
        type="button"
        role="tab"
        :aria-selected="active === 'practice'"
        @click="active = 'practice'"
      >AI 练习</button>
    </div>

    <div v-if="active === 'memory'" class="practice-chooser__panel" role="tabpanel" aria-label="记忆练习">
      <ErrorNotice v-if="configError" :error="configError" retry-label="重新读取" @retry="loadConfig" />
      <div class="practice-chooser__rows">
        <button
          v-for="module in MEMORY_MODULES"
          :key="module"
          class="practice-chooser__row"
          type="button"
          :disabled="memoryConfig !== null && !memoryModes.includes(module)"
          @click="startMemory(module)"
        >
          <span class="practice-chooser__mark" aria-hidden="true">
            <AppIcon :name="module === 'spelling' ? 'star' : module === 'choice' ? 'cards' : 'book'" />
          </span>
          <span class="practice-chooser__copy">
            <strong>{{ MEMORY_MODULE_LABELS[module] }}</strong>
            <small>{{ descriptions[module] }}</small>
          </span>
          <span class="practice-chooser__state">{{ memoryConfig === null || memoryModes.includes(module) ? '开始' : '未启用' }}</span>
        </button>
      </div>
    </div>

    <div v-else class="practice-chooser__panel" role="tabpanel" aria-label="AI 练习">
      <div class="practice-chooser__types">
        <button
          v-for="type in (['fill_blank', 'reading', 'translation', 'writing'] as PracticeType[])"
          :key="type"
          class="practice-chooser__type"
          :class="{ 'is-selected': practiceType === type }"
          type="button"
          @click="practiceType = type"
        >
          <strong>{{ PRACTICE_TYPE_LABELS[type] }}</strong>
          <small>{{ typeDescriptions[type] }}</small>
        </button>
      </div>

      <div class="practice-chooser__footer">
        <label class="practice-chooser__count">
          <span>题量</span>
          <select v-model.number="count">
            <option v-for="value in counts" :key="value" :value="value">{{ value }} 题</option>
          </select>
        </label>
        <ErrorNotice v-if="startError" :error="startError" :show-retry="false" />
        <button class="button" type="button" :disabled="starting" @click="startPractice">
          {{ starting ? '正在生成…' : '生成并开始' }} <AppIcon name="arrow" />
        </button>
      </div>
    </div>
  </section>
</template>
