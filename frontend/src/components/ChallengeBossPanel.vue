<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue'
import ErrorNotice from './ErrorNotice.vue'
import LoadingState from './LoadingState.vue'
import PracticeQuestionCard from './PracticeQuestionCard.vue'
import { submitChallengeBoss, type ChallengeBossAnswer, type ChallengeBossResult } from '../api/challenge'
import { usePracticeSession } from '../composables/usePracticeSession'

const props = defineProps<{
  challengeId: string
  nodeId: string
  sessionId: string
}>()

const emit = defineEmits<{ (event: 'completed', result: ChallengeBossResult): void }>()

const practice = usePracticeSession(props.sessionId)
const answers = reactive<Record<string, string>>({})
const submitting = ref(false)
const submitError = ref<unknown>(null)
const bossResult = ref<ChallengeBossResult | null>(null)
let pendingKey: string | null = null
let pendingSignature = ''

const questions = computed(() => practice.session.value?.questions ?? [])
const allAnswered = computed(() =>
  questions.value.length > 0 && questions.value.every((question) => Boolean(answers[question.id]?.trim())),
)

function newKey(): string {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') return crypto.randomUUID()
  return `boss-${Date.now()}-${Math.random().toString(16).slice(2)}`
}

function answerSignature(): string {
  return questions.value.map((question) => `${question.id}:${answers[question.id] ?? ''}`).join('|')
}

async function load(): Promise<void> {
  bossResult.value = null
  submitError.value = null
  await practice.load()
  if (practice.session.value?.draftAnswers) {
    for (const [questionId, answer] of Object.entries(practice.session.value.draftAnswers)) {
      if (!answers[questionId]) answers[questionId] = answer
    }
  }
}

async function submit(): Promise<void> {
  if (!allAnswered.value || submitting.value) return
  const signature = answerSignature()
  if (!pendingKey || pendingSignature !== signature) {
    pendingKey = newKey()
    pendingSignature = signature
  }
  submitting.value = true
  submitError.value = null
  try {
    const payload: ChallengeBossAnswer[] = questions.value.map((question) => ({
      questionId: question.id,
      answer: answers[question.id] ?? '',
    }))
    const result = await submitChallengeBoss(props.challengeId, props.nodeId, payload, pendingKey)
    bossResult.value = result
    if (result.completed) {
      pendingKey = null
      pendingSignature = ''
      emit('completed', result)
    }
  } catch (error) {
    submitError.value = error
  } finally {
    submitting.value = false
  }
}

watch(
  () => practice.session.value?.id,
  () => {
    if (practice.session.value?.draftAnswers) {
      for (const [questionId, answer] of Object.entries(practice.session.value.draftAnswers)) {
        if (!answers[questionId]) answers[questionId] = answer
      }
    }
  },
)

onMounted(() => {
  void load()
})
</script>

<template>
  <section class="challenge-boss panel" aria-labelledby="challenge-boss-title">
    <div class="challenge-boss__heading">
      <div>
        <p class="eyebrow">Final challenge</p>
        <h2 id="challenge-boss-title">终点挑战</h2>
        <p class="field-hint">固定 5–10 题；分数不会阻止当天通关，提交后不可重做。</p>
      </div>
      <span class="challenge-node__status">{{ bossResult?.status === 'completed' ? '已完成' : bossResult?.status === 'scoring' ? '正在评分' : '进行中' }}</span>
    </div>

    <LoadingState v-if="practice.loading.value || practice.generating.value" label="正在读取真实 BOSS 题目…" />
    <ErrorNotice
      v-else-if="practice.error.value"
      :error="practice.error.value"
      retry-label="重新读取 BOSS"
      @retry="load"
    />
    <div v-else-if="questions.length === 0" class="alert alert-warning">
      <strong>服务端尚未返回 BOSS 题目</strong>
      <p>页面不会生成替代题；请稍后刷新。</p>
      <button class="button-secondary" type="button" @click="load">重新读取</button>
    </div>
    <template v-else>
      <div class="challenge-boss__questions">
        <PracticeQuestionCard
          v-for="(question, index) in questions"
          :key="question.id"
          :question="question"
          :model-value="answers[question.id] ?? ''"
          :index="index"
          :total="questions.length"
          @update:model-value="answers[question.id] = $event"
        />
      </div>
      <p class="field-hint">{{ Object.values(answers).filter(Boolean).length }} / {{ questions.length }} 题已作答</p>
      <ErrorNotice v-if="submitError" :error="submitError" :show-retry="false" />
      <div v-if="bossResult" class="challenge-boss__result" aria-live="polite">
        <strong>{{ bossResult.message }}</strong>
        <p v-if="bossResult.score !== null">得分：{{ bossResult.score }}</p>
        <p v-if="bossResult.result?.question_stats" class="field-hint">
          题目统计：{{ JSON.stringify(bossResult.result.question_stats) }}
        </p>
      </div>
      <button class="button challenge-boss__submit" type="button" :disabled="!allAnswered || submitting" @click="submit">
        {{ submitting ? '正在提交…' : '提交终点挑战' }}
      </button>
    </template>
  </section>
</template>

