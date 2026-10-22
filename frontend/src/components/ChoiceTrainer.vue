<script setup lang="ts">
/**
 * Multiple-choice trainer. Options come from the server with no correctness
 * marker, so there is nothing in the DOM or in local state that reveals the
 * answer. Submitting only sends the chosen option id; the server grades.
 */
import { computed, nextTick, ref, watch } from 'vue'
import { CHOICE_OPTION_COUNT, type ChoiceQuestion } from '../types/learning'

const props = defineProps<{
  question: ChoiceQuestion
  disabled?: boolean
}>()

const emit = defineEmits<{
  (event: 'answer', optionId: string): void
}>()

const selected = ref<string | null>(null)
const promptHeading = ref<HTMLElement | null>(null)

/**
 * Product rule: a choice question shows four distinct options. A payload that
 * breaks that rule is a contract defect, not something to paper over — a
 * duplicated option would let the learner submit a label twice, and a short list
 * would make "the answer is there" untrue. The server keeps grading either way,
 * but the UI must say the payload is wrong instead of rendering it as normal.
 */
const optionsWellFormed = computed(() => {
  const options = props.question.options
  if (options.length !== CHOICE_OPTION_COUNT) {
    return false
  }
  const ids = new Set(options.map((option) => option.optionId))
  const labels = new Set(options.map((option) => option.label.trim()))
  return ids.size === options.length && labels.size === options.length
})

watch(
  () => props.question.questionId,
  () => {
    selected.value = null
    // Focus follows the new prompt; the radios of the old card are gone, so
    // leaving focus behind would strand keyboard users.
    void nextTick(() => promptHeading.value?.focus())
  },
)

const canSubmit = computed(
  () => selected.value !== null && !props.disabled && optionsWellFormed.value,
)

function choose(optionId: string): void {
  if (props.disabled) {
    return
  }
  selected.value = optionId
}

function submit(): void {
  if (!canSubmit.value || selected.value === null) {
    return
  }
  emit('answer', selected.value)
}
</script>

<template>
  <section class="study-card" aria-labelledby="choice-prompt">
    <p class="study-card__meta">
      <span class="study-badge">选择</span>
      <span>剩余 {{ props.question.remaining }} 张</span>
    </p>

    <h2 id="choice-prompt" ref="promptHeading" class="study-card__prompt" tabindex="-1">{{ props.question.prompt }}</h2>
    <p v-if="props.question.phonetic" class="study-card__phonetic">{{ props.question.phonetic }}</p>

    <p v-if="!optionsWellFormed" class="alert alert-warning" role="alert">
      服务端返回的选项不符合「四个不重复选项」的契约（当前 {{ props.question.options.length }} 个）。
      本页不会按这份数据判分，请刷新或联系管理员；提交按钮保持不可用。
    </p>

    <fieldset v-else class="choice-list" :disabled="props.disabled" aria-describedby="choice-hint">
      <legend class="visually-hidden">选择一个答案</legend>
      <label
        v-for="(option, index) in props.question.options"
        :key="option.optionId"
        class="choice-option"
        :class="{ 'choice-option--selected': selected === option.optionId }"
      >
        <input
          type="radio"
          :name="`choice-${props.question.questionId}`"
          :value="option.optionId"
          :checked="selected === option.optionId"
          @change="choose(option.optionId)"
        />
        <span class="choice-option__index" aria-hidden="true">{{ String.fromCharCode(65 + index) }}</span>
        <span class="choice-option__label">{{ option.label }}</span>
      </label>
    </fieldset>

    <div class="button-row">
      <button class="button" type="button" :disabled="!canSubmit" @click="submit">提交答案</button>
    </div>
    <p id="choice-hint" class="inline-note">提交后由服务端判分并返回解析；本页不会提前得知正确答案。</p>
  </section>
</template>
