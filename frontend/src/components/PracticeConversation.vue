<script setup lang="ts">
/**
 * The conversation practice: the guide leads, the learner answers.
 *
 * The guide is a character, not a quiz. It says its opening line, then waits;
 * whatever the learner says — typed or spoken — the guide answers it and moves
 * the talk on. The transcript is the whole exercise, so it is what gets graded.
 *
 * Voice is the browser's: speech recognition writes the learner's words into
 * the box, and speech synthesis reads the guide's lines aloud. Nothing leaves
 * the machine.
 */
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import AppIcon from './AppIcon.vue'
import SpokenText from './SpokenText.vue'
import { useRuneSurface } from '../composables/useRuneSurface'
import {
  listConversationTurns,
  postConversationTurn,
  type PracticeConversationTurn,
  type PracticeQuestion,
} from '../api/practice'
import { useSpeechRecognition } from '../composables/useSpeechRecognition'
import { useSpeechSynthesis } from '../composables/useSpeechSynthesis'

const props = defineProps<{
  sessionId: string
  question: PracticeQuestion
}>()

const emit = defineEmits<{
  (event: 'answer', value: string): void
}>()

// The brief wears the same paper as the written questions, in both themes.
const { surface } = useRuneSurface()
const composerInput = ref<HTMLTextAreaElement | null>(null)

function resizeComposerInput(): void {
  const el = composerInput.value
  if (!el) return
  el.style.height = 'auto'
  const next = Math.min(96, Math.max(24, el.scrollHeight - 2))
  el.style.height = `${next}px`
  el.style.overflowY = el.scrollHeight > next + 2 ? 'auto' : 'hidden'
}

const turns = ref<PracticeConversationTurn[]>([])
const draft = ref('')
const loading = ref(false)
const waitingForGuide = ref(false)
const error = ref<string | null>(null)
const scroller = ref<HTMLElement | null>(null)
/** Whether the talk is long enough to scroll; only then does it fade. */
const scrollable = ref(false)

const topic = computed(() => props.question.topic ?? '')
const topicZh = computed(() => props.question.topicZh ?? '')
const roleName = computed(() => props.question.role ?? '对话伙伴')
const roleZh = computed(() => props.question.roleZh ?? '')
// The brief is Chinese-only now; only the Chinese scenario is printed.
const scenarioZh = computed(() => props.question.scenarioZh ?? '')
const targetWords = computed(() => props.question.targetWords ?? [])

const canSend = computed(
  () => draft.value.trim().length > 0 && !loading.value && !waitingForGuide.value,
)

const { speak, stop: stopSpeaking } = useSpeechSynthesis()

/** Speech-to-text: the browser writes what it hears into the box. */
const dictation = useSpeechRecognition(
  (text) => {
    draft.value = draft.value.trim() ? `${draft.value.trim()} ${text}` : text
    void scrollToEnd()
  },
  // The learner is speaking English, whatever language their system is in.
  { language: 'en-US' },
)

async function scrollToEnd(): Promise<void> {
  await nextTick()
  const element = scroller.value
  if (!element) return
  scrollable.value = element.scrollHeight > element.clientHeight + 1
  element.scrollTop = element.scrollHeight
}

async function load(): Promise<void> {
  try {
    turns.value = await listConversationTurns(props.sessionId)
    await scrollToEnd()
  } catch (requestError) {
    error.value = requestError instanceof Error ? requestError.message : '对话记录读取失败。'
  }
}

watch(() => props.sessionId, () => { void load() }, { immediate: true })
watch(draft, () => { void nextTick(resizeComposerInput) })

/** A wider window can fit more of the talk, so the fade may no longer belong. */
function remeasure(): void {
  const element = scroller.value
  if (!element) return
  scrollable.value = element.scrollHeight > element.clientHeight + 1
}

onMounted(() => {
  window.addEventListener('resize', remeasure)
})

onBeforeUnmount(() => {
  window.removeEventListener('resize', remeasure)
})

/**
 * Wait for the guide to answer.
 *
 * The guide's line is written by a background job, so the first read may
 * still be empty. Polling is short and bounded: if the guide stays silent
 * the learner is told, rather than left watching a spinner.
 */
async function waitForGuide(turnId: string): Promise<void> {
  for (let attempt = 0; attempt < 30; attempt += 1) {
    await new Promise<void>((resolve) => { window.setTimeout(resolve, 900) })
    try {
      const latest = await listConversationTurns(props.sessionId)
      turns.value = latest
      const answered = latest.find((turn) => turn.id === turnId)
      if (answered && answered.line.trim()) {
        await scrollToEnd()
        speak(answered.line)
        return
      }
    } catch {
      // Keep waiting; the last error is reported below.
    }
  }
  error.value = 'AI 这次没有接上话，再试一次就好。'
}

async function send(): Promise<void> {
  const line = draft.value.trim()
  if (!line || loading.value || waitingForGuide.value) return
  loading.value = true
  error.value = null
  draft.value = ''
  stopSpeaking()
  try {
    const key =
      typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function'
        ? crypto.randomUUID()
        : `turn-${Date.now()}-${Math.random().toString(16).slice(2)}`
    const response = await postConversationTurn(props.sessionId, line, key)
    // The learner's own line shows up immediately; the guide's arrives later.
    turns.value = [
      ...turns.value,
      {
        id: `pending-${response.turn.sequence}`,
        sequence: response.turn.sequence,
        speaker: 'learner',
        line,
        lineZh: null,
        intent: null,
        createdAt: null,
      },
    ]
    emit('answer', line)
    await scrollToEnd()
    waitingForGuide.value = true
    await waitForGuide(response.turn.id)
  } catch (requestError) {
    error.value = requestError instanceof Error ? requestError.message : '这次没能把话接上。'
  } finally {
    waitingForGuide.value = false
    loading.value = false
  }
}

function speakTurn(turn: PracticeConversationTurn): void {
  if (turn.speaker === 'guide' && turn.line.trim()) speak(turn.line)
}
</script>

<template>
  <section class="practice-conversation">
    <!-- The brief is a question card like every other task: same paper, same
         header. It introduces the task in Chinese; the English lives in the
         talk itself, where it is being practised. -->
    <header
      class="practice-conversation__brief practice-question-card practice-question-card--conversation"
      :style="surface"
    >
      <div class="practice-question-card__header">
        <div class="practice-question-step">
          <span class="status-badge">口语对话</span>
        </div>
      </div>
      <h2 id="practice-conversation-title" class="practice-conversation__topic">{{ topicZh || topic }}</h2>
      <p class="practice-conversation__role">
        <AppIcon name="coach" />
        <span class="practice-conversation__role-text">
          {{ roleZh || scenarioZh || roleName }}
        </span>
      </p>
      <ul v-if="targetWords.length" class="practice-conversation__words" aria-label="本轮要用到的词">
        <li v-for="word in targetWords" :key="word">{{ word }}</li>
      </ul>
    </header>

    <section class="practice-conversation__chat">
    <div
      ref="scroller"
      class="practice-conversation__talk"
      :class="{ 'is-scrollable': scrollable }"
      aria-live="polite"
    >
      <article
        v-for="(turn, index) in turns"
        :key="turn.id"
        class="practice-conversation__turn"
        :class="`practice-conversation__turn--${turn.speaker}`"
        v-show="turn.line.trim()"
      >
        <p
          v-if="index === 0 || turns[index - 1].speaker !== turn.speaker"
          class="practice-conversation__speaker"
        >
          <span class="practice-conversation__who">{{ turn.speaker === 'guide' ? 'Hob' : '我' }}</span>
        </p>
        <div class="practice-conversation__row">
          <div class="practice-conversation__bubble">
            <SpokenText class="practice-conversation__line" :text="turn.line" :highlight="targetWords" />
            <p v-if="turn.lineZh" class="practice-conversation__zh">{{ turn.lineZh }}</p>
          </div>
          <button
            v-if="turn.speaker === 'guide' && turn.line"
            class="practice-conversation__speak"
            type="button"
            :aria-label="`朗读这句 ${turn.line}`"
            @click="speakTurn(turn)"
          >
            <AppIcon name="speaker" />
          </button>
        </div>
      </article>

      <p v-if="waitingForGuide" class="practice-conversation__waiting" role="status">
        <span class="practice-conversation__dots" aria-hidden="true"><i></i><i></i><i></i></span>
        Hob 正在想下一句…
      </p>
    </div>

    <!-- The same bar Hob answers in: one field, one round tool, one round
         send, and a hairline above the whole thing. -->
    <form class="practice-conversation__composer" @submit.prevent="send">
      <div class="practice-conversation__row-bar">
        <div class="practice-conversation__field">
          <textarea
            ref="composerInput"
            v-model="draft"
            class="practice-conversation__input"
            rows="1"
            maxlength="2000"
            placeholder="回一句…"
            aria-label="对对话伙伴说"
            @keydown.enter.exact.prevent="send"
          ></textarea>
        </div>
        <button
          v-if="dictation.supported.value"
          class="practice-conversation__tool"
          :class="{ 'is-listening': dictation.listening.value }"
          type="button"
          :aria-label="dictation.listening.value ? '停止语音输入' : '语音输入'"
          :aria-pressed="dictation.listening.value"
          :title="dictation.listening.value ? '正在听…' : '语音'"
          @click="dictation.toggle()"
        >
          <AppIcon name="speaker" />
        </button>
        <button
          class="practice-conversation__send"
          type="submit"
          :aria-label="waitingForGuide ? '等它回话…' : '说'"
          :title="waitingForGuide ? '等它回话…' : '说'"
          :disabled="!canSend"
        >
          <AppIcon name="send" />
        </button>
      </div>
      <p v-if="dictation.error.value" class="practice-conversation__error" role="status">
        {{ dictation.error.value }}
      </p>
      <p v-if="error" class="practice-conversation__error" role="alert">{{ error }}</p>
    </form>
    </section>
  </section>
</template>

<style scoped>
/* The talk is the page. Everything else — who you are talking to, the words to
   reach for, the box you type in — is furniture around it, and stays out of the
   way: one strip above, one bar below. */
.practice-conversation {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
  min-height: 0;
  width: 100%;
}

/* Two rows, top to bottom: the topic first, then the partner and the scene.
 * Side by side, a long scenario squeezed the title into a sliver. The paper
 * itself comes from the shared question-card rule. */
.practice-conversation__brief {
  display: grid;
  gap: 0.3rem;
  width: 100%;
}

/* The chat is its own card inside the question card, like Hob's composer:
   no second paper frame, just the host card with clear inner space. */
.practice-conversation__chat {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
  min-height: 26rem;
  padding: 10px 0 0;
  border: 0;
  border-top: 1px solid var(--ui-line, #ecd9bb);
  border-radius: 0;
  background: transparent;
}

html[data-theme='night'] .practice-conversation__chat {
  border-color: var(--ui-line, #3d2c66);
  background: transparent;
}

.practice-conversation__headline {
  display: flex;
  flex-wrap: wrap;
  gap: 0.2rem 0.5rem;
  align-items: baseline;
  min-width: 0;
}

.practice-conversation__topic {
  margin: 0;
  font-size: 1.15rem;
  font-weight: 800;
  line-height: 1.3;
  color: var(--ui-ink, #35240f);
}

.practice-conversation__zh {
  margin: 0;
  font-size: 0.8rem;
  color: var(--ui-muted, #7d6247);
}

.practice-conversation__role {
  display: flex;
  gap: 0.45rem;
  align-items: flex-start;
  min-width: 0;
  margin: 0;
  color: var(--ui-ink, #35240f);
}

.practice-conversation__role :deep(svg) { flex: 0 0 auto; margin-top: 0.15rem; }

.practice-conversation__role-text {
  display: block;
  min-width: 0;
  font-size: 0.82rem;
  line-height: 1.5;
}

.practice-conversation__role-text strong { font-weight: 700; }

.practice-conversation__role-text em {
  display: block;
  font-style: normal;
  color: var(--ui-muted, #7d6247);
}

.practice-conversation__words {
  display: flex;
  flex-wrap: wrap;
  gap: 0.3rem;
  margin: 0;
  padding: 0;
  list-style: none;
}

.practice-conversation__words li {
  padding: 0.1rem 0.5rem;
  border: 1px dashed var(--g-gold-edge, #d9a400);
  border-radius: 999px;
  font-size: 0.74rem;
  font-weight: 700;
  color: var(--g-orange-edge, #cf7400);
  background: var(--g-gold-soft, #fff2b8);
}

/* The talk takes every pixel the page will give it, and what has been said
   rests on the composer the way it does in every chat: `margin-top: auto` on
   the first turn rather than `justify-content: flex-end`, which would strand
   the first line of a long talk out of reach above the scroll box. */
.practice-conversation__talk > :first-child { margin-top: auto; }

.practice-conversation__talk {
  flex: 1 1 auto;
  display: flex;
  flex-direction: column;
  gap: 0.85rem;
  min-height: 0;
  padding: 0.25rem 0.15rem;
  overflow-y: auto;
}

.practice-conversation__talk.is-scrollable {
  mask-image: linear-gradient(to bottom, #000 calc(100% - 1.5rem), transparent 100%);
}

/* A turn is a column so the name sits above its own bubble, not beside it. */
.practice-conversation__turn {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
  align-items: flex-start;
  max-width: 100%;
}

.practice-conversation__row {
  display: flex;
  gap: 0.4rem;
  align-items: flex-end;
  max-width: 100%;
}

.practice-conversation__who {
  display: inline-block;
  font-size: 0.72rem;
  font-weight: 800;
  letter-spacing: 0.04em;
  color: var(--ui-muted, #7d6247);
}

.practice-conversation__bubble {
  max-width: min(38rem, 82%);
  padding: 0.65rem 0.9rem;
  border: 1px solid var(--ui-line, #ecd9bb);
  border-radius: 4px 16px 16px 16px;
  background: var(--ui-surface, #fffdf6);
}

.practice-conversation__turn--learner {
  align-items: flex-end;
}

.practice-conversation__turn--learner .practice-conversation__row {
  flex-direction: row-reverse;
}

.practice-conversation__turn--learner .practice-conversation__bubble {
  border-color: var(--g-gold-edge, #d9a400);
  border-radius: 16px 4px 16px 16px;
  background: var(--g-gold-soft, #fff2b8);
}

.practice-conversation__turn--learner .practice-conversation__who {
  color: var(--g-orange-edge, #cf7400);
}

.practice-conversation__line {
  margin: 0;
  font-size: 1rem;
  line-height: 1.6;
  color: var(--ui-ink, #35240f);
}

.practice-conversation__zh {
  margin-top: 0.25rem;
  line-height: 1.5;
}

.practice-conversation__speak {
  flex: 0 0 auto;
  display: grid;
  width: 2rem;
  height: 2rem;
  place-items: center;
  border: 1px solid var(--ui-line, #ecd9bb);
  border-radius: 50%;
  background: var(--ui-surface, #fffdf6);
  color: var(--g-orange-edge, #cf7400);
  cursor: pointer;
}

.practice-conversation__speak:hover { border-color: var(--g-orange, #ff9600); }

.practice-conversation__waiting {
  display: flex;
  gap: 0.5rem;
  align-items: center;
  margin: 0;
  font-size: 0.85rem;
  color: var(--ui-muted, #7d6247);
}

.practice-conversation__dots {
  display: inline-flex;
  gap: 0.2rem;
}

.practice-conversation__dots i {
  width: 0.4rem;
  height: 0.4rem;
  border-radius: 50%;
  background: var(--g-orange, #ff9600);
  animation: conversation-pulse 1s ease-in-out infinite alternate;
}

.practice-conversation__dots i:nth-child(2) { animation-delay: 0.18s; }
.practice-conversation__dots i:nth-child(3) { animation-delay: 0.36s; }

@keyframes conversation-pulse {
  from { opacity: 0.3; transform: translateY(0); }
  to { opacity: 1; transform: translateY(-0.2rem); }
}

/* The composer copies Hob's: one field, one round tool, one round send, all
 * sitting on a hairline that lights when you are writing. */
.practice-conversation__composer {
  display: grid;
  gap: 0.4rem;
  padding: 0;
  border: 0;
  background: none;
}

.practice-conversation__row-bar {
  display: flex;
  gap: 10px;
  align-items: flex-end;
  padding-top: 12px;
  border-top: 1px solid var(--ui-line, #ecd9bb);
  transition: border-color 200ms ease;
}

.practice-conversation__row-bar:focus-within {
  border-top-color: var(--g-orange, #ff9600);
}

/* The answer trough is the same control-field art the settings pages use. */
.practice-conversation__field {
  display: flex;
  flex: 1 1 auto;
  min-width: 0;
  padding: 4px 12px;
  border: 6px solid transparent;
  border-image: url('../assets/halloween/card/control-field-day.webp') 18% 5% fill stretch;
  background: none;
  box-shadow: none;
  transition: filter 160ms ease;
}

.practice-conversation__field:focus-within { filter: brightness(1.03); }

.practice-conversation__input {
  flex: 1 1 auto;
  min-width: 0;
  width: 100%;
  max-width: none;
  min-height: 24px;
  max-height: 96px;
  padding: 0;
  border: 0;
  background: none;
  outline: none;
  color: var(--ui-ink, #35240f);
  font: inherit;
  font-size: 1rem;
  line-height: 24px;
  resize: none;
  overflow-y: hidden;
  field-sizing: content;
}

.practice-conversation__input::placeholder { color: var(--ui-muted, #7d6247); }

.practice-conversation__tool,
.practice-conversation__send {
  display: inline-flex;
  flex: 0 0 auto;
  align-items: center;
  justify-content: center;
  width: 38px;
  height: 38px;
  border-radius: 50%;
  cursor: pointer;
  transition: color 140ms ease, border-color 140ms ease, background-color 140ms ease;
}

.practice-conversation__tool {
  border: 1px solid var(--ui-line, #ecd9bb);
  background: none;
  color: var(--ui-muted, #7d6247);
}

.practice-conversation__tool:hover:not(:disabled) {
  border-color: var(--ui-line-strong, #e0c9a4);
  background: var(--ui-surface-subtle, #fff4e2);
  color: var(--ui-ink, #35240f);
}

.practice-conversation__tool.is-listening {
  border-color: var(--g-red, #d93025);
  color: var(--g-red, #d93025);
}

.practice-conversation__send {
  border: 1px solid transparent;
  background: var(--g-orange, #ff9600);
  color: #35240f;
  box-shadow: 0 2px 0 var(--g-orange-edge, #cf7400);
}

.practice-conversation__send:hover:not(:disabled) { filter: brightness(1.06); }

.practice-conversation__send:active:not(:disabled) {
  transform: translateY(2px);
  box-shadow: 0 0 0 var(--g-orange-edge, #cf7400);
}

.practice-conversation__send:disabled {
  border-color: var(--ui-line, #ecd9bb);
  background: color-mix(in srgb, var(--ui-ink, #35240f) 8%, transparent);
  color: color-mix(in srgb, var(--ui-ink, #35240f) 40%, transparent);
  box-shadow: none;
  cursor: default;
}

.practice-conversation__tool svg,
.practice-conversation__send svg { width: 17px; height: 17px; }

.practice-conversation__error {
  margin: 0;
  font-size: 0.8rem;
  color: var(--g-red, #d93025);
}

@media (max-width: 720px) {
  .practice-conversation { min-height: 0; }
  .practice-conversation__bubble { max-width: 92%; }
}
</style>
