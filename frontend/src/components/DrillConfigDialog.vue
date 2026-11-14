<script setup lang="ts">
/**
 * 记忆题型配置：每种练习可以出示哪个面。
 *
 * 英文、中文、读音是三张可选的面，不是三张都摊在卡上。勾一项就固定出这一项；
 * 勾多项时，每张卡在勾中的面里取一个。没勾的面不会作为提示出现——在一张要你
 * 回忆中文的卡上顺手印出读音，等于把答案递到眼前。
 *
 * 配置改的是存储里的偏好，下一张卡生效，不打断当前这一轮。
 */
import { ref, watch } from 'vue'
import AppIcon from './AppIcon.vue'
import ErrorNotice from './ErrorNotice.vue'
import SvgPlateButton from './SvgPlateButton.vue'
import { fetchMemoryConfig, saveMemoryConfig } from '../api/learning'
import type { MemoryConfig, SpellingBlankType } from '../types/learning'
import '../practice.css'

const props = defineProps<{ open: boolean }>()
const emit = defineEmits<{
  (event: 'close'): void
  (event: 'saved', config: MemoryConfig): void
}>()

const SIDES = [
  { key: 'headword', label: '英文' },
  { key: 'definition', label: '中文' },
  { key: 'phonetic', label: '读音' },
] as const
type Side = (typeof SIDES)[number]['key']

const BLANK_MODES: ReadonlyArray<{ key: SpellingBlankType | null; label: string }> = [
  { key: null, label: '随机' },
  { key: 'full', label: '整词挖空' },
  { key: 'partial', label: '部分字母' },
  { key: 'first_letter', label: '只留首字母' },
  { key: 'middle', label: '中间挖空' },
]

const config = ref<MemoryConfig | null>(null)
const flashcardSides = ref<Side[]>(['definition'])
const choiceSides = ref<Side[]>(['definition'])
const spellingMode = ref<SpellingBlankType | null>(null)
const loading = ref(false)
const saving = ref(false)
const loadError = ref<unknown>(null)
const saveError = ref<unknown>(null)

function keepSides(value: unknown): Side[] {
  const list = Array.isArray(value) ? value : []
  const kept = list.filter((item): item is Side => SIDES.some((side) => side.key === item))
  return kept.length ? kept : ['definition']
}

function toggle(module: 'flashcard' | 'choice', side: Side): void {
  const current = module === 'flashcard' ? flashcardSides.value : choiceSides.value
  const next = current.includes(side) ? current.filter((item) => item !== side) : [...current, side]
  // 至少留一个面，否则这张卡没有题面。
  if (!next.length) return
  if (module === 'flashcard') flashcardSides.value = next
  else choiceSides.value = next
}

async function load(): Promise<void> {
  loading.value = true
  loadError.value = null
  saveError.value = null
  try {
    const current = await fetchMemoryConfig()
    config.value = current
    const preferences = current.preferences ?? {}
    flashcardSides.value = keepSides(preferences.flashcard_prompt_types)
    choiceSides.value = keepSides(preferences.choice_prompt_types)
    spellingMode.value = current.spelling.blankType
  } catch (error) {
    config.value = null
    loadError.value = error
  } finally {
    loading.value = false
  }
}

async function save(): Promise<void> {
  if (!config.value || saving.value) return
  saving.value = true
  saveError.value = null
  try {
    const next: MemoryConfig = {
      flashcard: { ...config.value.flashcard },
      choice: { ...config.value.choice },
      spelling: { ...config.value.spelling, blankType: spellingMode.value },
      preferences: {
        ...config.value.preferences,
        flashcard_prompt_types: [...flashcardSides.value],
        choice_prompt_types: [...choiceSides.value],
      },
    }
    const saved = await saveMemoryConfig(next)
    config.value = saved
    emit('saved', saved)
    emit('close')
  } catch (error) {
    saveError.value = error
  } finally {
    saving.value = false
  }
}

watch(
  () => props.open,
  (open) => {
    if (open) void load()
  },
)
</script>

<template>
  <div v-if="props.open" class="dialog-backdrop" @click.self="emit('close')">
    <section
      class="dialog-card practice-config-dialog drill-config"
      role="dialog"
      aria-modal="true"
      aria-labelledby="drill-config-title"
    >
      <header class="practice-config-dialog__head">
        <div>
          <h2 id="drill-config-title">记忆题型配置</h2>
          <p class="field-hint">勾选每种练习可以出示的面。勾一项就固定出这一项，勾多项时每张卡在勾中的面里取一个。</p>
        </div>
        <DivButton
          class="icon-button practice-config-dialog__close"
          type="button"
          aria-label="关闭"
          @click="emit('close')"
        >
          <AppIcon name="close" />
        </DivButton>
      </header>

      <p v-if="loading" class="field-hint">正在读取配置…</p>
      <ErrorNotice v-else-if="loadError" :error="loadError" retry-label="重新读取配置" @retry="load" />

      <div v-else class="practice-form">
        <fieldset class="drill-config__group">
          <legend>翻卡正面</legend>
          <div class="drill-config__pills">
            <DivButton
              v-for="side in SIDES"
              :key="`flashcard-${side.key}`"
              class="settings-toggle"
              :class="{ 'is-active': flashcardSides.includes(side.key) }"
              :aria-pressed="flashcardSides.includes(side.key)"
              type="button"
              @click="toggle('flashcard', side.key)"
            >
              {{ side.label }}
            </DivButton>
          </div>
          <p class="field-hint">背面永远是正面没给的那一面。</p>
        </fieldset>

        <fieldset class="drill-config__group">
          <legend>选择题干</legend>
          <div class="drill-config__pills">
            <DivButton
              v-for="side in SIDES"
              :key="`choice-${side.key}`"
              class="settings-toggle"
              :class="{ 'is-active': choiceSides.includes(side.key) }"
              :aria-pressed="choiceSides.includes(side.key)"
              type="button"
              @click="toggle('choice', side.key)"
            >
              {{ side.label }}
            </DivButton>
          </div>
          <p class="field-hint">四个选项跟着题干换：问英文选中文，问中文选英文。</p>
        </fieldset>

        <fieldset class="drill-config__group">
          <legend>拼写挖空</legend>
          <div class="drill-config__pills">
            <DivButton
              v-for="mode in BLANK_MODES"
              :key="`blank-${mode.key ?? 'random'}`"
              class="settings-toggle"
              :class="{ 'is-active': spellingMode === mode.key }"
              :aria-pressed="spellingMode === mode.key"
              type="button"
              @click="spellingMode = mode.key"
            >
              {{ mode.label }}
            </DivButton>
          </div>
        </fieldset>

        <ErrorNotice v-if="saveError" :error="saveError" :show-retry="false" retry-label="重新保存" @retry="save" />

        <div class="practice-create-footer">
          <DivButton class="button-secondary" type="button" @click="emit('close')">取消</DivButton>
          <SvgPlateButton type="button" :disabled="saving" @click="save">
            {{ saving ? '保存中…' : '保存配置' }}
          </SvgPlateButton>
        </div>
      </div>
    </section>
  </div>
</template>

<style scoped>
.drill-config__group {
  margin: 0;
  padding: 0;
  border: 0;
}

.drill-config__group legend {
  padding: 0;
  margin-bottom: 8px;
  font-size: 0.92rem;
  font-weight: 900;
  color: var(--ui-ink, #35240f);
}

.drill-config__pills {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

/* Two buttons at the foot: 取消 reads as a way out, 保存 as the one action. */
.drill-config .practice-create-footer {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
}
</style>
