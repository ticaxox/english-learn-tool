<script setup lang="ts">
/**
 * Per-user AI quota limits.
 *
 * The numbers apply to today onwards and are enforced by the API on every
 * reservation. The unlimited switch stores -1.
 */
import { computed, onMounted, reactive, ref, watch } from 'vue'
import ErrorNotice from './ErrorNotice.vue'
import LoadingState from './LoadingState.vue'
import { fetchLearningProfile, updateAiQuotaLimits } from '../api/learning'
import { fetchPracticeUsage, type PracticeUsage } from '../api/practice'
import { updatePersonalProvider, type AiProvider } from '../api/personal-ai'
import { useToast } from '../composables/useToast'

const props = defineProps<{ providers?: AiProvider[] }>()
const emit = defineEmits<{ saved: [] }>()

const KINDS = [
  { key: 'coach_messages', label: '教练消息' },
  { key: 'question_generation', label: '题目生成' },
  { key: 'subjective_grading', label: '主观题评分' },
] as const

const usage = ref<PracticeUsage | null>(null)
const timeout = ref(120)
const values = reactive<Record<string, number>>({})
const unlimited = reactive<Record<string, boolean>>({})
const loading = ref(false)
const saving = ref(false)
const loadError = ref<unknown>(null)
const saveError = ref<unknown>(null)
const toast = useToast()

watch(
  () => props.providers,
  (list) => {
    if (list?.length) timeout.value = list[0].timeoutSeconds
  },
  { immediate: true },
)

const usageByKind = computed(() => {
  const map: Record<string, { limit: number; used: number }> = {}
  for (const quota of usage.value?.quotas ?? []) {
    map[quota.quotaKind] = { limit: quota.limit, used: quota.used }
  }
  return map
})

async function load(): Promise<void> {
  loading.value = true
  loadError.value = null
  try {
    const [profile, usagePayload] = await Promise.all([
      fetchLearningProfile(),
      fetchPracticeUsage(),
    ])
    usage.value = usagePayload
    for (const kind of KINDS) {
      const override = profile.aiQuotaLimits?.[kind.key]
      const effective = usageByKind.value[kind.key]?.limit ?? 0
      const limit = override ?? (effective >= 0 ? effective : 0)
      unlimited[kind.key] = override === -1 || limit === -1
      values[kind.key] = limit === -1 ? 0 : limit
    }
  } catch (error) {
    loadError.value = error
  } finally {
    loading.value = false
  }
}

async function save(): Promise<void> {
  if (saving.value || !usage.value) return
  const payload: Record<string, number> = {}
  for (const kind of KINDS) {
    payload[kind.key] = unlimited[kind.key]
      ? -1
      : Math.max(0, Math.min(10000, Math.round(Number(values[kind.key]) || 0)))
  }
  const timeoutSeconds = Math.round(Number(timeout.value))
  if (!Number.isInteger(timeoutSeconds) || timeoutSeconds < 1 || timeoutSeconds > 300) {
    saveError.value = new Error('生成超时必须为 1–300 秒')
    return
  }
  saving.value = true
  saveError.value = null
  try {
    await updateAiQuotaLimits(payload)
    for (const provider of props.providers ?? []) {
      await updatePersonalProvider(provider.id, { timeoutSeconds })
    }
    await load()
    emit('saved')
    toast.success('AI 配置已保存', '额度与生成超时都会从下一次请求开始生效。')
  } catch (error) {
    saveError.value = error
  } finally {
    saving.value = false
  }
}

onMounted(() => {
  void load()
})
</script>

<template>
  <section class="panel ai-quota-panel" aria-labelledby="ai-quota-title">
    <header class="ai-quota-panel__head">
      <div>
        <h3 id="ai-quota-title">AI 额度与生成配置</h3>
        <p class="field-hint">每天可用的 AI 次数；勾选「不限」后不再按次数限制。</p>
      </div>
      <DivButton class="button" type="button" :disabled="saving || loading || !usage" @click="save">
        {{ saving ? '正在保存…' : '保存' }}
      </DivButton>
    </header>

    <LoadingState v-if="loading && !usage" label="正在读取额度…" />
    <ErrorNotice v-else-if="loadError" :error="loadError" retry-label="重新读取额度" @retry="load" />

    <div v-else class="ai-quota-list" role="list" aria-label="AI 额度">
      <div v-for="kind in KINDS" :key="kind.key" role="listitem" class="ai-quota-row">
        <div class="ai-quota-row__copy">
          <strong>{{ kind.label }}</strong>
        </div>
        <div class="ai-quota-row__controls">
          <label class="ai-quota-row__unlimited">
            <input v-model="unlimited[kind.key]" type="checkbox" />
            不限
          </label>
          <span v-if="unlimited[kind.key]" class="ai-quota-unlimited">不限</span>
          <input
            v-else
            v-model.number="values[kind.key]"
            class="ai-quota-row__input"
            type="number"
            min="0"
            max="10000"
            step="1"
            :aria-label="`${kind.label}每日上限`"
          />
        </div>
        <small class="ai-quota-row__used">今日已用 {{ usageByKind[kind.key]?.used ?? 0 }} 次</small>
      </div>
    </div>

    <div class="ai-quota-global">
      <label for="global-timeout">生成超时（秒，1–300）</label>
      <input id="global-timeout" v-model.number="timeout" type="number" min="1" max="300" step="1" />
    </div>

    <ErrorNotice v-if="saveError" :error="saveError" :show-retry="false" retry-label="重试" @retry="save" />
  </section>
</template>
