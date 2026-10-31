<script setup lang="ts">
/**
 * In-frame practice launcher.
 *
 * Opening a practice from 学习中心 must not leave the page: this dialog offers
 * the choices on top of the map, and only the actual session navigates.
 */
import { computed, ref, watch } from 'vue'
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

const props = defineProps<{
  open: boolean
  kind: 'memory' | 'practice'
}>()

const emit = defineEmits<{
  (event: 'close'): void
}>()

const router = useRouter()
const memoryConfig = ref<MemoryConfig | null>(null)
const configError = ref<unknown>(null)
const configLoading = ref(false)
const starting = ref(false)
const startError = ref<unknown>(null)
const practiceType = ref<PracticeType>('fill_blank')
const count = ref(5)

const memoryModes = computed<MemoryModule[]>(() => MEMORY_MODULES.filter((module) => memoryConfig.value?.[module].enabled))
const counts = computed(() => (practiceType.value === 'writing' ? [1] : [3, 5, 10, 15, 20]))
const title = computed(() => (props.kind === 'memory' ? '记忆练习' : 'AI 练习'))
const subtitle = computed(() => (props.kind === 'memory'
  ? '选一种方式，直接进入今天的复习队列。'
  : '选题型和题量，生成一组针对今天内容的练习。'))

const typeDescriptions: Record<PracticeType, string> = {
  fill_blank: '词义与语境',
  reading: '文章理解',
  translation: '英译中 / 中译英',
  writing: 'AI 评分作文',
}

watch(() => props.open, (open) => {
  if (!open) return
  startError.value = null
  if (props.kind === 'memory') void loadConfig()
}, { immediate: true })

watch(practiceType, (type) => {
  count.value = type === 'writing' ? 1 : 5
})

async function loadConfig(): Promise<void> {
  if (memoryConfig.value || configLoading.value) return
  configLoading.value = true
  configError.value = null
  try {
    memoryConfig.value = await fetchMemoryConfig()
  } catch (error) {
    configError.value = error
  } finally {
    configLoading.value = false
  }
}

function startMemory(module: MemoryModule): void {
  emit('close')
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
    emit('close')
    await router.push({ name: 'practice-session', params: { sessionId: session.id } })
  } catch (error) {
    startError.value = error
  } finally {
    starting.value = false
  }
}

function close(): void {
  if (!starting.value) emit('close')
}
</script>

<template>
  <div v-if="open" class="dialog-backdrop practice-launcher-backdrop" @click.self="close">
    <section
      class="dialog-card practice-launcher"
      role="dialog"
      aria-modal="true"
      :aria-label="title"
    >
      <header class="practice-launcher__header">
        <div>
          <p class="eyebrow">学习中心</p>
          <h2>{{ title }}</h2>
          <p class="field-hint">{{ subtitle }}</p>
        </div>
        <button class="workspace-icon-button" type="button" aria-label="关闭" @click="close">
          <AppIcon name="close" />
        </button>
      </header>

      <div v-if="kind === 'memory'" class="practice-launcher__body">
        <p v-if="configLoading" class="field-hint">正在读取记忆配置…</p>
        <ErrorNotice v-else-if="configError" :error="configError" retry-label="重新读取" @retry="loadConfig" />
        <template v-else>
          <button
            v-for="module in MEMORY_MODULES"
            :key="module"
            class="launcher-option"
            :class="{ 'is-disabled': !memoryModes.includes(module) }"
            type="button"
            :disabled="!memoryModes.includes(module)"
            @click="startMemory(module)"
          >
            <span class="launcher-option__mark" aria-hidden="true">
              <AppIcon :name="module === 'spelling' ? 'star' : module === 'choice' ? 'cards' : 'book'" />
            </span>
            <span class="launcher-option__copy">
              <strong>{{ MEMORY_MODULE_LABELS[module] }}</strong>
              <small>{{ module === 'flashcard' ? '看词回忆释义' : module === 'choice' ? '选出正确释义' : '按提示拼写' }}</small>
            </span>
            <span class="launcher-option__state">{{ memoryModes.includes(module) ? '开始' : '未启用' }}</span>
          </button>
        </template>
      </div>

      <div v-else class="practice-launcher__body">
        <div class="launcher-type-grid">
          <button
            v-for="type in (['fill_blank', 'reading', 'translation', 'writing'] as PracticeType[])"
            :key="type"
            class="launcher-type"
            :class="{ 'is-selected': practiceType === type }"
            type="button"
            @click="practiceType = type"
          >
            <strong>{{ PRACTICE_TYPE_LABELS[type] }}</strong>
            <small>{{ typeDescriptions[type] }}</small>
          </button>
        </div>

        <label class="launcher-count">
          <span>题量</span>
          <select v-model.number="count">
            <option v-for="value in counts" :key="value" :value="value">{{ value }} 题</option>
          </select>
        </label>

        <ErrorNotice v-if="startError" :error="startError" :show-retry="false" />

        <div class="launcher-actions">
          <button class="button" type="button" :disabled="starting" @click="startPractice">
            {{ starting ? '正在生成…' : '生成并开始' }} <AppIcon name="arrow" />
          </button>
          <button class="button-secondary" type="button" :disabled="starting" @click="close">取消</button>
        </div>
      </div>
    </section>
  </div>
</template>
