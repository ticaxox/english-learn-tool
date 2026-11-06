<script setup lang="ts">
/**
 * 练习页自己的顶栏：返回、题型导航、头像。
 * 点击题型进入对应的练习/生成页，不依赖应用外壳。
 */
import { computed } from 'vue'
import { useRouter } from 'vue-router'
import AppIcon from './AppIcon.vue'
import { useAuthStore } from '../stores/auth'
import { MEMORY_MODULE_LABELS, MEMORY_MODULES, type MemoryModule } from '../types/learning'
import { PRACTICE_TYPE_LABELS, type PracticeType } from '../api/practice'

const props = defineProps<{
  mode: 'memory' | 'practice'
  active?: string | null
}>()

const router = useRouter()
// The top bar also renders in unit tests without a Pinia instance.
let auth: ReturnType<typeof useAuthStore> | null = null
try {
  auth = useAuthStore()
} catch {
  auth = null
}
const displayName = computed(() => auth?.displayName || '学')
const initials = computed(() => displayName.value.trim().slice(0, 2).toUpperCase())

type TabIcon = 'cards' | 'book' | 'star' | 'arrow' | 'spark'
const memoryIcons: Record<MemoryModule, TabIcon> = {
  flashcard: 'book',
  choice: 'cards',
  spelling: 'star',
}
const practiceIcons: Record<PracticeType, TabIcon> = {
  fill_blank: 'book',
  reading: 'cards',
  translation: 'arrow',
  writing: 'spark',
  mixed: 'star',
}

const tabs = computed<Array<{ id: string; label: string; icon: TabIcon }>>(() => (
  props.mode === 'memory'
    ? MEMORY_MODULES.map((module: MemoryModule) => ({ id: module, label: MEMORY_MODULE_LABELS[module], icon: memoryIcons[module] }))
    : (['fill_blank', 'reading', 'translation', 'writing'] as PracticeType[])
      .map((type) => ({ id: type, label: PRACTICE_TYPE_LABELS[type], icon: practiceIcons[type] }))
))

function open(id: string): void {
  if (props.mode === 'memory') {
    void router.push({ name: 'memory', query: { module: id } })
    return
  }
  void router.push({ name: 'practice', query: { type: id } })
}

function openSettings(): void {
  void router.push({ name: 'settings-learning' })
}
</script>

<template>
  <header class="practice-topbar">
    <RouterLink class="practice-topbar__back" to="/practice"><AppIcon name="arrow-left" /> AI 练习</RouterLink>

    <nav class="practice-topbar__tabs" aria-label="题型导航">
      <DivButton
        v-for="tab in tabs"
        :key="tab.id"
        class="practice-topbar__tab"
        :class="[`practice-topbar__tab--${tab.id}`, { 'is-active': tab.id === active }]"
        type="button"
        :aria-current="tab.id === active ? 'page' : undefined"
        @click="open(tab.id)"
      ><AppIcon :name="tab.icon" /><span>{{ tab.label }}</span></DivButton>
    </nav>

    <DivButton
      class="practice-topbar__avatar"
      type="button"
      :aria-label="`${displayName} 的账户设置`"
      @click="openSettings"
    >{{ initials }}</DivButton>
  </header>
</template>
