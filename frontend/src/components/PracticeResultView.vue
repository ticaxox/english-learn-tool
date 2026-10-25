<script setup lang="ts">
import { computed } from 'vue'
import { PRACTICE_SUBMISSION_LABELS, PRACTICE_TYPE_LABELS, type PracticeResult } from '../api/practice'

const props = defineProps<{ result: PracticeResult }>()

const scoreLabel = computed(() => (props.result.score === null ? '—' : `${props.result.score} 分`))
</script>

<template>
  <section class="practice-result" aria-labelledby="practice-result-title">
    <header class="practice-result__hero">
      <div>
        <p class="eyebrow">练习结果</p>
        <h2 id="practice-result-title">本次练习结果</h2>
        <p class="inline-note">{{ PRACTICE_SUBMISSION_LABELS[result.status] }} · {{ result.totalQuestions }} 题</p>
      </div>
      <div class="practice-result__score">{{ scoreLabel }}</div>
    </header>

    <section class="practice-result__summary">
      <div><strong>{{ result.correctCount ?? '—' }}</strong><span>答对</span></div>
      <div><strong>{{ result.wrongCount ?? '—' }}</strong><span>错题</span></div>
      <div><strong>{{ result.submittedAt ?? '—' }}</strong><span>提交时间</span></div>
    </section>

    <p v-if="result.errorCode" class="alert alert-warning">
      <strong>评分失败</strong>
      <span>{{ result.errorMessage }}</span>
      <code>{{ result.errorCode }}</code>
    </p>

    <article v-for="(item, index) in result.questions" :key="item.questionId" class="panel result-question">
      <header class="result-question__header">
        <div>
          <p class="eyebrow">第 {{ index + 1 }} 题 · {{ PRACTICE_TYPE_LABELS[item.questionType] }}</p>
          <h3>你的答案：{{ item.userAnswer || '未填写' }}</h3>
        </div>
        <span class="status-badge" :class="item.isMistake ? 'status-badge--danger' : 'status-badge--success'">
          {{ item.isMistake ? '错题' : item.gradedCorrect === false ? '未通过' : '完成' }}
        </span>
      </header>

      <p v-if="item.score !== null" class="result-score">得分：{{ item.score }}</p>
      <p v-if="item.correctOptionText" class="alert alert-success">
        正确答案：{{ item.correctOptionText }}
        <span v-if="item.correctChoiceId" class="inline-note">（选项 {{ item.correctChoiceId }}）</span>
      </p>
      <p v-if="item.explanation" class="result-copy"><strong>解析：</strong>{{ item.explanation }}</p>
      <p v-if="item.referenceContent" class="result-copy"><strong>参考内容：</strong>{{ item.referenceContent }}</p>

      <ul v-if="item.dimensions.length" class="dimension-list">
        <li v-for="dimension in item.dimensions" :key="dimension.name">
          {{ dimension.name }}：{{ dimension.score }} / {{ dimension.maxScore }}
        </li>
      </ul>
      <ul v-if="item.errors.length" class="result-list result-list--error">
        <li v-for="error in item.errors" :key="error">{{ error }}</li>
      </ul>
      <ul v-if="item.suggestions.length" class="result-list">
        <li v-for="suggestion in item.suggestions" :key="suggestion">{{ suggestion }}</li>
      </ul>
    </article>
  </section>
</template>