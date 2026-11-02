<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { RouterLink } from 'vue-router'
import ErrorNotice from '../components/ErrorNotice.vue'
import NotificationPlainText from '../components/NotificationPlainText.vue'
import NotificationStatePanel from '../components/NotificationStatePanel.vue'
import {
  fetchUnreadNotificationCount,
  listNotifications,
  markAllNotificationsRead,
  markNotificationRead,
  NOTIFICATION_CATEGORY_LABELS,
  type NotificationItem,
} from '../api/notifications'
import '../notifications.css'

const PAGE_SIZE = 20

const notifications = ref<NotificationItem[]>([])
const nextCursor = ref<string | null>(null)
const hasMore = ref(false)
const unreadOnly = ref(false)
const loading = ref(true)
const loadingMore = ref(false)
const error = ref<unknown>(null)
const actionError = ref<unknown>(null)
const actionMessage = ref('')
const markingId = ref<string | null>(null)
const markingAll = ref(false)
const unreadCount = ref<number | null>(null)
const unreadCountError = ref<unknown>(null)

const unreadCountLabel = computed(() => {
  if (unreadCountError.value) return '未读数暂不可用'
  if (unreadCount.value === null) return '未读数读取中'
  return `${unreadCount.value} 条未读`
})

const canMarkAll = computed(() =>
  unreadCount.value !== null && unreadCount.value > 0 && !markingAll.value && !loading.value,
)

function formatDate(value: string): string {
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return new Intl.DateTimeFormat('zh-CN', {
    dateStyle: 'medium',
    timeStyle: 'short',
  }).format(date)
}

function categoryClass(category: NotificationItem['category']): string {
  return `notification-item--${category.replaceAll('_', '-')}`
}

function businessLink(item: NotificationItem): string {
  if (item.businessRefType === 'ai_job') return '/practice'
  if (item.businessRefType === 'coach_action') return '/coach'
  return '/overview'
}

function businessLinkLabel(item: NotificationItem): string {
  if (item.businessRefType === 'ai_job') return '前往 AI 练习'
  if (item.businessRefType === 'coach_action') return '查看 AI 教练'
  return '前往学习概览'
}


async function refreshUnreadCount(): Promise<void> {
  unreadCountError.value = null
  try {
    const result = await fetchUnreadNotificationCount()
    unreadCount.value = result.unreadCount
  } catch (requestError) {
    unreadCountError.value = requestError
  }
}

async function loadFirstPage(): Promise<void> {
  loading.value = true
  error.value = null
  actionError.value = null
  try {
    const page = await listNotifications({ limit: PAGE_SIZE, unreadOnly: unreadOnly.value })
    notifications.value = page.items
    nextCursor.value = page.nextCursor
    hasMore.value = page.hasMore
  } catch (requestError) {
    notifications.value = []
    nextCursor.value = null
    hasMore.value = false
    error.value = requestError
  } finally {
    loading.value = false
  }
  void refreshUnreadCount()
}

async function loadMore(): Promise<void> {
  if (!hasMore.value || !nextCursor.value || loadingMore.value) return
  loadingMore.value = true
  actionError.value = null
  try {
    const page = await listNotifications({
      limit: PAGE_SIZE,
      cursor: nextCursor.value,
      unreadOnly: unreadOnly.value,
    })
    const known = new Set(notifications.value.map((item) => item.id))
    notifications.value = [
      ...notifications.value,
      ...page.items.filter((item) => !known.has(item.id)),
    ]
    nextCursor.value = page.nextCursor
    hasMore.value = page.hasMore
  } catch (requestError) {
    actionError.value = requestError
  } finally {
    loadingMore.value = false
  }
}

async function markOneRead(item: NotificationItem): Promise<void> {
  if (item.readAt || markingId.value || markingAll.value) return
  markingId.value = item.id
  actionError.value = null
  actionMessage.value = ''
  try {
    const updated = await markNotificationRead(item.id)
    notifications.value = unreadOnly.value
      ? notifications.value.filter((candidate) => candidate.id !== updated.id)
      : notifications.value.map((candidate) => candidate.id === updated.id ? updated : candidate)
    actionMessage.value = '已标记为已读。'
    await refreshUnreadCount()
  } catch (requestError) {
    actionError.value = requestError
  } finally {
    markingId.value = null
  }
}

async function markAllRead(): Promise<void> {
  if (!canMarkAll.value) return
  markingAll.value = true
  actionError.value = null
  actionMessage.value = ''
  try {
    const result = await markAllNotificationsRead()
    actionMessage.value = result.updatedCount > 0
      ? '已将 ' + result.updatedCount + ' 条通知标为已读。'
      : '没有未读通知。'
    await loadFirstPage()
  } catch (requestError) {
    actionError.value = requestError
  } finally {
    markingAll.value = false
  }
}

watch(unreadOnly, () => {
  actionMessage.value = ''
  void loadFirstPage()
})

onMounted(() => {
  void loadFirstPage()
})
</script>

<template>
  <article class="notifications-page">
    <header class="notifications-hero">
      <div class="notifications-hero__copy">
        <p class="eyebrow">站内通知</p>
        <h1>通知中心</h1>
        <p class="lead">重要提醒都会放在这里。</p>
        <div class="notification-hero-badges" aria-label="通知摘要">
          <span class="notification-unread-pill" :class="{ 'notification-unread-pill--error': unreadCountError }">
            {{ unreadCountLabel }}
          </span>
          <span class="notification-channel-pill">仅站内</span>
        </div>
      </div>
      <div class="notifications-hero__aside">
        <div class="notification-orbit" aria-hidden="true">
          <span></span>
        </div>
        <RouterLink class="button-secondary" to="/notifications/preferences">通知偏好</RouterLink>
      </div>
    </header>

    <section class="panel notification-toolbar" aria-label="通知筛选与操作">
      <label class="notification-toggle">
        <input v-model="unreadOnly" type="checkbox" />
        <span>只看未读</span>
      </label>
      <div class="button-row">
        <DivButton class="button-secondary button-small" type="button" :disabled="loading" @click="loadFirstPage">
          刷新
        </DivButton>
        <DivButton class="button button-small" type="button" :disabled="!canMarkAll" @click="markAllRead">
          {{ markingAll ? '正在处理…' : '全部已读' }}
        </DivButton>
      </div>
    </section>

    <p v-if="actionMessage" class="alert alert-success notification-live-message" role="status" aria-live="polite">
      {{ actionMessage }}
    </p>
    <ErrorNotice
      v-if="actionError"
      :error="actionError"
      :show-retry="false"
      retry-label="重新操作"
      @retry="loadFirstPage"
    />
    <ErrorNotice
      v-if="unreadCountError && !error"
      :error="unreadCountError"
      retry-label="重新读取未读数"
      @retry="refreshUnreadCount"
    />

    <NotificationStatePanel
      v-if="loading && notifications.length === 0"
      state="loading"
      message="正在加载通知…"
    />
    <NotificationStatePanel
      v-else-if="error"
      state="error"
      title="通知读取失败"
      :error="error"
      @retry="loadFirstPage"
    />
    <NotificationStatePanel
      v-else-if="notifications.length === 0"
      state="empty"
      :title="unreadOnly ? '没有未读通知' : '通知箱暂时空着'"
      :message="unreadOnly ? '暂时没有未读通知。' : '暂时没有通知。'"
    />

    <section v-else class="notification-list" aria-label="通知列表" aria-live="polite">
      <article
        v-for="item in notifications"
        :key="item.id"
        class="notification-item"
        :class="[categoryClass(item.category), { 'notification-item--unread': !item.readAt }]"
      >
        <div class="notification-item__stamp" aria-hidden="true">
          {{ !item.readAt ? 'NEW' : '✓' }}
        </div>
        <div class="notification-item__body">
          <div class="notification-item__meta">
            <span class="notification-category">{{ NOTIFICATION_CATEGORY_LABELS[item.category] }}</span>
            <time :datetime="item.createdAt">{{ formatDate(item.createdAt) }}</time>
            <span v-if="!item.readAt" class="notification-unread-dot">未读</span>
          </div>
          <h2>{{ item.title }}</h2>
          <NotificationPlainText :text="item.body" />
          <div class="notification-item__actions">
            <RouterLink class="notification-business-link" :to="businessLink(item)">
              {{ businessLinkLabel(item) }}
            </RouterLink>
            <DivButton
              v-if="!item.readAt"
              class="button-secondary button-small"
              type="button"
              :disabled="markingId === item.id || markingAll"
              @click="markOneRead(item)"
            >
              {{ markingId === item.id ? '正在确认…' : '标记已读' }}
            </DivButton>
          </div>
        </div>
      </article>

      <div class="notification-list__footer">
        <p class="inline-note">这里只显示站内通知。</p>
        <DivButton
          v-if="hasMore"
          class="button-secondary"
          type="button"
          :disabled="loadingMore"
          @click="loadMore"
        >
          {{ loadingMore ? '正在读取下一页…' : '加载更多通知' }}
        </DivButton>
        <span v-else class="inline-note">已到通知列表末尾</span>
      </div>
    </section>
  </article>
</template>
