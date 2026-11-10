<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import AppIcon from '../components/AppIcon.vue'
import SvgPlateButton from '../components/SvgPlateButton.vue'
import ErrorNotice from '../components/ErrorNotice.vue'
import {
  createPracticeSession,
  PRACTICE_SOURCE_LABELS,
  PRACTICE_TYPE_LABELS,
  type PracticeCreateInput,
  type PracticeDifficulty,
  type PracticeSource,
  type PracticeType,
  type TranslationDirection,
} from '../api/practice'
import { listWordbooks, type Wordbook } from '../api/wordbooks'
import { fetchLearningProfile, fetchMemoryConfig, saveMemoryConfig } from '../api/learning'
import { useToast } from '../composables/useToast'
import PracticeSessionView from './PracticeSessionView.vue'
import MemoryPracticeView from './MemoryPracticeView.vue'
import { MEMORY_MODULES, MEMORY_MODULE_LABELS, type MemoryConfig, type MemoryModule } from '../types/learning'
import PracticeTaskList from '../components/PracticeTaskList.vue'
import GameHud from '../components/GameHud.vue'

import '../practice.css'
import ShelfPicker from '../components/ShelfPicker.vue'
import { illustration, practiceBooks } from '../assets/halloween'

const router = useRouter()
const route = useRoute()
const activeSessionId = computed(() => (typeof route.query.session === 'string' && route.query.session ? route.query.session : null))
// Memory training is the same page: ?module=flashcard|choice|spelling starts it here.
const memoryModule = computed<MemoryModule | null>(() => {
  const value = route.query.module
  return value === 'flashcard' || value === 'choice' || value === 'spelling' ? value : null
})
const memoryConfig = ref<MemoryConfig | null>(null)

async function loadMemoryConfig(): Promise<void> {
  try {
    memoryConfig.value = await fetchMemoryConfig()
  } catch {
    memoryConfig.value = null
  }
}

function memoryEnabled(module: MemoryModule): boolean {
  return memoryConfig.value ? memoryConfig.value[module].enabled : true
}

/** The shelf needs the list, not a predicate; default open until config lands. */
const enabledMemoryModules = computed(() => MEMORY_MODULES.filter(memoryEnabled))

function startMemory(module: MemoryModule): void {
  void router.push({ name: 'practice', query: { module } })
}
const practiceTypes: PracticeType[] = ['fill_blank', 'reading', 'translation', 'writing']
const practiceTypeOptions: PracticeType[] = [...practiceTypes, 'mixed']
function queryType(value: unknown): PracticeType | null {
  return typeof value === 'string' && practiceTypeOptions.includes(value as PracticeType)
    ? (value as PracticeType)
    : null
}
const practiceType = ref<PracticeType>(queryType(route.query.type) ?? 'fill_blank')
const source = ref<PracticeSource>('today_new')
const count = ref(practiceType.value === 'writing' ? 1 : 5)
const difficulty = ref<PracticeDifficulty>('CET6')
const translationDirection = ref<TranslationDirection>('en_to_zh')
const writingTargetWords = ref<number>(150)
const DIRECTIONS: TranslationDirection[] = ['en_to_zh', 'zh_to_en', 'mixed']
const DIRECTION_LABELS: Record<TranslationDirection, string> = {
  en_to_zh: '英译中',
  zh_to_en: '中译英',
  mixed: '混合',
}
const WRITING_LENGTHS = [50, 100, 150, 200, 250, 300]
const wordbookId = ref('')
const creating = ref(false)
const createError = ref<unknown>(null)


const wordbooks = ref<Wordbook[]>([])
const wordbooksError = ref<unknown>(null)
const toast = useToast()
const spellingBlankMode = ref('')
const timerLimit = ref<number>(0)

function onTimerLimitChange(event: Event): void {
  timerLimit.value = Number((event.target as HTMLSelectElement).value) || 0
}

async function loadSpellingMode(): Promise<void> {
  try {
    const profile = await fetchLearningProfile()
    spellingBlankMode.value = profile.memoryConfig.spelling.blankType ?? ''
  } catch {
    spellingBlankMode.value = ''
  }
}

async function saveSpellingMode(): Promise<void> {
  try {
    const profile = await fetchLearningProfile()
    await saveMemoryConfig({
      ...profile.memoryConfig,
      spelling: {
        ...profile.memoryConfig.spelling,
        blankType: (spellingBlankMode.value || null) as typeof profile.memoryConfig.spelling.blankType,
      },
    })
    toast.success('拼写挖空方式已保存')
  } catch {
    toast.error('没有保存成功', '稍后再试一次。')
  }
}
const formError = ref<string | null>(null)
let pendingKey: string | null = null
let pendingSignature = ''

const sources: PracticeSource[] = ['today_new', 'today_review', 'memory_mistakes', 'whole_book', 'difficulty']
const difficulties: PracticeDifficulty[] = [
  'GAOKAO',
  'CET4',
  'CET6',
  'POSTGRAD',
  'IELTS',
  'TOEFL',
]
const counts = computed(() => (practiceType.value === 'writing' ? [1] : [3, 5, 10, 15, 20]))
const needsDifficulty = computed(() => source.value === 'difficulty')
const needsWordbook = computed(() => source.value !== 'difficulty')
onMounted(() => { void loadSpellingMode() })

watch(() => route.query.type, (value) => {
  const next = queryType(value)
  if (next && next !== practiceType.value) selectType(next)
})

function newKey(): string {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') return crypto.randomUUID()
  return `practice-${Date.now()}-${Math.random().toString(16).slice(2)}`
}

function signature(input: PracticeCreateInput): string {
  return JSON.stringify(input)
}

function selectType(next: PracticeType): void {
  practiceType.value = next
  count.value = next === 'writing' ? 1 : 5
}

const typeIcons: Record<PracticeType, 'book' | 'cards' | 'arrow' | 'spark' | 'star'> = {
  fill_blank: 'book',
  reading: 'cards',
  translation: 'arrow',
  writing: 'spark',
  mixed: 'star',
}

const typeOptions = computed(() =>
  practiceTypeOptions.map((type) => ({ key: type, label: PRACTICE_TYPE_LABELS[type] })),
)

function chooseType(next: PracticeType): void {
  selectType(next)
  void router.replace({ query: { ...route.query, type: next } })
}

function validate(): string | null {
  if (!counts.value.includes(count.value)) return '题量不符合当前题型允许值。'
  if (needsDifficulty.value && !difficulty.value) return '按难度练习必须选择考试难度。'
  return null
}

async function create(): Promise<void> {
  formError.value = validate()
  if (formError.value) return
  const input: PracticeCreateInput = {
    practiceType: practiceType.value,
    source: source.value,
    count: count.value,
    difficulty: needsDifficulty.value ? difficulty.value : null,
    wordbookId: needsWordbook.value && wordbookId.value ? wordbookId.value : null,
    translationDirection:
      practiceType.value === 'translation' ? translationDirection.value : null,
    writingTargetWords:
      practiceType.value === 'writing' ? writingTargetWords.value : null,
  }
  const sig = signature(input)
  if (!pendingKey || pendingSignature !== sig) {
    pendingKey = newKey()
    pendingSignature = sig
  }
  creating.value = true
  createError.value = null
  try {
    const session = await createPracticeSession(input, pendingKey)
    pendingKey = null
    pendingSignature = ''
    await router.push({
      name: 'practice',
      query: {
        session: session.id,
        ...(timerLimit.value > 0 ? { timer: String(timerLimit.value) } : {}),
      },
    })
  } catch (error) {
    createError.value = error
  } finally {
    creating.value = false
  }
}

async function loadWordbooks(): Promise<void> {
  try {
    const page = await listWordbooks({ limit: 100 })
    wordbooks.value = page.items.filter((book) => book.status === 'ready' && book.visibility === 'private')
    wordbooksError.value = null
  } catch (error) {
    wordbooks.value = []
    wordbooksError.value = error
  }
}

onMounted(() => {
  void Promise.all([loadWordbooks(), loadMemoryConfig()])
})
</script>

<template>
  <article class="practice-page practice-hub member-practice-page practice-workspace workspace-page">
    <MemoryPracticeView v-if="memoryModule" embedded />
    <PracticeSessionView v-else-if="activeSessionId" embedded :session-id="activeSessionId" />

    <template v-else>
      <GameHud />

      <ShelfPicker
        :modules="MEMORY_MODULES"
        :enabled="enabledMemoryModules"
        :labels="MEMORY_MODULE_LABELS"
        @pick="startMemory"
      />

      <div class="practice-hub-layout">
      <section class="workspace-card practice-create-panel" aria-labelledby="practice-create-title">
        <h2 id="practice-create-title" class="visually-hidden">新建练习</h2>

        <form class="practice-form" novalidate @submit.prevent="create">
          <div class="practice-type-picker" role="group" aria-label="题型">
            <DivButton
              v-for="option in typeOptions"
              :key="option.key"
              class="practice-type-pill"
              :class="[`practice-type-pill--${option.key}`, { 'is-active': practiceType === option.key }]"
              :aria-pressed="practiceType === option.key"
              type="button"
              @click="chooseType(option.key)"
            >
              <img
                v-if="practiceBooks[option.key]"
                class="practice-type-pill__art"
                :src="practiceBooks[option.key].day"
                alt=""
              />
              <AppIcon v-else :name="typeIcons[option.key]" />
              <span class="practice-type-pill__label">{{ option.label }}</span>
            </DivButton>
          </div>
          <p v-if="practiceType === 'mixed'" class="field-hint">同一组题里混合多种题型，按整组题量生成。</p>
          <div class="practice-form-row">
            <div class="field">
              <label for="practice-source">来源</label>
              <select id="practice-source" v-model="source">
                <option v-for="item in sources" :key="item" :value="item">{{ PRACTICE_SOURCE_LABELS[item] }}</option>
              </select>
            </div>
            <div v-if="needsDifficulty" class="field">
              <label for="practice-difficulty">难度</label>
              <select id="practice-difficulty" v-model="difficulty">
                <option v-for="item in difficulties" :key="item" :value="item">{{ item }}</option>
              </select>
            </div>
            <div v-if="practiceType !== 'writing'" class="field">
              <label for="practice-count">题量</label>
              <select id="practice-count" v-model.number="count">
                <option v-for="item in counts" :key="item" :value="item">{{ item }} 题</option>
              </select>
            </div>
            <div class="field">
              <label for="practice-spelling-mode">拼写挖空方式</label>
              <select id="practice-spelling-mode" v-model="spellingBlankMode" @change="saveSpellingMode">
                <option value="">随机（推荐）</option>
                <option value="full">整词挖空</option>
                <option value="partial">部分字母</option>
                <option value="first_letter">只留首字母</option>
                <option value="middle">中间挖空</option>
              </select>
            </div>
            <div v-if="practiceType === 'translation'" class="field">
              <label for="practice-direction">翻译方向</label>
              <select id="practice-direction" v-model="translationDirection">
                <option v-for="item in DIRECTIONS" :key="item" :value="item">
                  {{ DIRECTION_LABELS[item] }}
                </option>
              </select>
            </div>
            <div v-if="practiceType === 'writing'" class="field">
              <label for="practice-writing-length">词数</label>
              <select id="practice-writing-length" v-model.number="writingTargetWords">
                <option v-for="item in WRITING_LENGTHS" :key="item" :value="item">{{ item }} 词</option>
              </select>
            </div>
            <div v-if="needsWordbook" class="field">
              <label for="practice-wordbook">词书</label>
              <select id="practice-wordbook" v-model="wordbookId">
                <option value="">使用当前激活词书</option>
                <option v-for="book in wordbooks" :key="book.id" :value="book.id">{{ book.name }}</option>
              </select>
              <p v-if="wordbooksError" class="field-hint">词书列表读取失败；仍可留空使用当前激活词书。</p>
            </div>
            <div class="field">
              <label for="practice-timer">计时</label>
              <select id="practice-timer" :value="timerLimit" @change="onTimerLimitChange">
                <option :value="0">不限（正计时）</option>
                <option :value="5">5 分钟</option>
                <option :value="10">10 分钟</option>
                <option :value="15">15 分钟</option>
                <option :value="20">20 分钟</option>
                <option :value="30">30 分钟</option>
              </select>
            </div>
          </div>

          <p v-if="formError" class="field-error" role="alert">{{ formError }}</p>
          <div v-if="creating" class="practice-generation-state is-loading" role="status" aria-live="polite">
            <img class="practice-generation-art" :src="illustration.brewing.day" alt="" />
            <div><strong>正在生成练习</strong><span>正在读取素材并准备题目，请稍候。</span></div>
          </div>
          <div v-else-if="createError" class="practice-generation-state is-error" role="status">
            <strong>这次没有生成成功</strong>
            <span>可以调整条件后重试，当前设置会保留。</span>
          </div>
          <ErrorNotice v-if="createError" :error="createError" :show-retry="false" retry-label="重试创建" @retry="create" />
          <div class="practice-create-footer">
            <SvgPlateButton class="practice-generate-action" type="submit" :disabled="creating">
              {{ creating ? '正在生成…' : '生成练习' }} <AppIcon name="arrow" />
            </SvgPlateButton>
          </div>
        </form>
      </section>

      <PracticeTaskList :limit="5" show-tabs />
      </div>
    </template>
  </article>
</template>
