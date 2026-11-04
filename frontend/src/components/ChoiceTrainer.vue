<script setup lang="ts">
/**
 * Multiple-choice trainer. Options come from the server with no correctness
 * marker, so there is nothing in the DOM or in local state that reveals the
 * answer. Submitting only sends the chosen option id; the server grades.
 */
import { computed, nextTick, ref, watch } from 'vue'
import type { ChoiceQuestion } from '../types/learning'
import OptionBadge from './OptionBadge.vue'

const props = defineProps<{
  question: ChoiceQuestion
  disabled?: boolean
}>()

const emit = defineEmits<{
  (event: 'answer', optionId: string): void
}>()

const wordOptions = computed(() => props.question.options.length > 0
  && props.question.options.every((option) => {
    const text = (option.label ?? '').trim()
    return text.length > 0 && text.length <= 18 && !text.includes(' ')
  }))

const selected = ref<string | null>(null)
const promptHeading = ref<HTMLElement | null>(null)

/**
 * `option_count` is the server's authority. Small wordbooks can legitimately
 * return fewer than four options; the UI only verifies that the declared count
 * matches the rendered labels and that labels are non-empty and distinct.
 */
const optionsWellFormed = computed(() => {
  const options = props.question.options
  if (props.question.optionCount < 1 || options.length !== props.question.optionCount) {
    return false
  }
  const ids = new Set(options.map((option) => option.optionId))
  const labels = new Set(options.map((option) => option.label.trim()))
  return labels.size === options.length && !labels.has('') && ids.size === options.length
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

function choose(optionId: string): void {
  if (props.disabled || !optionsWellFormed.value) {
    return
  }
  // Choosing is the answer: no separate submit step.
  selected.value = optionId
  emit('answer', optionId)
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
      选项暂时不可用，请稍后重试。
      本页不会按这份数据判分，请刷新或联系管理员；提交按钮保持不可用。
    </p>

    <fieldset v-else class="choice-list" :class="{ 'choice-list--words': wordOptions }" :disabled="props.disabled">
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
        <OptionBadge :letter="String.fromCharCode(65 + index)" />
        <span class="choice-option__label">{{ option.label }}</span>
      </label>
    </fieldset>
  </section>
</template>
