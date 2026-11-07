<script setup lang="ts">
import { computed } from 'vue'
import { PRACTICE_TYPE_LABELS, type PracticeOption, type PracticeQuestion } from '../api/practice'
import OptionBadge from './OptionBadge.vue'
import SpokenText from './SpokenText.vue'

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
const optionLayout = computed<'four' | 'two' | 'one'>(() => {
  // Reading questions always give each option its own row.
  if (props.question.questionType === 'reading') return 'one'
  const longest = props.question.options.reduce((max, option) => Math.max(max, (option.text ?? '').trim().length), 0)
  if (longest <= 16) return 'four'
  if (longest <= 32) return 'two'
  return 'one'
})

const correctId = computed(() => props.review?.correct ?? null)
const selectedId = computed(() => props.review?.selected ?? props.modelValue)
const promptId = computed(() => `practice-question-${props.question.id}`)
const answerId = computed(() => `practice-answer-${props.question.id}`)

function update(value: string): void {
  emit('update:modelValue', value)
}

/** The submitted answer may arrive as an option id or as its text. */
function matches(value: string | null, option: PracticeOption): boolean {
  if (!value) return false
  return value === option.id || value === option.text
}

function optionClass(option: PracticeOption): Record<string, boolean> {
  if (!inReview.value) return {}
  const picked = matches(selectedId.value, option)
  const correct = matches(correctId.value, option)
  return {
    'practice-option--picked': picked,
    'practice-option--correct': correct,
    'practice-option--wrong': picked && !correct,
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
        </div>
      </div>
    </header>

    <div v-if="question.questionType === 'reading'" class="practice-reading">
      <template v-if="!hideArticle">
        <SpokenText v-if="question.article" class="practice-article" :text="question.article" :highlight="question.targetWords" />
        <p v-if="inReview && question.articleZh" class="practice-translation-note">{{ question.articleZh }}</p>
      </template>
      <SpokenText :id="promptId" as="h3" :text="question.prompt ?? ''" />
    </div>

    <div v-else-if="question.questionType === 'fill_blank'" class="practice-fill-blank">
      <SpokenText :id="promptId" as="h2" class="practice-sentence" :text="question.sentence ?? ''" :highlight="question.targetWords" />
      <p v-if="inReview && question.sentenceZh" class="practice-translation-note">{{ question.sentenceZh }}</p>
    </div>

    <div v-else-if="question.questionType === 'translation'" class="practice-translation">
      <SpokenText v-if="question.sourceText" class="practice-prompt-text" :text="question.sourceText" />
      <div role="list" v-if="question.requirements.length" class="practice-requirements">
        <div role="listitem" v-for="requirement in question.requirements" :key="requirement">{{ requirement }}</div>
      </div>
    </div>

    <div v-else class="practice-writing">
      <p class="practice-prompt-note">题目</p>
      <SpokenText v-if="question.prompt" class="practice-prompt-text" :text="question.prompt" />
      <p v-if="question.requirements.length" class="practice-prompt-note">要求</p>
      <div role="list" v-if="question.requirements.length" class="practice-requirements">
        <div role="listitem" v-for="requirement in question.requirements" :key="requirement">{{ requirement }}</div>
      </div>
    </div>

    <fieldset
      v-if="isChoice"
      class="practice-options"
      :class="`practice-options--${optionLayout}`"
      :disabled="disabled || inReview"
    >
      <legend class="visually-hidden">选择一个答案</legend>
      <div
        v-for="(option, optionIndex) in question.options"
        :key="option.id"
        class="practice-option-unit"
      >
        <label class="practice-option" :class="optionClass(option)">
        <input
          class="practice-option__input"
          type="radio"
          :name="`answer-${question.id}`"
          :value="option.id"
          :checked="selectedId === option.id"
          :disabled="disabled || inReview"
          @change="update(option.id)"
        />
        <OptionBadge :letter="String.fromCharCode(65 + optionIndex)" />
        <span class="practice-option__body">
          <span class="practice-option__text">{{ option.text }}</span>
        </span>
        </label>
        <small v-if="option.textZh" class="practice-option-translation">{{ option.textZh }}</small>
      </div>
    </fieldset>

    <div v-else-if="!inReview" class="field">
      <textarea
        :id="answerId"
        class="practice-answer-textarea"
        :value="modelValue"
        :disabled="disabled"
        maxlength="20000"
        :rows="question.questionType === 'translation' ? 2 : 6"
        :aria-label="`${PRACTICE_TYPE_LABELS[question.questionType]}作答`"
        @input="update(($event.target as HTMLTextAreaElement).value)"
      ></textarea>
    </div>



  </section>
</template>
