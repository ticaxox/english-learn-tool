/**
 * Web Speech API pronunciation.
 *
 * The browser owns voice selection and playback; this module only picks the
 * first English voice it finds and keeps one shared "speaking" flag so any
 * button can show its pressed state. Nothing is sent to the server.
 */
import { onBeforeUnmount, onMounted, ref } from 'vue'

const supported = typeof window !== 'undefined' && 'speechSynthesis' in window

const speaking = ref(false)

function englishVoice(): SpeechSynthesisVoice | null {
  if (!supported) return null
  const voices = window.speechSynthesis.getVoices()
  return voices.find((voice) => voice.lang.toLowerCase().startsWith('en') && voice.localService)
    ?? voices.find((voice) => voice.lang.toLowerCase().startsWith('en'))
    ?? null
}

export function speak(text: string, lang = 'en-US'): void {
  if (!supported || !text.trim()) return
  const synth = window.speechSynthesis
  synth.cancel()
  const utterance = new SpeechSynthesisUtterance(text)
  utterance.lang = lang
  utterance.rate = 0.9
  const voice = englishVoice()
  if (voice) utterance.voice = voice
  utterance.onstart = () => { speaking.value = true }
  utterance.onend = () => { speaking.value = false }
  utterance.onerror = () => { speaking.value = false }
  synth.speak(utterance)
}

export function stopSpeaking(): void {
  if (!supported) return
  window.speechSynthesis.cancel()
  speaking.value = false
}

export function useSpeechSynthesis() {
  // Voice lists arrive asynchronously in Chromium; re-reading on mount is enough
  // because speak() queries getVoices() at click time.
  const onVoicesChanged = (): void => { englishVoice() }

  onMounted(() => {
    if (supported) window.speechSynthesis.addEventListener?.('voiceschanged', onVoicesChanged)
  })
  onBeforeUnmount(() => {
    if (supported) window.speechSynthesis.removeEventListener?.('voiceschanged', onVoicesChanged)
  })

  return { supported, speaking, speak, stop: stopSpeaking }
}
