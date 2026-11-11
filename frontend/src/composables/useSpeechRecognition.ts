/**
 * Web Speech API dictation.
 *
 * Recognition stays in the browser; only the final transcript is handed back
 * to the caller as plain text. Chromium exposes it behind a webkit prefix, and
 * other browsers simply do not offer the button.
 *
 * The language defaults to the browser's, but a caller can pin it: a learner
 * practising English wants the microphone to hear English even on a Chinese
 * system.
 */
import { onBeforeUnmount, onMounted, ref } from 'vue'

interface RecognitionResult {
  isFinal: boolean
  0: { transcript: string }
}

interface RecognitionEvent {
  resultIndex: number
  results: { length: number } & Record<number, RecognitionResult>
  error?: string
}

interface RecognitionLike {
  lang: string
  interimResults: boolean
  continuous: boolean
  onresult: ((event: RecognitionEvent) => void) | null
  onerror: ((event: RecognitionEvent) => void) | null
  onend: (() => void) | null
  start: () => void
  stop: () => void
  abort: () => void
}

type RecognitionConstructor = new () => RecognitionLike

function recognitionConstructor(): RecognitionConstructor | null {
  if (typeof window === 'undefined') return null
  const scope = window as unknown as {
    SpeechRecognition?: RecognitionConstructor
    webkitSpeechRecognition?: RecognitionConstructor
  }
  return scope.SpeechRecognition ?? scope.webkitSpeechRecognition ?? null
}

export function useSpeechRecognition(
  onTranscript: (text: string) => void,
  options: { language?: string } = {},
) {
  const supported = ref(false)
  const listening = ref(false)
  const error = ref<string | null>(null)
  let recognition: RecognitionLike | null = null

  const language =
    options.language ??
    (typeof navigator !== 'undefined' && navigator.language.toLowerCase().startsWith('zh')
      ? 'zh-CN'
      : 'en-US')

  onMounted(() => {
    supported.value = recognitionConstructor() !== null
  })

  onBeforeUnmount(() => {
    recognition?.abort()
    recognition = null
  })

  function start(): void {
    const Constructor = recognitionConstructor()
    if (!Constructor || listening.value) return
    error.value = null
    const instance = new Constructor()
    instance.lang = language
    instance.interimResults = false
    instance.continuous = false
    instance.onresult = (event) => {
      let transcript = ''
      for (let index = event.resultIndex; index < event.results.length; index += 1) {
        if (event.results[index].isFinal) transcript += event.results[index][0].transcript
      }
      const text = transcript.trim()
      if (text) onTranscript(text)
    }
    instance.onerror = (event) => {
      error.value = event.error === 'not-allowed' || event.error === 'service-not-allowed'
        ? '浏览器拒绝了麦克风权限'
        : '语音识别暂时不可用'
      listening.value = false
    }
    instance.onend = () => {
      listening.value = false
    }
    recognition = instance
    listening.value = true
    try {
      instance.start()
    } catch {
      listening.value = false
      error.value = '语音识别启动失败'
    }
  }

  function stop(): void {
    recognition?.stop()
    listening.value = false
  }

  function toggle(): void {
    if (listening.value) stop()
    else start()
  }

  return { supported, listening, error, start, stop, toggle }
}
