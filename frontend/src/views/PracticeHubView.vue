<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import AppIcon from '../components/AppIcon.vue'
import ArtImage from '../components/ArtImage.vue'
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
import PracticeShelf from '../components/PracticeShelf.vue'
import DrillConfigDialog from '../components/DrillConfigDialog.vue'

import '../practice.css'
import ShelfPicker from '../components/ShelfPicker.vue'
import { illustration, settingsCard } from '../assets/halloween'

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

/** The spelling drill has one setting, so it asks before it starts. */
const spellingOpen = ref(false)

/** 记忆题型配置：哪几个面可以出现，改一次对三种练习都生效。 */
const drillConfigOpen = ref(false)

function startMemory(module: MemoryModule): void {
  if (module === 'spelling') {
    spellingOpen.value = true
    return
  }
  void router.push({ name: 'practice', query: { module } })
}

function startSpelling(): void {
  spellingOpen.value = false
  void router.push({ name: 'practice', query: { module: 'spelling' } })
}
const practiceTypes: PracticeType[] = ['fill_blank', 'reading', 'translation', 'writing']
const practiceTypeOptions: PracticeType[] = [...practiceTypes, 'conversation', 'mixed']

/** 书架分三行：记忆三本一行，练习三本一行，对话、作文和设置一行。 */
const exerciseRow: PracticeType[] = ['fill_blank', 'reading', 'translation']
const pairRow: PracticeType[] = ['conversation', 'writing']
/** 设置不是一种练习，它打开的是练习的题型配置。 */
const settingsBooks = [
  { key: 'settings', label: '设置', hint: '配置练习的题型', art: settingsCard },
]
function queryType(value: unknown): PracticeType | null {
  return typeof value === 'string' && practiceTypeOptions.includes(value as PracticeType)
    ? (value as PracticeType)
    : null
}
const practiceType = ref<PracticeType>(queryType(route.query.type) ?? 'fill_blank')
const source = ref<PracticeSource>('today_new')
// A conversation is one dialogue and an essay one piece: neither counts in fives.
const singlePieceTypes: PracticeType[] = ['writing', 'conversation']
const count = ref(singlePieceTypes.includes(practiceType.value) ? 1 : 5)
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
const counts = computed(() => (singlePieceTypes.includes(practiceType.value) ? [1] : [3, 5, 10, 15, 20]))
const needsDifficulty = computed(() => source.value === 'difficulty')
const needsWordbook = computed(() => source.value !== 'difficulty')
onMounted(() => { void loadSpellingMode() })

// The URL names the exercise, so arriving with ?type=writing opens its
// settings rather than leaving the learner to pick the same thing again.
function openFromQuery(value: unknown): void {
  const next = queryType(value)
  if (!next) return
  if (next !== practiceType.value) selectType(next)
  configOpen.value = true
}

watch(() => route.query.type, openFromQuery)

function newKey(): string {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') return crypto.randomUUID()
  return `practice-${Date.now()}-${Math.random().toString(16).slice(2)}`
}

function signature(input: PracticeCreateInput): string {
  return JSON.stringify(input)
}

function selectType(next: PracticeType): void {
  practiceType.value = next
  count.value = singlePieceTypes.includes(next) ? 1 : 5
}

// The form is a dialog now: picking a book opens it for that exercise.
const configOpen = ref(false)

function openConfig(next: PracticeType): void {
  selectType(next)
  formError.value = null
  configOpen.value = true
  void router.replace({ query: { ...route.query, type: next } })
}

function closeConfig(): void {
  configOpen.value = false
  formError.value = null
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
  openFromQuery(route.query.type)
})
</script>

<template>
  <article class="practice-page practice-hub member-practice-page practice-workspace workspace-page">
    <MemoryPracticeView v-if="memoryModule" embedded />
    <PracticeSessionView v-else-if="activeSessionId" embedded :session-id="activeSessionId" />

    <template v-else>
      <!-- 书架在左、题目列表在右：书分三行摆，列表是右边的边栏。 -->
      <div class="practice-hub-layout practice-hub-layout--split">
        <div class="practice-hub-shelf">
          <ShelfPicker
            :modules="MEMORY_MODULES"
            :enabled="enabledMemoryModules"
            :labels="MEMORY_MODULE_LABELS"
            @pick="startMemory"
          />

          <PracticeShelf :types="exerciseRow" :labels="PRACTICE_TYPE_LABELS" @pick="openConfig" />

          <PracticeShelf
            :types="pairRow"
            :labels="PRACTICE_TYPE_LABELS"
            :extra="settingsBooks"
            @pick="openConfig"
            @pick-extra="drillConfigOpen = true"
          />
        </div>

        <PracticeTaskList class="practice-hub-tasks" :limit="8" show-tabs />
      </div>

      <DrillConfigDialog
        :open="drillConfigOpen"
        @close="drillConfigOpen = false"
        @saved="memoryConfig = $event"
      />

      <div v-if="spellingOpen" class="dialog-backdrop" @click.self="spellingOpen = false">
        <section class="dialog-card practice-config-dialog" role="dialog" aria-modal="true" aria-labelledby="spelling-start-title">
          <header class="practice-config-dialog__head">
            <div>
              <h2 id="spelling-start-title">拼写练习</h2>
              <p class="field-hint">给出一个词的中文和读音，按字母把它拼回来。</p>
            </div>
            <DivButton class="icon-button practice-config-dialog__close" type="button" aria-label="关闭" @click="spellingOpen = false">
              <AppIcon name="close" />
            </DivButton>
          </header>

          <div class="practice-form">
            <div class="practice-form-row">
              <div class="field">
                <label for="practice-spelling-mode">挖空方式</label>
                <select id="practice-spelling-mode" v-model="spellingBlankMode" @change="saveSpellingMode">
                  <option value="">随机（推荐）</option>
                  <option value="full">整词挖空</option>
                  <option value="partial">部分字母</option>
                  <option value="first_letter">只留首字母</option>
                  <option value="middle">中间挖空</option>
                </select>
                <p class="field-hint">决定题目里哪些字母先给你、哪些要自己填。</p>
              </div>
            </div>
            <div class="practice-create-footer">
              <SvgPlateButton type="button" @click="startSpelling">开始拼写 <AppIcon name="arrow" /></SvgPlateButton>
            </div>
          </div>
        </section>
      </div>

      <div v-if="configOpen" class="dialog-backdrop" @click.self="closeConfig">
      <section class="dialog-card practice-config-dialog" role="dialog" aria-modal="true" aria-labelledby="practice-create-title">
        <header class="practice-config-dialog__head">
          <div>
            <h2 id="practice-create-title">{{ PRACTICE_TYPE_LABELS[practiceType] }}练习</h2>
            <p v-if="practiceType === 'mixed'" class="field-hint">同一组题里混合多种题型，按整组题量生成。</p>
            <p v-else-if="practiceType === 'conversation'" class="field-hint">AI 会想出一个话题，由它扮演角色引导整段对话；可以用文字或语音作答。</p>
          </div>
          <DivButton class="icon-button practice-config-dialog__close" type="button" aria-label="关闭" @click="closeConfig">
            <AppIcon name="close" />
          </DivButton>
        </header>

        <form class="practice-form" novalidate @submit.prevent="create">
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
            <div v-if="!singlePieceTypes.includes(practiceType)" class="field">
              <label for="practice-count">题量</label>
              <select id="practice-count" v-model.number="count">
                <option v-for="item in counts" :key="item" :value="item">{{ item }} 题</option>
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
            <ArtImage class="practice-generation-art" :set="illustration.brewing" />
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
      </div>
    </template>
  </article>
</template>
