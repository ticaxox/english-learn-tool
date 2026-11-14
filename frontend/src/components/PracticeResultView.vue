<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { type PracticeQuestion, type PracticeResult } from '../api/practice'
import PracticeQuestionCard from './PracticeQuestionCard.vue'
import { useRuneSurface } from '../composables/useRuneSurface'
import { countUp } from '../composables/useMotion'
import SpokenText from './SpokenText.vue'
import { illustration } from '../assets/halloween'
import ArtImage from './ArtImage.vue'

const props = defineProps<{
  result: PracticeResult
  /** The submitted session's questions, so every result keeps its original text. */
  questions?: PracticeQuestion[]
}>()

// The passage is its own sheet; the card rows below bind their own paper.
const { surface } = useRuneSurface()
const scoreRef = ref<HTMLElement | null>(null)
const scoreLabel = computed(() => (props.result.score === null ? '—' : `${Math.round(props.result.score)} 分`))

// The result reads as a score reveal: the number climbs instead of appearing.
onMounted(() => {
  if (props.result.score !== null) countUp(scoreRef.value, props.result.score, { suffix: ' 分' })
})
const questionMap = computed(() => new Map((props.questions ?? []).map((question) => [question.id, question])))
const isChoiceType = (type: string): boolean => type === 'fill_blank' || type === 'reading'

const isReading = computed(() => (props.questions ?? []).some((question) => question.questionType === 'reading'))
const readingArticle = computed(
  () => (props.questions ?? []).find((question) => question.questionType === 'reading' && question.article)?.article ?? '',
)
const readingArticleZh = computed(
  () => (props.questions ?? []).find((question) => question.questionType === 'reading' && question.articleZh)?.articleZh ?? '',
)
const readingWords = computed(() => [...new Set((props.questions ?? []).flatMap((question) => question.targetWords))])

// A mixed set may hold a passage whose questions share it; show the text once.
const repeatedArticles = computed(() => {
  const seen = new Set<string>()
  const repeated = new Set<string>()
  for (const question of props.questions ?? []) {
    if (!question.article) continue
    if (seen.has(question.article)) repeated.add(question.id)
    else seen.add(question.article)
  }
  return repeated
})
function hideArticle(questionId: string): boolean {
  return isReading.value || repeatedArticles.value.has(questionId)
}

const correctCount = computed(() => props.result.correctCount ?? 0)
const wrongCount = computed(() => props.result.wrongCount ?? 0)
const correctPercent = computed(() => {
  const total = correctCount.value + wrongCount.value
  return total > 0 ? Math.round((correctCount.value / total) * 100) : 0
})
</script>

<template>
  <section class="practice-result" aria-labelledby="practice-result-title">
    <section
      v-if="isReading && readingArticle"
      class="panel practice-article-panel practice-article-panel--wide"
      :style="surface"
    >
      <p class="eyebrow">阅读材料</p>
      <SpokenText class="practice-article" :text="readingArticle" :highlight="readingWords" />
      <p v-if="readingArticleZh" class="practice-translation-note practice-translation-note--article">{{ readingArticleZh }}</p>
    </section>

    <div class="practice-result__layout">
    <aside class="practice-result__aside">
    <ArtImage class="practice-result__art" :set="illustration.result" />

    <section class="panel practice-result__card">
      <h2 id="practice-result-title" class="visually-hidden">本次练习得分</h2>
      <div class="practice-result__scoreline">
        <span ref="scoreRef" class="practice-result__score">{{ scoreLabel }}</span>
        <span class="practice-result__tally">答对 {{ correctCount }} · 错题 {{ wrongCount }}</span>
      </div>
      <div
        class="practice-result__bar"
        role="img"
        :aria-label="`正确 ${correctCount} 题，错误 ${wrongCount} 题`"
      >
        <span class="practice-result__bar-fill" :style="{ width: `${correctPercent}%` }"></span>
      </div>
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
        :hide-article="hideArticle(item.questionId)"
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
