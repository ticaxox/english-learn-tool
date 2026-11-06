<script setup lang="ts">
/** One speaker button for a whole word or sentence, using the Web Speech API. */
import AppIcon from './AppIcon.vue'
import { useSpeechSynthesis } from '../composables/useSpeechSynthesis'

const props = withDefaults(defineProps<{ text: string; label?: string }>(), { label: '朗读' })
const speech = useSpeechSynthesis()
</script>

<template>
  <DivButton
    v-if="speech.supported && props.text.trim()"
    class="speak-button"
    type="button"
    :aria-label="`${props.label}：${props.text}`"
    :title="`朗读 ${props.text}`"
    @click.stop="speech.speak(props.text)"
  >
    <AppIcon name="speaker" />
  </DivButton>
</template>
