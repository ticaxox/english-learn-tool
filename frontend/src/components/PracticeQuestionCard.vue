<script setup lang="ts">
import { computed } from 'vue'
import { PRACTICE_TYPE_LABELS, type PracticeOption, type PracticeQuestion } from '../api/practice'

const props = defineProps<{
  question: PracticeQuestion
  modelValue: string
  disabled?: boolean
  index: number
  total: number
  /** The passage is rendered once above its questions. */
  hideArticle?: boolean
  /** Post-submit review: highlight the picked and the correct option. */
  review?: { selected: string | null; correct: string | null } | null
}>()

const emit = defineEmits<{
  (event: 'update:modelValue', value: string): void
}>()

const questionLabel = computed(() => `第 ${props.index + 1} 题，共 ${props.total} 题`)
const isChoice = computed(() => ['fill_blank', 'reading'].includes(props.question.questionType))
const inReview = computed(() => props.review !== null && props.review !== undefined)
const typeLabel = computed(() => PRACTICE_TYPE_LABELS[props.question.questionType] ?? '')
const longOptions = computed(() => props.question.options.some((option) => (option.text ?? '').length > 26))
const correctId = computed(() => props.review?.correct ?? null)
const selectedId = computed(() => props.review?.selected ?? props.modelValue)
const promptId = computed(() => `practice-question-${props.question.id}`)
const answerId = computed(() => `practice-answer-${props.question.id}`)

function update(value: string): void {
  emit('update:modelValue', value)
}

function optionClass(option: PracticeOption): Record<string, boolean> {
  if (!inReview.value) return {}
  return {
    'practice-option--picked': option.id === selectedId.value,
    'practice-option--correct': option.id === correctId.value,
    'practice-option--wrong': option.id === selectedId.value && option.id !== correctId.value,
  }
}
</script>

<template>
  <section class="panel practice-question-card" :aria-labelledby="promptId">
    <header class="practice-question-card__header">
      <div class="practice-question-step">
        <span class="practice-question-number">{{ String(index + 1).padStart(2, '0') }}</span>
        <div>
          <span class="status-badge">{{ questionLabel }}</span>
          <p v-if="!inReview">提交后查看答案和解析。</p>
        </div>
      </div>
      <span class="practice-question-type">{{ typeLabel }}</span>
    </header>

    <div v-if="question.questionType === 'reading'" class="practice-reading">
      <template v-if="!hideArticle">
        <p v-if="question.article" class="practice-article">{{ question.article }}</p>
        <p v-if="inReview && question.articleZh" class="practice-translation-note">{{ question.articleZh }}</p>
      </template>
      <h3 :id="promptId">{{ question.prompt }}</h3>
    </div>

    <div v-else-if="question.questionType === 'fill_blank'" class="practice-fill-blank">
      <h2 :id="promptId" class="practice-sentence">{{ question.sentence }}</h2>
      <p v-if="inReview && question.sentenceZh" class="practice-translation-note">{{ question.sentenceZh }}</p>
    </div>

    <div v-else-if="question.questionType === 'translation'" class="practice-translation">
      <p v-if="question.sourceText" class="practice-source-text">{{ question.sourceText }}</p>
      <ul v-if="question.requirements.length" class="practice-requirements">
        <li v-for="requirement in question.requirements" :key="requirement">{{ requirement }}</li>
      </ul>
    </div>

    <div v-else class="practice-writing">
      <p v-if="question.prompt" class="practice-source-text">{{ question.prompt }}</p>
      <ul v-if="question.requirements.length" class="practice-requirements">
        <li v-for="requirement in question.requirements" :key="requirement">{{ requirement }}</li>
      </ul>
    </div>

    <fieldset
      v-if="isChoice"
      class="practice-options"
      :class="{ 'practice-options--long': longOptions }"
      :disabled="disabled || inReview"
    >
      <legend class="visually-hidden">选择一个答案</legend>
      <label
        v-for="(option, optionIndex) in question.options"
        :key="option.id"
        class="practice-option"
        :class="optionClass(option)"
      >
        <input
          type="radio"
          :name="`answer-${question.id}`"
          :value="option.id"
          :checked="selectedId === option.id"
          :disabled="disabled || inReview"
          @change="update(option.id)"
        />
        <span class="practice-option__mark" aria-hidden="true">{{ String.fromCharCode(65 + optionIndex) }}</span>
        <span class="practice-option__body">
          <span class="practice-option__text">{{ option.text }}</span>
          <small v-if="inReview && option.textZh">{{ option.textZh }}</small>
        </span>
        <span v-if="inReview && option.id === correctId" class="practice-option__flag">
          {{ option.id === selectedId ? '正确 · 你的选择' : '正确' }}
        </span>
        <span
          v-else-if="inReview && option.id === selectedId"
          class="practice-option__flag practice-option__flag--wrong"
        >你的选择</span>
      </label>
    </fieldset>

    <div v-else-if="!inReview" class="field">
      <label :for="answerId">你的答案</label>
      <textarea
        :id="answerId"
        :value="modelValue"
        :disabled="disabled"
        maxlength="20000"
        rows="6"
        placeholder="请在这里作答"
        @input="update(($event.target as HTMLTextAreaElement).value)"
      ></textarea>
      <p class="field-hint">当前字数：{{ modelValue.length }} / 20000</p>
    </div>
  </section>
</template>
