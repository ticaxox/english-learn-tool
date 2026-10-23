<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { RouterLink } from 'vue-router'
import ErrorNotice from '../components/ErrorNotice.vue'
import NotificationStatePanel from '../components/NotificationStatePanel.vue'
import {
  fetchNotificationPreferences,
  updateNotificationPreferences,
  type NotificationCategoryPreferences,
  type NotificationPreferences,
} from '../api/notifications'
import '../notifications.css'

interface CategoryOption {
  key: keyof NotificationCategoryPreferences
  label: string
  description: string
  ai: boolean
}

const CATEGORY_OPTIONS: CategoryOption[] = [
  { key: 'dueReview', label: '到期复习', description: '有单词到达复习时间时提醒。', ai: false },
  { key: 'todayIncomplete', label: '今日任务未完成', description: '当天计划仍未完成时提醒。', ai: false },
  { key: 'streakRisk', label: '学习节奏提醒', description: '连续学习节奏可能中断时提醒。', ai: false },
  { key: 'aiCompleted', label: 'AI 任务完成', description: '练习生成或评分任务完成时提醒。', ai: true },
  { key: 'aiFailed', label: 'AI 任务失败', description: 'AI 任务未能完成时提醒。', ai: true },
  { key: 'planAdjusted', label: '学习计划调整', description: '学习计划由系统调整时提醒。', ai: true },
  { key: 'aiAction', label: 'AI 教练建议', description: 'AI 教练产生可查看建议时提醒。', ai: true },
]

const preferences = ref<NotificationPreferences | null>(null)
const draft = ref<NotificationPreferences | null>(null)
const loading = ref(true)
const loadError = ref<unknown>(null)
const saving = ref(false)
const saveError = ref<unknown>(null)
const savedMessage = ref('')
const localError = ref('')

function clonePreferences(value: NotificationPreferences): NotificationPreferences {
  return {
    categories: { ...value.categories },
    dndStart: value.dndStart,
    dndEnd: value.dndEnd,
    dailyLimit: value.dailyLimit,
    timezone: value.timezone,
  }
}

const dirty = computed(() => {
  if (!preferences.value || !draft.value) return false
  return JSON.stringify(preferences.value) !== JSON.stringify(draft.value)
})

function setCategory(key: keyof NotificationCategoryPreferences, checked: boolean): void {
  if (!draft.value) return
  draft.value.categories[key] = checked
  savedMessage.value = ''
}

function validateDraft(value: NotificationPreferences): string | null {
  if (!/^\d{2}:\d{2}$/.test(value.dndStart) || !/^\d{2}:\d{2}$/.test(value.dndEnd)) {
    return '免打扰开始和结束时间必须使用 HH:MM 格式。'
  }
  if (!Number.isInteger(value.dailyLimit) || value.dailyLimit < 0 || value.dailyLimit > 20) {
    return '每日非 AI 通知上限必须是 0 到 20 之间的整数。'
  }
  return null
}

async function load(): Promise<void> {
  loading.value = true
  loadError.value = null
  saveError.value = null
  localError.value = ''
  savedMessage.value = ''
  try {
    const result = await fetchNotificationPreferences()
    preferences.value = clonePreferences(result)
    draft.value = clonePreferences(result)
  } catch (requestError) {
    preferences.value = null
    draft.value = null
    loadError.value = requestError
  } finally {
    loading.value = false
  }
}

async function save(): Promise<void> {
  if (!draft.value || saving.value || !dirty.value) return
  localError.value = validateDraft(draft.value) ?? ''
  saveError.value = null
  savedMessage.value = ''
  if (localError.value) return

  saving.value = true
  try {
    const result = await updateNotificationPreferences(draft.value)
    preferences.value = clonePreferences(result)
    draft.value = clonePreferences(result)
    savedMessage.value = '偏好已保存，仅对后续通知生效；已经发送的历史通知不会被修改或撤回。'
  } catch (requestError) {
    saveError.value = requestError
  } finally {
    saving.value = false
  }
}

onMounted(() => {
  void load()
})
</script>

<template>
  <article class="notifications-page notification-preferences-page">
    <header class="notifications-hero notifications-hero--preferences">
      <div class="notifications-hero__copy">
        <p class="eyebrow">Moustache Rules · 通知设置</p>
        <h1>通知偏好</h1>
        <p class="lead">
          决定哪些站内提醒可以出现，以及它们何时安静下来。保存结果由服务端确认，不会用浏览器本地状态替代。
        </p>
      </div>
      <div class="notifications-hero__aside">
        <div class="notification-orbit notification-orbit--rules" aria-hidden="true">
          <span></span>
        </div>
        <RouterLink class="button-secondary" to="/notifications">返回通知中心</RouterLink>
      </div>
    </header>

    <NotificationStatePanel
      v-if="loading"
      state="loading"
      message="正在读取真实通知偏好…"
    />
    <NotificationStatePanel
      v-else-if="loadError"
      state="error"
      title="通知偏好读取失败"
      :error="loadError"
      @retry="load"
    />

    <form v-else-if="draft" class="notification-preference-layout" @submit.prevent="save">
      <section class="panel notification-preference-structure" aria-labelledby="notification-categories-title">
        <div class="section-heading">
          <div>
            <p class="eyebrow">类别开关</p>
            <h2 id="notification-categories-title">让重要提醒留下来</h2>
          </div>
          <span class="notification-channel-pill">仅站内</span>
        </div>

        <div class="notification-category-grid">
          <label
            v-for="option in CATEGORY_OPTIONS"
            :key="option.key"
            class="notification-category-option"
            :class="{ 'notification-category-option--ai': option.ai }"
          >
            <span class="notification-category-option__copy">
              <strong>{{ option.label }}</strong>
              <small>{{ option.description }}</small>
            </span>
            <input
              type="checkbox"
              :checked="draft.categories[option.key]"
              @change="setCategory(option.key, ($event.target as HTMLInputElement).checked)"
            />
            <span class="notification-switch" aria-hidden="true"><span></span></span>
          </label>
        </div>
      </section>

      <section class="panel notification-quiet-panel" aria-labelledby="notification-quiet-title">
        <div class="section-heading">
          <div>
            <p class="eyebrow">安静时段</p>
            <h2 id="notification-quiet-title">免打扰时间</h2>
          </div>
          <span class="notification-timezone">{{ draft.timezone }}</span>
        </div>

        <div class="notification-quiet-hours">
          <label>
            <span>开始</span>
            <input v-model="draft.dndStart" type="time" required />
          </label>
          <span class="notification-quiet-hours__dash" aria-hidden="true">〰</span>
          <label>
            <span>结束</span>
            <input v-model="draft.dndEnd" type="time" required />
          </label>
        </div>
        <p class="field-hint">开始与结束相同表示不启用免打扰；跨越午夜的时段会按当前时区解释。</p>

        <div class="field notification-daily-limit">
          <label for="notification-daily-limit">每日非 AI 通知上限</label>
          <input
            id="notification-daily-limit"
            v-model.number="draft.dailyLimit"
            type="number"
            min="0"
            max="20"
            step="1"
            required
          />
          <p class="field-hint">范围 0–20；0 表示当天不发送非 AI 通知。AI 类别不受此上限抑制。</p>
        </div>
      </section>

      <aside class="notification-exception-note">
        <span class="notification-exception-note__mark" aria-hidden="true">AI</span>
        <div>
          <strong>AI 完成与失败例外</strong>
          <p>
            AI 完成、AI 失败、计划调整和 AI 教练建议不受免打扰与每日条数上限抑制；
            关闭对应类别仍会抑制该类通知。这里没有邮件、短信或浏览器推送开关。
          </p>
        </div>
      </aside>

      <div class="notification-save-bar">
        <div>
          <p v-if="localError" class="field-error" role="alert">{{ localError }}</p>
          <p v-else-if="savedMessage" class="alert alert-success" role="status">{{ savedMessage }}</p>
          <p v-else class="field-hint">保存只影响后续通知，不追溯修改历史记录。</p>
        </div>
        <button class="button" type="submit" :disabled="saving || !dirty">
          {{ saving ? '正在保存…' : '保存偏好' }}
        </button>
      </div>

      <ErrorNotice
        v-if="saveError"
        :error="saveError"
        :show-retry="false"
        retry-label="重新保存"
        @retry="save"
      />
    </form>
  </article>
</template>
