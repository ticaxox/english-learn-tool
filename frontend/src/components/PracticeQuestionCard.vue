<script setup lang="ts">
import { computed } from 'vue'
import type { PracticeQuestion } from '../api/practice'

const props = defineProps<{
  question: PracticeQuestion
  modelValue: string
  disabled?: boolean
  index: number
  total: number
}>()

const emit = defineEmits<{
  (event: 'update:modelValue', value: string): void
}>()

const questionLabel = computed(() => `第 ${props.index + 1} 题，共 ${props.total} 题`)
const isChoice = computed(() => ['fill_blank', 'reading'].includes(props.question.questionType))
const promptId = computed(() => `practice-question-${props.question.id}`)
const answerId = computed(() => `practice-answer-${props.question.id}`)

function update(value: string): void {
  emit('update:modelValue', value)
}
</script>

<template>
  <section class="panel practice-question-card" :aria-labelledby="promptId">
    <header class="practice-question-card__header">
      <div class="practice-question-step">
        <span class="practice-question-number">{{ String(index + 1).padStart(2, '0') }}</span>
        <div><span class="status-badge">{{ questionLabel }}</span><p>提交后查看结果。</p></div>
      </div>
      <span class="practice-question-type">{{ question.questionType.replaceAll('_', ' ') }}</span>
    </header>

    <div v-if="question.questionType === 'reading'" class="practice-reading">
      <h2 :id="promptId">阅读材料</h2>
      <p v-if="question.article" class="practice-article">{{ question.article }}</p>
      <p v-if="question.articleZh" class="inline-note">{{ question.articleZh }}</p>
      <h3 v-if="question.prompt">{{ question.prompt }}</h3>
      <p v-if="question.sentence">{{ question.sentence }}</p>
    </div>

    <div v-else-if="question.questionType === 'fill_blank'" class="practice-fill-blank">
      <h2 :id="promptId">{{ question.prompt ?? '选择最合适的答案' }}</h2>
      <p v-if="question.sentence" class="practice-sentence">{{ question.sentence }}</p>
      <p v-if="question.sentenceZh" class="inline-note">{{ question.sentenceZh }}</p>
    </div>

    <div v-else-if="question.questionType === 'translation'" class="practice-translation">
      <h2 :id="promptId">翻译练习</h2>
      <p v-if="question.sourceText" class="practice-source-text">{{ question.sourceText }}</p>
      <p class="inline-note">
        源语言：{{ question.sourceLanguage ?? '—' }} · 目标语言：{{ question.targetLanguage ?? '—' }}
      </p>
      <ul v-if="question.requirements.length" class="practice-requirements">
        <li v-for="requirement in question.requirements" :key="requirement">{{ requirement }}</li>
      </ul>
    </div>

    <div v-else class="practice-writing">
      <h2 :id="promptId">作文练习</h2>
      <p v-if="question.prompt" class="practice-source-text">{{ question.prompt }}</p>
      <ul v-if="question.requirements.length" class="practice-requirements">
        <li v-for="requirement in question.requirements" :key="requirement">{{ requirement }}</li>
      </ul>
    </div>

    <fieldset v-if="isChoice" class="practice-options" :disabled="disabled">
      <legend class="visually-hidden">选择一个答案</legend>
      <label v-for="(option, optionIndex) in question.options" :key="option.id" class="practice-option">
        <input
          type="radio"
          :name="`answer-${question.id}`"
          :value="option.id"
          :checked="modelValue === option.id"
          @change="update(option.id)"
        />
        <span class="practice-option__mark" aria-hidden="true">{{ String.fromCharCode(65 + optionIndex) }}</span>
        <span>
          <span class="practice-option__text">{{ option.text }}</span>
          <small v-if="option.textZh">{{ option.textZh }}</small>
        </span>
      </label>
    </fieldset>

    <div v-else class="field">
      <label :for="answerId">你的答案</label>
      <textarea
        :id="answerId"
        :value="modelValue"
        :disabled="disabled"
        maxlength="20000"
        rows="8"
        placeholder="请在这里作答"
        @input="update(($event.target as HTMLTextAreaElement).value)"
      ></textarea>
      <p class="field-hint">当前字数：{{ modelValue.length }} / 20000</p>
    </div>
  </section>
</template>