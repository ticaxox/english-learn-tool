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
import ContractGate from '../components/ContractGate.vue'
import { fetchLearningProfile, updateLearningProfile } from '../api/learning'
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
  EXAM_TARGET_LABELS,
  EXAM_TARGETS,
  MEMORY_MODULES,
  MEMORY_MODULE_LABELS,
  SPELLING_BLANK_LABELS,
  type ExamTarget,
  type LearningProfile,
  type LearningProfileUpdate,
  type MemoryConfig,
  type SpellingBlankType,
} from '../types/learning'
import '../learning.css'

const frozen = computed(() => isContractFrozen())

const profile = ref<LearningProfile | null>(null)
const loading = ref(false)
const saving = ref(false)
const loadError = ref<unknown>(null)
const saveError = ref<unknown>(null)
const saved = ref(false)
const fieldErrors = ref<FieldErrors>({})

const blankTypes: SpellingBlankType[] = ['full', 'partial', 'first_letter']

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
  form.examTarget = value.examTarget
  form.examDate = value.examDate
  form.dailyNewWords = value.dailyNewWords
  form.dailyMinutes = value.dailyMinutes
  form.memoryConfig = cloneConfig(value.memoryConfig)
}

function cloneConfig(config: MemoryConfig): MemoryConfig {
  return {
    flashcard: { ...config.flashcard },
    choice: { ...config.choice },
    spelling: { ...config.spelling },
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
  } catch (error) {
    loadError.value = error
  } finally {
    loading.value = false
  }
}

async function save(): Promise<void> {
  saved.value = false
  saveError.value = null
  fieldErrors.value = validateProfile(form, today)

  if (hasFieldErrors(fieldErrors.value)) {
    return
  }

  saving.value = true
  try {
    const updated = await updateLearningProfile({ ...form, memoryConfig: cloneConfig(form.memoryConfig) })
    applyProfile(updated)
    saved.value = true
  } catch (error) {
    saveError.value = error
  } finally {
    saving.value = false
  }
}

const effectiveFrom = computed(() => profile.value?.planEffectiveFrom ?? null)
const needsOnboarding = computed(() => profile.value?.needsOnboarding === true)

onMounted(() => {
  void load()
})
</script>

<template>
  <article class="settings-page">
    <header class="settings-hero">
      <div>
        <p class="eyebrow">学习档案</p>
        <h1>目标与记忆偏好</h1>
        <p class="lead">
          档案决定每天生成多少新词与多久的学习目标。保存后新目标从次日计划生效，今天的快照不会改变。
        </p>
      </div>
    </header>

    <ContractGate
      v-if="!frozen"
      :endpoints="['GET /users/me/profile', 'PATCH /users/me/profile', 'GET/PUT /memory/config']"
      title="学习档案等待接口契约冻结"
    />

    <LoadingState v-else-if="loading" label="正在读取学习档案…" />

    <section v-else-if="loadError" class="panel">
      <ErrorNotice :error="loadError" retry-label="重新读取档案" @retry="load" />
    </section>

    <template v-else>
      <div v-if="needsOnboarding" class="alert alert-warning">
        <strong>还没有学习档案</strong>
        <p>填写下面的目标即可创建档案；服务端会据此生成明日计划。</p>
      </div>

      <form class="panel settings-form" novalidate @submit.prevent="save">
        <fieldset>
          <legend>目标考试</legend>
          <div class="field">
            <label for="exam-target">考试类型</label>
            <select id="exam-target" v-model="form.examTarget" :aria-invalid="Boolean(fieldErrors.examTarget)">
              <option v-for="target in EXAM_TARGETS" :key="target" :value="target">
                {{ EXAM_TARGET_LABELS[target] }}
              </option>
            </select>
            <p v-if="fieldErrors.examTarget" class="field-error" role="alert">{{ fieldErrors.examTarget }}</p>
          </div>

          <div class="field">
            <label for="exam-date">考试日期（可留空）</label>
            <input
              id="exam-date"
              v-model="form.examDate"
              type="date"
              :min="today"
              :aria-invalid="Boolean(fieldErrors.examDate)"
              :aria-describedby="fieldErrors.examDate ? 'exam-date-error' : undefined"
            />
            <p v-if="fieldErrors.examDate" id="exam-date-error" class="field-error" role="alert">
              {{ fieldErrors.examDate }}
            </p>
            <p v-else class="field-hint">必须晚于今天；留空表示暂不设置。</p>
          </div>
        </fieldset>

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

          <p class="inline-note">
            实际可用新词不足时，服务端会按真实数量调整并在今日页说明原因，不会补造词条。
          </p>
        </fieldset>

        <fieldset>
          <legend>记忆模块</legend>
          <p v-if="fieldErrors.memoryConfig" class="field-error" role="alert">{{ fieldErrors.memoryConfig }}</p>
          <div v-for="module in MEMORY_MODULES" :key="module" class="field field-inline">
            <label class="checkbox">
              <input v-model="form.memoryConfig[module].enabled" type="checkbox" />
              <span>{{ MEMORY_MODULE_LABELS[module] }}</span>
            </label>
            <div v-if="module === 'spelling'" class="field field-compact">
              <label :for="`blank-${module}`">挖空方式</label>
              <select
                :id="`blank-${module}`"
                :value="form.memoryConfig.spelling.blankType ?? 'full'"
                :disabled="!form.memoryConfig.spelling.enabled"
                @change="form.memoryConfig.spelling.blankType = ($event.target as HTMLSelectElement).value as SpellingBlankType"
              >
                <option v-for="blank in blankTypes" :key="blank" :value="blank">
                  {{ SPELLING_BLANK_LABELS[blank] }}
                </option>
              </select>
            </div>
          </div>
          <p class="inline-note">至少保留一种训练方式；服务端也会拒绝全部关闭的配置。</p>
        </fieldset>

        <fieldset v-if="profile && (profile.department || profile.learningGroup)">
          <legend>组织信息</legend>
          <p class="field-hint">
            部门：{{ profile.department ?? '未设置' }} · 学习小组：{{ profile.learningGroup ?? '未设置' }}
          </p>
          <p class="inline-note">组织归属由管理员维护，本页只读展示。</p>
        </fieldset>

        <div class="button-row">
          <button class="button" type="submit" :disabled="saving">
            {{ saving ? '正在保存…' : '保存档案' }}
          </button>
        </div>

        <div v-if="saved" class="alert alert-success" role="status">
          <strong>档案已保存</strong>
          <p>新目标从次日计划生效；今天的今日任务快照保持不变。</p>
          <p v-if="effectiveFrom" class="inline-note">服务端生效时间：{{ effectiveFrom }}</p>
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
