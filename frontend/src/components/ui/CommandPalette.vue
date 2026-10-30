<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch, type Component } from 'vue'
import { useRouter } from 'vue-router'
import {
  BookOpen,
  House,
  Layers,
  LogOut,
  Map as MapIcon,
  Search,
  Settings,
  Sparkles,
} from '@lucide/vue'
import { DialogContent, DialogOverlay, DialogPortal, DialogRoot, DialogTitle } from 'reka-ui'

const emit = defineEmits<{ coach: []; signout: [] }>()
const router = useRouter()

const open = ref(false)
const query = ref('')
const activeIndex = ref(0)
const inputRef = ref<HTMLInputElement | null>(null)

interface PaletteItem {
  id: string
  label: string
  hint: string
  keywords: string
  icon: Component
  run: () => void
}

const items = computed<PaletteItem[]>(() => [
  { id: 'today', label: '今日学习', hint: '今天的路线', keywords: 'today overview 今日 首页', icon: House, run: () => router.push('/overview') },
  { id: 'center', label: '学习中心', hint: '每日闯关地图', keywords: 'challenge map 学习中心 闯关', icon: MapIcon, run: () => router.push('/challenges') },
  { id: 'wordbooks', label: '词书', hint: '导入与切换', keywords: 'wordbook 词书 导入', icon: BookOpen, run: () => router.push('/wordbooks') },
  { id: 'memory', label: '记忆练习', hint: '翻卡 / 选择 / 拼写', keywords: 'memory 记忆 复习', icon: Layers, run: () => router.push('/memory') },
  { id: 'practice', label: 'AI 练习', hint: '生成一组练习', keywords: 'practice ai 练习', icon: Sparkles, run: () => router.push('/practice') },
  { id: 'settings', label: '设置', hint: '学习目标与 AI 配置', keywords: 'settings 设置 配置', icon: Settings, run: () => router.push('/settings/learning') },
  { id: 'coach', label: '打开 AI 教练', hint: '随时问一句', keywords: 'coach ai 教练 对话', icon: Sparkles, run: () => emit('coach') },
  { id: 'signout', label: '退出登录', hint: '结束本次使用', keywords: 'logout signout 退出', icon: LogOut, run: () => emit('signout') },
])

const filtered = computed(() => {
  const q = query.value.trim().toLowerCase()
  if (!q) return items.value
  return items.value.filter((item) =>
    `${item.label} ${item.hint} ${item.keywords}`.toLowerCase().includes(q),
  )
})

watch(filtered, () => { activeIndex.value = 0 })

function show(): void {
  open.value = true
  query.value = ''
  activeIndex.value = 0
  void nextTick(() => inputRef.value?.focus())
}

function run(item: PaletteItem | undefined): void {
  if (!item) return
  open.value = false
  item.run()
}

function onKeydown(event: KeyboardEvent): void {
  if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 'k') {
    event.preventDefault()
    if (open.value) open.value = false
    else show()
    return
  }
  if (!open.value) return
  if (event.key === 'ArrowDown') {
    event.preventDefault()
    activeIndex.value = Math.min(activeIndex.value + 1, filtered.value.length - 1)
  } else if (event.key === 'ArrowUp') {
    event.preventDefault()
    activeIndex.value = Math.max(activeIndex.value - 1, 0)
  } else if (event.key === 'Enter') {
    event.preventDefault()
    run(filtered.value[activeIndex.value])
  }
}

onMounted(() => document.addEventListener('keydown', onKeydown))
onBeforeUnmount(() => document.removeEventListener('keydown', onKeydown))

defineExpose({ show })
</script>

<template>
  <DialogRoot :open="open" @update:open="(value) => { open = value }">
    <DialogPortal>
      <DialogOverlay class="cmdk-overlay" />
      <DialogContent class="cmdk-panel" @open-auto-focus.prevent>
        <DialogTitle class="sr-only">快速跳转</DialogTitle>
        <div class="cmdk-search">
          <Search :size="18" aria-hidden="true" />
          <input
            ref="inputRef"
            v-model="query"
            class="cmdk-input"
            type="text"
            placeholder="搜索页面或操作…"
            aria-label="搜索页面或操作"
            autocomplete="off"
          />
          <kbd class="cmdk-kbd">Esc</kbd>
        </div>
        <ul class="cmdk-list" role="listbox" aria-label="可用操作">
          <li v-if="filtered.length === 0" class="cmdk-empty">没有匹配的项目</li>
          <li
            v-for="(item, index) in filtered"
            :key="item.id"
            role="option"
            :aria-selected="index === activeIndex"
          >
            <button
              class="cmdk-item"
              :class="{ 'cmdk-item--active': index === activeIndex }"
              type="button"
              @mouseenter="activeIndex = index"
              @click="run(item)"
            >
              <component :is="item.icon" :size="18" aria-hidden="true" />
              <span class="cmdk-item__label">{{ item.label }}</span>
              <span class="cmdk-item__hint">{{ item.hint }}</span>
            </button>
          </li>
        </ul>
        <footer class="cmdk-footer">
          <span><kbd>↑</kbd><kbd>↓</kbd> 选择</span>
          <span><kbd>Enter</kbd> 打开</span>
          <span><kbd>⌘K</kbd> 关闭</span>
        </footer>
      </DialogContent>
    </DialogPortal>
  </DialogRoot>
</template>
