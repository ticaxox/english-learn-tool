<script setup lang="ts">
/**
 * Multiple-choice trainer. Options come from the server with no correctness
 * marker, so there is nothing in the DOM or in local state that reveals the
 * answer. Submitting only sends the chosen option id; the server grades.
 */
import { computed, ref, watch } from 'vue'
import type { ChoiceQuestion } from '../types/learning'

const props = defineProps<{
  question: ChoiceQuestion
  disabled?: boolean
}>()

const emit = defineEmits<{
  (event: 'answer', optionId: string): void
}>()

const selected = ref<string | null>(null)

watch(
  () => props.question.questionId,
  () => {
    selected.value = null
  },
)

const canSubmit = computed(() => selected.value !== null && !props.disabled)

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

    <h2 id="choice-prompt" class="study-card__prompt">{{ props.question.prompt }}</h2>
    <p v-if="props.question.phonetic" class="study-card__phonetic">{{ props.question.phonetic }}</p>

    <fieldset class="choice-list" :disabled="props.disabled">
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
    <p class="inline-note">提交后由服务端判分并返回解析；本页不会提前得知正确答案。</p>
  </section>
</template>
