<script setup lang="ts">
/**
 * /practice/records/:recordId — one submitted practice, read back whole.
 *
 * The list carries summaries only, so the questions and the answers live on
 * this page: what was asked, what the learner answered, what was right, and
 * why. `from=mistakes` keeps the way back pointing at the mistake book.
 */
import { computed, ref, watch } from 'vue'
import { RouterLink, useRoute } from 'vue-router'
import ErrorNotice from '../components/ErrorNotice.vue'
import LoadingState from '../components/LoadingState.vue'
import PracticeResultView from '../components/PracticeResultView.vue'
import TypeMark from '../components/TypeMark.vue'
import AppIcon from '../components/AppIcon.vue'
import {
  getPracticeRecord,
  PRACTICE_SOURCE_LABELS,
  PRACTICE_TYPE_LABELS,
  type PracticeRecordDetail,
} from '../api/practice'
import '../practice.css'

const route = useRoute()

const record = ref<PracticeRecordDetail | null>(null)
const loading = ref(false)
const error = ref<unknown>(null)
/** A record can hold right answers too; the mistake book may want only the wrong ones. */
const onlyWrong = ref(false)

const recordId = computed(() => String(route.params.recordId ?? ''))
const fromMistakes = computed(() => route.query.from === 'mistakes')
const typeQuery = computed<Record<string, string>>(() => {
  const type = route.query.type
  const query: Record<string, string> = {}
  if (typeof type === 'string' && type) query.type = type
  return query
})
const backTarget = computed(() =>
  fromMistakes.value
    ? { name: 'practice-mistakes', query: typeQuery.value }
    : { name: 'practice-records', query: typeQuery.value },
)
const backLabel = computed(() => (fromMistakes.value ? '错题本' : '题目集'))

const hasWrongAnswers = computed(() =>
  Boolean(record.value?.result?.questions.some((item) => item.isMistake)),
)
const shownResult = computed(() => {
  const result = record.value?.result
  if (!result) return null
  if (!onlyWrong.value) return result
  return { ...result, questions: result.questions.filter((item) => item.isMistake) }
})
const shownQuestions = computed(() => {
  const questions = record.value?.questions ?? []
  if (!onlyWrong.value) return questions
  const keep = new Set(shownResult.value?.questions.map((item) => item.questionId))
  return questions.filter((question) => keep.has(question.id))
})

function formatSubmittedAt(value: string | null): string {
  if (!value) return '—'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return '—'
  return new Intl.DateTimeFormat('zh-CN', {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  }).format(date)
}

async function load(): Promise<void> {
  if (!recordId.value) return
  loading.value = true
  error.value = null
  try {
    record.value = await getPracticeRecord(recordId.value)
  } catch (requestError) {
    record.value = null
    error.value = requestError
  } finally {
    loading.value = false
  }
}

watch(
  recordId,
  () => {
    onlyWrong.value = false
    void load()
  },
  { immediate: true },
)
</script>

<template>
  <article class="practice-page practice-record-page workspace-page">
    <header class="workspace-page-header">
      <div>
        <RouterLink class="record-detail__back" :to="backTarget">
          <AppIcon name="arrow-left" /> {{ backLabel }}
        </RouterLink>
        <p class="workspace-kicker">AI 练习记录</p>
        <h1>{{ record ? `${PRACTICE_TYPE_LABELS[record.practiceType]}练习` : '练习记录' }}</h1>
        <p class="workspace-page-lead">这次练习的题目、你的作答、正确答案和解析。</p>
      </div>
    </header>

    <LoadingState v-if="loading" label="正在读取这次记录…" />
    <section v-else-if="error" class="panel">
      <ErrorNotice :error="error" retry-label="重新读取" @retry="load" />
    </section>

    <section v-else-if="record" class="record-detail" aria-label="练习记录详情">
      <header class="record-detail__head">
        <div class="record-detail__title">
          <TypeMark :type="record.practiceType" :size="30" />
          <div>
            <h2>{{ PRACTICE_TYPE_LABELS[record.practiceType] }} · {{ record.totalQuestions }} 题</h2>
            <p>
              {{ PRACTICE_SOURCE_LABELS[record.source] }} · {{ formatSubmittedAt(record.submittedAt) }}
              <template v-if="record.wrongCount"> · 错 {{ record.wrongCount }}</template>
            </p>
          </div>
        </div>
        <div class="record-detail__aside">
          <label v-if="hasWrongAnswers" class="record-detail__only-wrong">
            <input v-model="onlyWrong" type="checkbox" />
            <span>只看错题</span>
          </label>
          <p class="record-detail__score">
            <strong>{{ record.score === null ? '—' : Math.round(record.score) }}</strong><span>分</span>
          </p>
        </div>
      </header>

      <PracticeResultView v-if="shownResult" :result="shownResult" :questions="shownQuestions" />
      <p v-else class="records-empty">这次练习暂无可用结果，可能仍在评分或评分失败。</p>
    </section>
  </article>
</template>
