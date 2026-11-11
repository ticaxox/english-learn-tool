/**
 * Shared reading of the learner's progress.
 *
 * One module-level state keeps the today board, the coach and the settings page
 * showing the same numbers without each fetching its own copy.
 */
import { computed, readonly, ref } from 'vue'
import { fetchProgress, type GamificationProgress } from '../api/progress'

const progress = ref<GamificationProgress | null>(null)
const loading = ref(false)
const error = ref<unknown>(null)

export type CrumboMood = 'tired' | 'normal' | 'happy' | 'glowing'

async function load(): Promise<void> {
  loading.value = true
  error.value = null
  try {
    progress.value = await fetchProgress()
  } catch (loadError) {
    error.value = loadError
  } finally {
    loading.value = false
  }
}

const crumboMood = computed<CrumboMood>(() => {
  const value = progress.value
  if (!value) return 'normal'
  if (value.streak === 0) return 'tired'
  if (value.streak >= 7) return 'glowing'
  if (value.activeToday) return 'happy'
  return 'normal'
})

export function useGamification() {
  return {
    progress: readonly(progress),
    loading: readonly(loading),
    error: readonly(error),
    crumboMood,
    load,
  }
}
