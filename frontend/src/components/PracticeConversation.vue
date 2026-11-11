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

const turns = ref<PracticeConversationTurn[]>([])
const draft = ref('')
const loading = ref(false)
const waitingForGuide = ref(false)
const error = ref<string | null>(null)
const scroller = ref<HTMLElement | null>(null)
/** Whether the talk is long enough to scroll; only then does it fade. */
const scrollable = ref(false)

/** The line the learner is writing right now, and the one they said before. */
const learnerLines = computed(() =>
  turns.value.filter((turn) => turn.speaker === 'learner').map((turn) => turn.line),
)

const topic = computed(() => props.question.topic ?? '')
const topicZh = computed(() => props.question.topicZh ?? '')
const roleName = computed(() => props.question.role ?? '对话伙伴')
const roleZh = computed(() => props.question.roleZh ?? '')
/**
 * The guide's short name for the bubbles.
 *
 * The role reads like a description — "a guide at the trailhead who knows the
 * mountain well" — which is right in the brief and too long above every line.
 * The name before the first dash is the name.
 */
const shortRole = computed(() => {
  const role = roleName.value
  const cut = role.split(/\s+(?:who|that|which)\s+/i)[0]
  return cut.length >= 2 && cut.length <= 24 ? cut : '对话伙伴'
})
const scenario = computed(() => props.question.scenario ?? '')
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
    <header class="practice-conversation__brief">
      <p class="practice-conversation__label">话题</p>
      <h2 class="practice-conversation__topic">{{ topic }}</h2>
      <p v-if="topicZh" class="practice-conversation__zh">{{ topicZh }}</p>
      <p class="practice-conversation__role">
        <AppIcon name="coach" />
        <span><strong>{{ roleName }}</strong><em v-if="roleZh">{{ roleZh }}</em></span>
      </p>
      <p v-if="scenario" class="practice-conversation__scenario">{{ scenario }}</p>
      <p v-if="scenarioZh" class="practice-conversation__zh">{{ scenarioZh }}</p>
      <ul v-if="targetWords.length" class="practice-conversation__words">
        <li v-for="word in targetWords" :key="word">{{ word }}</li>
      </ul>
    </header>

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
          <span class="practice-conversation__who">{{ turn.speaker === 'guide' ? shortRole : '我' }}</span>
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

      <p v-if="waitingForGuide" class="practice-conversation__waiting">
        <span class="practice-conversation__dots" aria-hidden="true"><i></i><i></i><i></i></span>
        {{ shortRole }} 正在想下一句…
      </p>
    </div>

    <form class="practice-conversation__composer" @submit.prevent="send">
      <textarea
        v-model="draft"
        class="practice-conversation__input"
        rows="2"
        maxlength="2000"
        :placeholder="'回一句…'"
        aria-label="对对话伙伴说"
        @keydown.enter.exact.prevent="send"
      ></textarea>
      <div class="practice-conversation__controls">
        <button
          v-if="dictation.supported.value"
          class="practice-conversation__mic"
          :class="{ 'is-listening': dictation.listening.value }"
          type="button"
          :aria-pressed="dictation.listening.value"
          @click="dictation.toggle()"
        >
          <AppIcon name="speaker" />
          {{ dictation.listening.value ? '正在听…' : '语音' }}
        </button>
        <button class="practice-conversation__send" type="submit" :disabled="!canSend">
          {{ waitingForGuide ? '等它回话…' : '说' }}
          <AppIcon name="send" />
        </button>
      </div>
      <p v-if="dictation.error.value" class="practice-conversation__error" role="status">
        {{ dictation.error.value }}
      </p>
      <p v-if="error" class="practice-conversation__error" role="alert">{{ error }}</p>
    </form>
  </section>
</template>

<style scoped>
.practice-conversation {
  display: grid;
  gap: 0.9rem;
}

.practice-conversation__brief {
  display: grid;
  gap: 0.3rem;
  padding: 1rem 1.1rem;
  border: 1px solid var(--ui-line, #ecd9bb);
  border-radius: 14px;
  background: var(--ui-surface-subtle, #fff4e2);
}

.practice-conversation__label {
  margin: 0;
  font-size: 0.7rem;
  font-weight: 800;
  letter-spacing: 0.14em;
  text-transform: uppercase;
  color: var(--ui-muted, #7d6247);
}

.practice-conversation__topic {
  margin: 0;
  font-size: 1.25rem;
  font-weight: 800;
  color: var(--ui-ink, #35240f);
}

.practice-conversation__zh {
  margin: 0;
  font-size: 0.85rem;
  color: var(--ui-muted, #7d6247);
}

.practice-conversation__role {
  display: flex;
  gap: 0.5rem;
  align-items: center;
  margin: 0.35rem 0 0;
  color: var(--ui-ink, #35240f);
}

.practice-conversation__role span {
  display: grid;
}

.practice-conversation__role em {
  font-style: normal;
  font-size: 0.78rem;
  color: var(--ui-muted, #7d6247);
}

.practice-conversation__scenario {
  margin: 0.2rem 0 0;
  font-size: 0.88rem;
  line-height: 1.55;
  color: var(--ui-ink, #35240f);
}

.practice-conversation__words {
  display: flex;
  flex-wrap: wrap;
  gap: 0.35rem;
  margin: 0.5rem 0 0;
  padding: 0;
  list-style: none;
}

.practice-conversation__words li {
  padding: 0.15rem 0.5rem;
  border: 1px dashed var(--g-gold-edge, #d9a400);
  border-radius: 999px;
  font-size: 0.78rem;
  font-weight: 700;
  color: var(--g-orange-edge, #cf7400);
  background: var(--g-gold-soft, #fff2b8);
}

.practice-conversation__talk {
  display: grid;
  gap: 0.7rem;
  /* The talk is one column: the guide and the learner face each other across
     it, so the two sides must not drift to the edges of a wide screen. */
  max-width: 46rem;
  /* The talk grows with the dialogue and only scrolls once it is long. */
  max-height: 32rem;
  padding: 0.35rem 0.15rem 0.6rem;
  overflow-y: auto;
}

/* The fade only belongs on a scrollable talk: on a short one it would dim
   the first line for no reason. */
.practice-conversation__talk.is-scrollable {
  mask-image: linear-gradient(to bottom, #000 calc(100% - 1.5rem), transparent 100%);
}

.practice-conversation__turn {
  display: grid;
  gap: 0.2rem;
  justify-items: start;
}

.practice-conversation__row {
  display: flex;
  gap: 0.4rem;
  align-items: flex-end;
  max-width: 100%;
}

.practice-conversation__speaker {
  margin: 0;
}

.practice-conversation__who {
  display: inline-block;
  padding: 0.1rem 0.5rem;
  border-radius: 999px;
  background: var(--ui-surface-subtle, #fff4e2);
  font-size: 0.72rem;
  font-weight: 800;
  letter-spacing: 0.04em;
  color: var(--ui-muted, #7d6247);
}

.practice-conversation__bubble {
  max-width: min(34rem, 78%);
  padding: 0.6rem 0.85rem;
  border: 1px solid var(--ui-line, #ecd9bb);
  border-radius: 4px 14px 14px 14px;
  background: var(--ui-surface, #fffdf6);
}

/* The learner talks from the other side, so the bubble leans the other way. */
.practice-conversation__turn--learner {
  justify-items: end;
}

.practice-conversation__turn--learner .practice-conversation__row {
  flex-direction: row-reverse;
}

.practice-conversation__turn--learner .practice-conversation__bubble {
  border-color: var(--g-gold-edge, #d9a400);
  border-radius: 14px 4px 14px 14px;
  background: var(--g-gold-soft, #fff2b8);
}

.practice-conversation__turn--learner .practice-conversation__speaker {
  text-align: right;
}

.practice-conversation__turn--learner .practice-conversation__who {
  background: transparent;
  color: var(--g-orange-edge, #cf7400);
}

.practice-conversation__line {
  margin: 0;
  font-size: 1rem;
  line-height: 1.6;
  color: var(--ui-ink, #35240f);
}

.practice-conversation__zh {
  margin: 0.3rem 0 0;
  font-size: 0.82rem;
  line-height: 1.5;
  color: var(--ui-muted, #7d6247);
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

.practice-conversation__speak:hover {
  border-color: var(--g-orange, #ff9600);
}

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

.practice-conversation__composer {
  display: grid;
  gap: 0.5rem;
  max-width: 46rem;
  padding: 0.75rem;
  border: 1px solid var(--ui-line, #ecd9bb);
  border-radius: 14px;
  background: var(--ui-surface-subtle, #fff4e2);
}

.practice-conversation__input {
  width: 100%;
  max-width: none;
  min-height: 3.2rem;
  padding: 0.6rem 0.75rem;
  border: 1px solid var(--ui-line, #ecd9bb);
  border-radius: 10px;
  background: var(--ui-surface, #fffdf6);
  color: var(--ui-ink, #35240f);
  font: inherit;
  line-height: 1.55;
  resize: vertical;
}

.practice-conversation__controls {
  display: flex;
  gap: 0.5rem;
  align-items: center;
  justify-content: space-between;
}

.practice-conversation__mic,
.practice-conversation__send {
  display: inline-flex;
  gap: 0.35rem;
  align-items: center;
  padding: 0.45rem 0.85rem;
  border-radius: 999px;
  border: 1px solid var(--g-gold-edge, #d9a400);
  background: var(--ui-surface, #fffdf6);
  color: var(--g-orange-edge, #cf7400);
  font: inherit;
  font-size: 0.85rem;
  font-weight: 700;
  cursor: pointer;
}

.practice-conversation__mic.is-listening {
  border-color: var(--g-red, #d93025);
  color: var(--g-red, #d93025);
  background: var(--g-red-soft, #ffe5e2);
}

.practice-conversation__send {
  border-color: var(--g-orange-edge, #cf7400);
  background: var(--g-orange, #ff9600);
  color: #35240f;
}

.practice-conversation__send:disabled {
  opacity: 0.55;
  cursor: not-allowed;
}

.practice-conversation__error {
  margin: 0;
  font-size: 0.8rem;
  color: var(--g-red, #d93025);
}
</style>
