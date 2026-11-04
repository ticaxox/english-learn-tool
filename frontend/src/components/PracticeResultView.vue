<script setup lang="ts">
import { computed } from 'vue'
import { PRACTICE_SUBMISSION_LABELS, type PracticeQuestion, type PracticeResult } from '../api/practice'
import PracticeQuestionCard from './PracticeQuestionCard.vue'

const props = defineProps<{
  result: PracticeResult
  /** The submitted session's questions, so every result keeps its original text. */
  questions?: PracticeQuestion[]
}>()

const scoreLabel = computed(() => (props.result.score === null ? '—' : `${props.result.score} 分`))
const submittedAtLabel = computed(() => {
  if (!props.result.submittedAt) return '—'
  const date = new Date(props.result.submittedAt)
  if (Number.isNaN(date.getTime())) return '—'
  return new Intl.DateTimeFormat('zh-CN', {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  }).format(date)
})
const questionMap = computed(() => new Map((props.questions ?? []).map((question) => [question.id, question])))
const isChoiceType = (type: string): boolean => type === 'fill_blank' || type === 'reading'
</script>

<template>
  <section class="practice-result" aria-labelledby="practice-result-title">
    <div class="practice-result__layout">
    <aside class="practice-result__aside">
    <header class="practice-result__hero">
      <div>
        <p class="eyebrow">练习结果</p>
        <h2 id="practice-result-title">本次练习得分</h2>
        <p class="inline-note">{{ PRACTICE_SUBMISSION_LABELS[result.status] }} · {{ result.totalQuestions }} 题</p>
      </div>
      <div class="practice-result__score">{{ scoreLabel }}</div>
    </header>

    <section class="practice-result__summary">
      <div><strong>{{ result.correctCount ?? '—' }}</strong><span>答对</span></div>
      <div><strong>{{ result.wrongCount ?? '—' }}</strong><span>错题</span></div>
      <div><strong>{{ submittedAtLabel }}</strong><span>提交时间</span></div>
    </section>

    </aside>

    <div class="practice-result__answers">
    <p v-if="result.errorCode" class="alert alert-warning">
      <strong>评分没有完成</strong>
      <span>请稍后重试；本次结果不会显示默认分数。</span>
    </p>

    <article
      v-for="(item, index) in result.questions"
      :key="item.questionId"
      class="result-question"
    >
      <PracticeQuestionCard
        v-if="questionMap.get(item.questionId)"
        :question="questionMap.get(item.questionId)!"
        :index="index"
        :total="result.questions.length"
        :model-value="item.userAnswer"
        :review="{ selected: item.userAnswer || null, correct: item.correctChoiceId }"
      />
      <section v-else class="panel result-question-fallback">
        <p class="eyebrow">第 {{ index + 1 }} 题</p>
        <h3>你的答案：{{ item.userAnswer || '未填写' }}</h3>
      </section>

      <section class="result-explanation">
        <p v-if="!isChoiceType(item.questionType) && item.userAnswer" class="result-copy">
          <strong>你的答案：</strong>{{ item.userAnswer }}
        </p>
        <p v-if="item.correctOptionText && !questionMap.get(item.questionId)" class="result-copy">
          <strong>正确答案：</strong>{{ item.correctOptionText }}
        </p>
        <p v-if="item.referenceContent" class="result-copy">
          <strong>参考内容：</strong>{{ item.referenceContent }}
        </p>
        <p v-if="item.explanation" class="result-copy">
          <strong>解析：</strong>{{ item.explanation }}
        </p>

        <div role="list" v-if="item.dimensions.length" class="dimension-list">
          <div role="listitem" v-for="dimension in item.dimensions" :key="dimension.name">
            {{ dimension.name }}：{{ dimension.score }} / {{ dimension.maxScore }}
          </div>
        </div>
        <div role="list" v-if="item.errors.length" class="result-list result-list--error">
          <div role="listitem" v-for="error in item.errors" :key="error">{{ error }}</div>
        </div>
        <div role="list" v-if="item.suggestions.length" class="result-list">
          <div role="listitem" v-for="suggestion in item.suggestions" :key="suggestion">{{ suggestion }}</div>
        </div>
      </section>
    </article>
    </div>
    </div>
  </section>
</template>
