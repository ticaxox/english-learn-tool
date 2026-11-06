<script setup lang="ts">
/**
 * 学习中心的练习选择：表头切换记忆/AI，内容在下方展开，不跳转页面。
 */
import { computed, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import AppIcon from './AppIcon.vue'
import ErrorNotice from './ErrorNotice.vue'
import SvgPlateButton from './SvgPlateButton.vue'
import { fetchLearningProfile, fetchMemoryConfig, saveMemoryConfig } from '../api/learning'

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
const spellingMode = ref('')
const savingMode = ref(false)
const memoryLimit = ref<number>(0)
const practiceLimit = ref<number>(0)

function setLimit(kind: 'memory' | 'practice', event: Event): void {
  const value = Number((event.target as HTMLSelectElement).value) || 0
  if (kind === 'memory') memoryLimit.value = value
  else practiceLimit.value = value
}

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
  mixed: '多种题型混合',
}

watch(practiceType, (type) => {
  count.value = type === 'writing' ? 1 : 5
})

onMounted(() => {
  void loadConfig()
  void loadSpellingMode()
})

async function loadSpellingMode(): Promise<void> {
  try {
    const profile = await fetchLearningProfile()
    spellingMode.value = profile.memoryConfig.spelling.blankType ?? ''
  } catch {
    spellingMode.value = ''
  }
}

async function saveSpellingMode(): Promise<void> {
  if (savingMode.value) return
  savingMode.value = true
  try {
    const profile = await fetchLearningProfile()
    await saveMemoryConfig({
      ...profile.memoryConfig,
      spelling: {
        ...profile.memoryConfig.spelling,
        blankType: (spellingMode.value || null) as typeof profile.memoryConfig.spelling.blankType,
      },
    })
  } finally {
    savingMode.value = false
  }
}

async function loadConfig(): Promise<void> {
  try {
    memoryConfig.value = await fetchMemoryConfig()
  } catch (error) {
    configError.value = error
  }
}

function startMemory(module: MemoryModule): void {
  void router.push({
    name: 'memory',
    query: memoryLimit.value > 0 ? { module, timer: String(memoryLimit.value) } : { module },
  })
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
    await router.push({
      name: 'practice-session',
      params: { sessionId: session.id },
      query: practiceLimit.value > 0 ? { timer: String(practiceLimit.value) } : {},
    })
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
      <DivButton
        class="practice-chooser__tab"
        :class="{ 'is-active': active === 'memory' }"
        type="button"
        role="tab"
        :aria-selected="active === 'memory'"
        @click="active = 'memory'"
      >记忆练习</DivButton>
      <DivButton
        class="practice-chooser__tab"
        :class="{ 'is-active': active === 'practice' }"
        type="button"
        role="tab"
        :aria-selected="active === 'practice'"
        @click="active = 'practice'"
      >AI 练习</DivButton>
    </div>

    <div v-if="active === 'memory'" class="practice-chooser__panel" role="tabpanel" aria-label="记忆练习">
      <div class="practice-chooser__toolbar">
        <label class="practice-timer-control">
          <span>计时</span>
          <select :value="memoryLimit" @change="setLimit('memory', $event)">
            <option :value="0">不限（正计时）</option>
            <option :value="5">5 分钟</option>
            <option :value="10">10 分钟</option>
            <option :value="15">15 分钟</option>
            <option :value="20">20 分钟</option>
            <option :value="30">30 分钟</option>
          </select>
        </label>
      </div>
      <ErrorNotice v-if="configError" :error="configError" retry-label="重新读取" @retry="loadConfig" />
      <div class="practice-chooser__rows">
        <DivButton
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
          <span v-if="module === 'spelling'" class="practice-chooser__config" @click.stop>
            <select
              v-model="spellingMode"
              aria-label="拼写挖空方式"
              :disabled="savingMode || !memoryModes.includes(module)"
              @change="saveSpellingMode"
            >
              <option value="">随机挖空</option>
              <option value="full">整词挖空</option>
              <option value="partial">部分字母</option>
              <option value="first_letter">只留首字母</option>
              <option value="middle">中间挖空</option>
            </select>
          </span>
          <span v-else-if="memoryConfig !== null && !memoryModes.includes(module)" class="practice-chooser__state">未启用</span>
          <AppIcon name="arrow" />
        </DivButton>
      </div>
    </div>

    <div v-else class="practice-chooser__panel" role="tabpanel" aria-label="AI 练习">
      <div class="practice-chooser__types">
        <DivButton
          v-for="type in (['fill_blank', 'reading', 'translation', 'writing', 'mixed'] as PracticeType[])"
          :key="type"
          class="practice-chooser__type"
          :class="{ 'is-selected': practiceType === type }"
          type="button"
          @click="practiceType = type"
        >
          <strong>{{ PRACTICE_TYPE_LABELS[type] }}</strong>
          <small>{{ typeDescriptions[type] }}</small>
        </DivButton>
      </div>

      <div class="practice-chooser__footer">
        <label class="practice-chooser__count">
          <span>题量</span>
          <select v-model.number="count">
            <option v-for="value in counts" :key="value" :value="value">{{ value }} 题</option>
          </select>
        </label>
        <label class="practice-timer-control">
          <span>计时</span>
          <select :value="practiceLimit" @change="setLimit('practice', $event)">
            <option :value="0">不限（正计时）</option>
            <option :value="5">5 分钟</option>
            <option :value="10">10 分钟</option>
            <option :value="15">15 分钟</option>
            <option :value="20">20 分钟</option>
            <option :value="30">30 分钟</option>
          </select>
        </label>
        <ErrorNotice v-if="startError" :error="startError" :show-retry="false" />
        <SvgPlateButton :disabled="starting" @click="startPractice">
          {{ starting ? '正在生成…' : '生成并开始' }} <AppIcon name="arrow" />
        </SvgPlateButton>
      </div>
    </div>
  </section>
</template>
