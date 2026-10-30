<script setup lang="ts">
/**
 * /settings — learning profile and memory preferences.
 *
 * The form is validated locally for fast feedback, but the server remains the
 * authority for ranges, dates and eligibility. A successful save never claims
 * the change applies today: the backend decides when the new target takes
 * effect, and the page states that explicitly.
 */
import { computed, onMounted, reactive, ref } from 'vue'
import ErrorNotice from '../components/ErrorNotice.vue'
import LoadingState from '../components/LoadingState.vue'
import { useToast } from '../composables/useToast'
import ContractGate from '../components/ContractGate.vue'
import { fetchLearningProfile, updateLearningProfile } from '../api/learning'
import { listWordbooks } from '../api/wordbooks'
import { isContractFrozen } from '../api/contract-adapter'
import {
  defaultMemoryConfig,
  hasFieldErrors,
  todayIsoDate,
  validateProfile,
  type FieldErrors,
} from '../lib/learning-validation'
import {
  DAILY_MINUTES_MAX,
  DAILY_MINUTES_MIN,
  DAILY_NEW_WORDS_MAX,
  DAILY_NEW_WORDS_MIN,
  type ExamTarget,
  type LearningProfile,
  type LearningProfileUpdate,
  type MemoryConfig,
} from '../types/learning'
import '../learning.css'

const frozen = computed(() => isContractFrozen())

const profile = ref<LearningProfile | null>(null)
const loading = ref(false)
const saving = ref(false)
const loadError = ref<unknown>(null)
const saveError = ref<unknown>(null)
const saved = ref(false)
const toast = useToast()
const fieldErrors = ref<FieldErrors>({})
const activeWordbookSize = ref<number | null>(null)

const PRACTICE_TYPE_OPTIONS = [
  { key: 'fill_blank', label: '填空' },
  { key: 'reading', label: '阅读' },
  { key: 'translation', label: '翻译' },
  { key: 'writing', label: '作文' },
] as const
const DRILL_MODE_OPTIONS = [
  { key: 'choice', label: '选择' },
  { key: 'spelling', label: '拼写' },
] as const

const challengePrefs = reactive<{ practiceTypes: string[]; drillModes: string[] }>({
  practiceTypes: PRACTICE_TYPE_OPTIONS.map((option) => option.key),
  drillModes: DRILL_MODE_OPTIONS.map((option) => option.key),
})

const completionDays = computed(() => {
  if (!activeWordbookSize.value || form.dailyNewWords <= 0) return null
  return Math.ceil(activeWordbookSize.value / form.dailyNewWords)
})

const form = reactive<LearningProfileUpdate>({
  examTarget: 'CET4' as ExamTarget,
  examDate: null,
  dailyNewWords: 20,
  dailyMinutes: 30,
  memoryConfig: defaultMemoryConfig(),
})

const today = todayIsoDate()

function applyProfile(value: LearningProfile): void {
  profile.value = value
  if (value.examTarget) {
    form.examTarget = value.examTarget
  }
  form.examDate = value.examDate
  form.dailyNewWords = value.dailyNewWords
  form.dailyMinutes = value.dailyMinutes
  form.memoryConfig = cloneConfig(value.memoryConfig)
  const stored = (value.memoryConfig.preferences?.challenge ?? {}) as {
    practiceTypes?: string[]
    drillModes?: string[]
  }
  const keep = (list: string[] | undefined, options: readonly string[]) => {
    const filtered = (list ?? []).filter((item) => options.includes(item))
    return filtered.length ? filtered : [...options]
  }
  challengePrefs.practiceTypes = keep(stored.practiceTypes, PRACTICE_TYPE_OPTIONS.map((option) => option.key))
  challengePrefs.drillModes = keep(stored.drillModes, DRILL_MODE_OPTIONS.map((option) => option.key))
}

function cloneConfig(config: MemoryConfig): MemoryConfig {
  return {
    flashcard: { ...config.flashcard },
    choice: { ...config.choice },
    spelling: { ...config.spelling },
    preferences: { ...config.preferences },
  }
}

async function load(): Promise<void> {
  if (!frozen.value) {
    return
  }
  loading.value = true
  loadError.value = null
  try {
    applyProfile(await fetchLearningProfile())
    void loadActiveWordbook()
  } catch (error) {
    loadError.value = error
  } finally {
    loading.value = false
  }
}

async function loadActiveWordbook(): Promise<void> {
  try {
    const page = await listWordbooks({ limit: 50 })
    const active = page.items.find((item) => item.is_active) ?? page.items.find((item) => item.status === 'ready')
    activeWordbookSize.value = active ? active.entry_count : null
  } catch {
    activeWordbookSize.value = null
  }
}

async function save(): Promise<void> {
  saved.value = false
  saveError.value = null
  fieldErrors.value = validateProfile(form, today)

  if (hasFieldErrors(fieldErrors.value)) {
    return
  }
  if (!challengePrefs.practiceTypes.length || !challengePrefs.drillModes.length) {
    saveError.value = new Error('关卡生成至少要保留一种题型和一种巩固方式。')
    return
  }
  form.memoryConfig.preferences = {
    ...form.memoryConfig.preferences,
    challenge: {
      practiceTypes: [...challengePrefs.practiceTypes],
      drillModes: [...challengePrefs.drillModes],
    },
  }

  saving.value = true
  try {
    const updated = await updateLearningProfile({ ...form, memoryConfig: cloneConfig(form.memoryConfig) })
    applyProfile(updated)
    saved.value = true
    toast.success('学习设置已保存', '之后的学习目标会按新设置执行。')
  } catch (error) {
    saveError.value = error
  } finally {
    saving.value = false
  }
}

const needsOnboarding = computed(() => profile.value?.needsOnboarding === true)

onMounted(() => {
  void load()
})
</script>

<template>
  <article class="settings-page">
    <header class="settings-hero">
      <div>
        <p class="eyebrow">学习设置</p>
        <h1>学习设置</h1>
        <p class="lead">设置目标、每日学习量和记忆方式。</p>
      </div>
    </header>

    <ContractGate
      v-if="!frozen"
      :endpoints="['GET /users/me/profile', 'PATCH /users/me/profile', 'GET/PUT /memory/config']"
      title="学习设置暂时不可用"
    />

    <LoadingState v-else-if="loading" label="正在读取学习档案…" />

    <section v-else-if="loadError" class="panel">
      <ErrorNotice :error="loadError" retry-label="重新读取档案" @retry="load" />
    </section>

    <template v-else>
      <div v-if="needsOnboarding" class="alert alert-warning">
        <strong>还没有学习档案</strong>
        <p>填写目标后，明天开始按新计划学习。</p>
      </div>

      <form class="panel settings-form" novalidate @submit.prevent="save">
        <fieldset>
          <legend>每日目标</legend>
          <div class="field">
            <label for="daily-new-words">每日新词量（{{ DAILY_NEW_WORDS_MIN }}–{{ DAILY_NEW_WORDS_MAX }}）</label>
            <input
              id="daily-new-words"
              v-model.number="form.dailyNewWords"
              type="number"
              :min="DAILY_NEW_WORDS_MIN"
              :max="DAILY_NEW_WORDS_MAX"
              step="1"
              :aria-invalid="Boolean(fieldErrors.dailyNewWords)"
              :aria-describedby="fieldErrors.dailyNewWords ? 'daily-new-words-error' : undefined"
            />
            <p v-if="fieldErrors.dailyNewWords" id="daily-new-words-error" class="field-error" role="alert">
              {{ fieldErrors.dailyNewWords }}
            </p>
          </div>

          <div class="field">
            <label for="daily-minutes">每日学习时长（{{ DAILY_MINUTES_MIN }}–{{ DAILY_MINUTES_MAX }} 分钟）</label>
            <input
              id="daily-minutes"
              v-model.number="form.dailyMinutes"
              type="number"
              :min="DAILY_MINUTES_MIN"
              :max="DAILY_MINUTES_MAX"
              step="1"
              :aria-invalid="Boolean(fieldErrors.dailyMinutes)"
              :aria-describedby="fieldErrors.dailyMinutes ? 'daily-minutes-error' : undefined"
            />
            <p v-if="fieldErrors.dailyMinutes" id="daily-minutes-error" class="field-error" role="alert">
              {{ fieldErrors.dailyMinutes }}
            </p>
          </div>

          <div class="settings-goal-summary">
            <p v-if="completionDays !== null" class="inline-note">
              按每天 {{ form.dailyNewWords }} 个新词计算，当前词书约 {{ completionDays }} 天学完。
            </p>
            <p v-else class="inline-note">激活一本词书后，这里会显示预计完成天数。</p>
          </div>
        </fieldset>

        <fieldset>
          <legend>关卡生成</legend>
          <p class="field-hint">今日地图只会使用勾选的题型和巩固方式，至少各保留一项。</p>
          <div class="settings-choice-block">
            <span class="field-label">练习题型</span>
            <div class="settings-choice-grid">
              <label v-for="option in PRACTICE_TYPE_OPTIONS" :key="option.key" class="checkbox">
                <input v-model="challengePrefs.practiceTypes" type="checkbox" :value="option.key" />
                <span>{{ option.label }}</span>
              </label>
            </div>
          </div>
          <div class="settings-choice-block">
            <span class="field-label">巩固方式</span>
            <div class="settings-choice-grid">
              <label v-for="option in DRILL_MODE_OPTIONS" :key="option.key" class="checkbox">
                <input v-model="challengePrefs.drillModes" type="checkbox" :value="option.key" />
                <span>{{ option.label }}</span>
              </label>
            </div>
          </div>
        </fieldset>

        <div class="button-row">
          <button class="button" type="submit" :disabled="saving">
            {{ saving ? '正在保存…' : '保存设置' }}
          </button>
        </div>

        <div v-if="saved" class="alert alert-success" role="status">
          <strong>档案已保存</strong>
          <p>新设置从下一次计划开始生效。</p>

        </div>

        <ErrorNotice
          v-if="saveError"
          :error="saveError"
          :show-retry="false"
          retry-label="重新保存"
          @retry="save"
        />
      </form>
    </template>
  </article>
</template>
