<script setup lang="ts">
/**
 * One full-screen moment when the level changes.
 *
 * It is deliberately short and dismissible: the learner can tap anywhere to keep
 * going, and it disappears on its own after a few seconds.
 */
import { onBeforeUnmount, onMounted, ref } from 'vue'
import HobMark from './HobMark.vue'
import { illustration } from '../assets/halloween'
import { sparkBurst, gsap, motionAllowed } from '../composables/useMotion'

const props = defineProps<{ level: number; title: string }>()
const emit = defineEmits<{ close: [] }>()

const cardRef = ref<HTMLElement | null>(null)
let timer: number | null = null

onMounted(() => {
  if (cardRef.value && motionAllowed()) {
    gsap.fromTo(
      cardRef.value,
      { scale: 0.7, opacity: 0, y: 24 },
      { scale: 1, opacity: 1, y: 0, duration: 0.55, ease: 'back.out(1.7)' },
    )
  }
  sparkBurst(cardRef.value, 24)
  timer = window.setTimeout(() => emit('close'), 4200)
})

onBeforeUnmount(() => {
  if (timer !== null) window.clearTimeout(timer)
})
</script>

<template>
  <div class="levelup-backdrop" @click="emit('close')">
    <section
      ref="cardRef"
      class="levelup-card"
      role="status"
      aria-live="polite"
      aria-label="等级提升"
      @click.stop
    >
      <HobMark size="large" mood="glowing" :set="illustration.celebrate" />
      <p class="levelup-kicker">LEVEL UP</p>
      <h2>Lv.{{ props.level }}</h2>
      <p class="levelup-title">{{ props.title }}</p>
      <p class="levelup-hint">点任意处继续</p>
    </section>
  </div>
</template>
