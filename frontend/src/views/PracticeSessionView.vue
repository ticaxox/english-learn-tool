<script setup lang="ts">
import { computed, onUnmounted, ref, watch } from 'vue'
import { RouterLink, useRoute } from 'vue-router'
import AppIcon from '../components/AppIcon.vue'
import ErrorNotice from '../components/ErrorNotice.vue'
import WhiskerCrumbMark from '../components/WhiskerCrumbMark.vue'
import LoadingState from '../components/LoadingState.vue'
import PracticeQuestionCard from '../components/PracticeQuestionCard.vue'
import PracticeResultView from '../components/PracticeResultView.vue'
import { usePracticeSession } from '../composables/usePracticeSession'
import { isApiError } from '../api/errors'
import {
  PRACTICE_SOURCE_LABELS,
  PRACTICE_STATUS_LABELS,
  PRACTICE_TYPE_LABELS,
  type PracticeAnswerInput,
} from '../api/practice'
import '../practice.css'

const route = useRoute()
const sessionId = String(route.params.sessionId)
const practice = usePracticeSession(sessionId)
const answers = ref<Record<string, string>>({})
const formError = ref<string | null>(null)
const draftSavedAt = ref<string | null>(null)
const hydratedKey = ref<string | null>(null)
let autosaveTimer: number | null = null
let pendingSubmitKey: string | null = null
let pendingSubmitSignature = ''
let pendingRegenerateKey: string | null = null
let hydrating = false

const session = practice.session
const result = practice.result
const questions = computed(() => session.value?.questions ?? [])
const answeredCount = computed(() => questions.value.filter((question) => (answers.value[question.id] ?? '').trim()).length)
const allAnswered = computed(() => questions.value.length > 0 && answeredCount.value === questions.value.length)
const hasAnyAnswer = computed(() => answeredCount.value > 0)
const draftConflict = computed(
  () => isApiError(practice.draftError.value) && practice.draftError.value.code === 'PRACTICE_DRAFT_VERSION_CONFLICT',
)
const canRegenerate = computed(
  () => (session.value?.status === 'ready' || session.value?.status === 'failed') && !hasAnyAnswer.value && !practice.busy.value,
)

function newKey(prefix: string): string {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') return `${prefix}-${crypto.randomUUID()}`
  return `${prefix}-${Date.now()}-${Math.random().toString(16).slice(2)}`
}

function clearAutosave(): void {
  if (autosaveTimer !== null) {
    window.clearTimeout(autosaveTimer)
    autosaveTimer = null
  }
}

function hydrate(nextKey: string): void {
  if (!session.value) return
  hydrating = true
  answers.value = { ...session.value.draftAnswers }
  hydratedKey.value = nextKey
  formError.value = null
  draftSavedAt.value = null
  queueMicrotask(() => { hydrating = false })
}

watch(
  () => session.value ? `${session.value.id}:${session.value.generationNumber}` : null,
  (key) => {
    if (key && key !== hydratedKey.value) hydrate(key)
  },
  { immediate: true },
)

watch(
  answers,
  () => {
    if (hydrating || session.value?.status !== 'ready' || draftConflict.value) return
    clearAutosave()
    autosaveTimer = window.setTimeout(() => {
      autosaveTimer = null
      void saveDraft()
    }, 900)
  },
  { deep: true },
)

async function saveDraft(): Promise<void> {
  if (!session.value || session.value.status !== 'ready') return
  const saved = await practice.saveDraft(answers.value)
  if (saved) draftSavedAt.value = saved.savedAt
}

async function retryDraftAfterConflict(): Promise<void> {
  await practice.refresh()
  hydrate(`${sessionId}:${session.value?.generationNumber ?? 0}:refresh`)
}

function answerPayload(): PracticeAnswerInput[] {
  return questions.value.map((question) => ({
    questionId: question.id,
    answer: (answers.value[question.id] ?? '').trim(),
  }))
}

async function submit(): Promise<void> {
  formError.value = null
  if (!allAnswered.value) {
    formError.value = `还有 ${questions.value.length - answeredCount.value} 题未作答。请完成全部题目后提交。`
    return
  }
  const payload = answerPayload()
  const signature = JSON.stringify(payload)
  if (!pendingSubmitKey || pendingSubmitSignature !== signature) {
    pendingSubmitKey = newKey('practice-submit')
    pendingSubmitSignature = signature
  }
  const response = await practice.submit(payload, pendingSubmitKey)
  if (response) {
    pendingSubmitKey = null
    pendingSubmitSignature = ''
  }
}

async function regenerate(): Promise<void> {
  if (!canRegenerate.value) return
  const confirmed = window.confirm('当前练习尚未作答，确定重新生成整组题目吗？旧题会由服务端标记为已替代。')
  if (!confirmed) return
  pendingRegenerateKey ??= newKey('practice-regenerate')
  await practice.regenerate(pendingRegenerateKey)
  pendingRegenerateKey = null
}

onUnmounted(clearAutosave)
void practice.load()
</script>

<template>
  <article class="practice-page practice-session-page member-practice-session-page">
    <header class="practice-session-header">
      <div>
        <p class="eyebrow">AI 练习会话</p>
        <h1>{{ session ? `${PRACTICE_TYPE_LABELS[session.practiceType]}练习` : '练习会话' }}</h1>
        <p v-if="session" class="lead">
          {{ PRACTICE_SOURCE_LABELS[session.source] }} · {{ session.questionCount }} 题 · {{ PRACTICE_STATUS_LABELS[session.status] }}
        </p>
      </div>
      <RouterLink class="button-secondary" to="/practice">返回练习中心</RouterLink>
    </header>

    <LoadingState v-if="practice.loading.value" label="正在读取练习会话…" />
    <section v-else-if="practice.error.value" class="panel">
      <ErrorNotice :error="practice.error.value" retry-label="重新读取会话" @retry="practice.refresh" />
      <RouterLink class="button" to="/practice">重新创建练习</RouterLink>
    </section>

    <template v-else-if="session">
      <section v-if="session.status === 'generating'" class="panel practice-generation-panel" aria-live="polite">
        <p class="eyebrow">真实 AI 生成中</p>
        <h2>正在生成第 {{ session.generationNumber }} 组题目</h2>
        <p>服务端任务状态：<code>{{ session.jobStatus ?? '排队中' }}</code>。页面会持续读取真实会话状态，不会展示占位题目。</p>
        <div class="practice-generation-loader" aria-hidden="true"><span></span><span></span><span></span></div>
        <p class="inline-note">生成失败时会保留服务端错误码和重试边界。</p>
      </section>

      <section v-else-if="session.status === 'failed'" class="panel">
        <p class="eyebrow">生成失败</p>
        <h2>{{ session.errorCode ?? 'AI 题目生成失败' }}</h2>
        <p>{{ session.errorMessage ?? '服务端没有返回可展示的题目。' }}</p>
        <div class="button-row">
          <button class="button" type="button" :disabled="practice.busy.value" @click="regenerate">重新生成</button>
          <RouterLink class="button-secondary" to="/practice">新建练习</RouterLink>
        </div>
      </section>

      <PracticeResultView v-else-if="result" :result="result" />

      <section v-else-if="session.status === 'submitted'" class="panel" aria-live="polite">
        <p class="eyebrow">主观题评分中</p>
        <h2>服务端正在评分，请稍候</h2>
        <p>评分完成前不会显示默认分数、参考译文或参考范文。页面会自动轮询真实结果。</p>
        <p v-if="practice.submitError.value" class="alert alert-warning">{{ String(practice.submitError.value) }}</p>
      </section>

      <template v-else-if="session.status === 'ready'">
        <div class="member-practice-session-layout">
          <div class="member-practice-workbench">
            <section class="practice-session-toolbar panel">
              <div>
                <strong>作答进度 {{ answeredCount }} / {{ questions.length }}</strong>
                <p class="inline-note">
                  <span v-if="practice.draftSaving.value">正在保存服务端草稿…</span>
                  <span v-else-if="draftSavedAt">草稿已保存：{{ draftSavedAt }}</span>
                  <span v-else>答案会以服务端草稿恢复，不使用浏览器存储。</span>
                </p>
              </div>
              <div class="button-row">
                <button class="button-secondary button-small" type="button" :disabled="practice.draftSaving.value || draftConflict" @click="saveDraft">保存草稿</button>
                <button class="button-secondary button-small" type="button" :disabled="!canRegenerate" @click="regenerate">未作答重生成</button>
              </div>
            </section>

            <section v-if="draftConflict" class="alert alert-warning" role="alert">
              <strong>草稿版本冲突</strong>
              <p>服务端草稿已被其他请求更新。当前页面不会自动覆盖最新版本，请重新读取后再编辑。</p>
              <button class="button-secondary button-small" type="button" @click="retryDraftAfterConflict">读取最新草稿</button>
            </section>
            <ErrorNotice v-else-if="practice.draftError.value" :error="practice.draftError.value" :show-retry="false" retry-label="重试" @retry="saveDraft" />

            <PracticeQuestionCard
              v-for="(question, index) in questions"
              :key="question.id"
              :question="question"
              :index="index"
              :total="questions.length"
              :model-value="answers[question.id] ?? ''"
              :disabled="practice.busy.value"
              @update:model-value="answers[question.id] = $event"
            />

            <section class="panel practice-submit-panel member-practice-submit">
              <p v-if="formError" class="field-error" role="alert">{{ formError }}</p>
              <ErrorNotice v-if="practice.submitError.value" :error="practice.submitError.value" :show-retry="false" retry-label="重试" @retry="submit" />
              <div class="button-row">
                <button class="button member-primary-button" type="button" :disabled="practice.busy.value || !allAnswered" @click="submit">
                  {{ practice.busy.value ? '正在提交…' : '提交全部答案' }} <AppIcon name="arrow" />
                </button>
                <span class="inline-note">提交后才会展示服务端返回的答案、解析、评分和参考内容。</span>
              </div>
            </section>
          </div>

          <aside class="member-practice-session-aside">
            <section class="member-session-mascot">
              <WhiskerCrumbMark size="hero" />
              <p>“Read the question once for meaning, once for clues. Then trust the sentence.”</p>
            </section>
            <section class="member-session-progress-card">
              <p class="eyebrow">LIVE PROGRESS</p>
              <strong>{{ answeredCount }} <span>/ {{ questions.length }}</span></strong>
              <div class="progress"><span :style="{ width: `${questions.length ? Math.round(answeredCount / questions.length * 100) : 0}%` }"></span></div>
              <p>{{ allAnswered ? '全部题目已作答，可以提交。' : `还有 ${questions.length - answeredCount} 题未作答。` }}</p>
            </section>
            <section class="member-session-note">
              <p class="eyebrow">REAL DRAFT STATE</p>
              <p v-if="practice.draftSaving.value">正在保存服务端草稿…</p>
              <p v-else-if="draftSavedAt">草稿已保存：{{ draftSavedAt }}</p>
              <p v-else>答案恢复和保存都走服务端草稿，不使用浏览器业务存储。</p>
              <RouterLink class="member-text-link" to="/coach">Ask Mr. Whisker for a hint <AppIcon name="arrow" /></RouterLink>
            </section>
          </aside>
        </div>
      </template>
    </template>
  </article>
</template>