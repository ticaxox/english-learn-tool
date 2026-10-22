<script setup lang="ts">
import '../wordbooks.css'
import { computed, onMounted, reactive, ref } from 'vue'
import { useAuthStore } from '../stores/auth'
import {
  activateWordbook,
  canActivateWordbook,
  listWordbooks,
  type Wordbook,
  type WordbookStatus,
  type WordbookVisibility,
} from '../api/wordbooks'
import ErrorNotice from '../components/ErrorNotice.vue'
import LoadingState from '../components/LoadingState.vue'
import WordbookDeleteDialog from '../components/WordbookDeleteDialog.vue'
import WordbookDetailDialog from '../components/WordbookDetailDialog.vue'
import WordbookExportDialog from '../components/WordbookExportDialog.vue'
import WordbookImportDialog from '../components/WordbookImportDialog.vue'

const PAGE_SIZE = 12
const auth = useAuthStore()
const books = ref<Wordbook[]>([])
const loading = ref(false)
const error = ref<unknown>(null)
const nextCursor = ref<string | null>(null)
const hasMore = ref(false)
const currentCursor = ref<string | null>(null)
const cursorHistory = ref<Array<string | null>>([])
const operationMessage = ref('')
const activationError = ref<unknown>(null)
const activatingId = ref<string | null>(null)
let loadRequestId = 0

const filters = reactive({
  search: '',
  visibility: '' as WordbookVisibility | '',
})

const detailId = ref<string | null>(null)
const importOpen = ref(false)
const exportTarget = ref<Wordbook | null>(null)
const deleteTarget = ref<Wordbook | null>(null)

const activeBook = computed(() => books.value.find((book) => book.is_active) ?? null)
const organizationBooks = computed(() => books.value.filter((book) => book.visibility === 'organization'))
const privateBooks = computed(() => books.value.filter((book) => book.visibility === 'private'))
const empty = computed(() => !loading.value && !error.value && books.value.length === 0)

function statusLabel(status: WordbookStatus): string {
  return {
    importing: '导入中',
    ready: '可用',
    failed: '导入失败',
    deleting: '删除中',
  }[status]
}

function statusDescription(book: Wordbook): string {
  if (book.status === 'importing') {
    return book.import_progress === null ? '后台正在导入' : `后台导入 ${book.import_progress}%`
  }
  if (book.status === 'failed') {
    return book.import_error || '导入失败，请查看任务原因'
  }
  if (book.status === 'deleting') {
    return '后台正在清理，操作已暂停'
  }
  return `${book.entry_count.toLocaleString('zh-CN')} 个词条`
}

function formatDate(value: string): string {
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? value : date.toLocaleDateString('zh-CN')
}

async function load(cursor: string | null = null): Promise<void> {
  const requestId = ++loadRequestId
  loading.value = true
  error.value = null
  try {
    const result = await listWordbooks({
      search: filters.search,
      visibility: filters.visibility,
      cursor,
      limit: PAGE_SIZE,
    })
    if (requestId !== loadRequestId) {
      return
    }
    books.value = result.items
    nextCursor.value = result.next_cursor
    hasMore.value = result.has_more
    currentCursor.value = cursor
  } catch (requestError) {
    if (requestId !== loadRequestId) {
      return
    }
    books.value = []
    nextCursor.value = null
    hasMore.value = false
    currentCursor.value = cursor
    error.value = requestError
  } finally {
    if (requestId === loadRequestId) {
      loading.value = false
    }
  }
}

async function applyFilters(): Promise<void> {
  cursorHistory.value = []
  await load(null)
}

function setVisibility(visibility: WordbookVisibility | ''): void {
  filters.visibility = visibility
  void applyFilters()
}

async function nextPage(): Promise<void> {
  if (!nextCursor.value) {
    return
  }
  cursorHistory.value.push(currentCursor.value)
  await load(nextCursor.value)
}

async function previousPage(): Promise<void> {
  const previous = cursorHistory.value.pop()
  if (previous === undefined) {
    return
  }
  await load(previous)
}

function createKey(): string {
  return globalThis.crypto?.randomUUID?.() || `${Date.now()}-${Math.random()}`
}

const activationKeys = new Map<string, string>()

async function activate(book: Wordbook): Promise<void> {
  if (activatingId.value || !canActivateWordbook(book)) {
    return
  }
  activatingId.value = book.id
  activationError.value = null
  operationMessage.value = ''

  const key = activationKeys.get(book.id) ?? createKey()
  activationKeys.set(book.id, key)

  try {
    await activateWordbook(book.id, key)
    activationKeys.delete(book.id)
    operationMessage.value = `已将「${book.name}」设为当前主词书；旧词书和学习数据不会被清除。`
    await load(currentCursor.value)
  } catch (requestError) {
    activationError.value = requestError
  } finally {
    activatingId.value = null
  }
}

function markDeleting(wordbookId: string): void {
  const target = books.value.find((book) => book.id === wordbookId)
  if (target) {
    target.status = 'deleting'
  }
  operationMessage.value = `「${target?.name ?? '词书'}」已进入真实删除清理任务，完成前不会被提前移除。`
}

async function deletionCompleted(): Promise<void> {
  operationMessage.value = '词书清理已完成，列表已按服务端状态刷新。'
  deleteTarget.value = null
  await load(currentCursor.value)
}

async function importCompleted(): Promise<void> {
  operationMessage.value = '词书导入完成，已刷新真实词书列表。'
  await load(null)
}

function closeDeleteDialog(): void {
  const wasDeleting = Boolean(deleteTarget.value && books.value.find((book) => book.id === deleteTarget.value?.id)?.status === 'deleting')
  deleteTarget.value = null
  if (wasDeleting) {
    void load(currentCursor.value)
  }
}

onMounted(() => {
  void load()
})
</script>

<template>
  <article class="wordbooks-page">
    <header class="wordbooks-hero">
      <div>
        <p class="eyebrow">WORD SHELF · 词书工作区</p>
        <h1>把词书放进真实学习书架</h1>
        <p class="lead">查看可见词书、导入自己的学习材料、激活主词书并导出。所有权限、任务进度与清理结果都以服务端为准。</p>
      </div>
      <button type="button" @click="importOpen = true">＋ 导入词书</button>
    </header>

    <section class="wordbook-active-banner" :class="{ 'wordbook-active-banner--empty': !activeBook }">
      <div>
        <span class="wordbook-active-mark" aria-hidden="true">Aa</span>
        <div>
          <p class="eyebrow">当前主词书</p>
          <strong>{{ activeBook?.name ?? '尚未激活词书' }}</strong>
          <p>{{ activeBook ? `可用词条 ${activeBook.entry_count.toLocaleString('zh-CN')} 个` : '从下方选择一本 ready 词书，或先导入自己的词书。' }}</p>
        </div>
      </div>
      <span v-if="activeBook" class="wordbook-status wordbook-status--active">已激活</span>
    </section>

    <section class="panel wordbooks-panel">
      <div class="wordbook-toolbar">
        <div class="wordbook-tabs" role="group" aria-label="词书可见范围筛选">
          <button
            type="button"
            :class="{ 'wordbook-tab--active': filters.visibility === '' }"
            :aria-pressed="filters.visibility === ''"
            @click="setVisibility('')"
          >全部</button>
          <button
            type="button"
            :class="{ 'wordbook-tab--active': filters.visibility === 'organization' }"
            :aria-pressed="filters.visibility === 'organization'"
            @click="setVisibility('organization')"
          >组织词书</button>
          <button
            type="button"
            :class="{ 'wordbook-tab--active': filters.visibility === 'private' }"
            :aria-pressed="filters.visibility === 'private'"
            @click="setVisibility('private')"
          >我的私有</button>
        </div>

        <form class="wordbook-search" role="search" @submit.prevent="applyFilters">
          <label class="sr-only" for="wordbook-search-input">搜索词书</label>
          <input
            id="wordbook-search-input"
            v-model="filters.search"
            type="search"
            placeholder="搜索名称或描述"
            autocomplete="off"
          />
          <button class="button-secondary" type="submit" :disabled="loading">搜索</button>
        </form>

        <button class="button-secondary" type="button" :disabled="loading" @click="load(currentCursor)">
          {{ loading ? '读取中…' : '刷新' }}
        </button>
      </div>

      <p v-if="operationMessage" class="alert alert-success" role="status">{{ operationMessage }}</p>

      <LoadingState v-if="loading && books.length === 0" label="正在读取真实词书列表…" />
      <ErrorNotice v-else-if="error" :error="error" retry-label="重新读取词书" @retry="load(currentCursor)" />

      <div v-else-if="empty" class="empty-state wordbook-empty">
        <span class="wordbook-empty-mark" aria-hidden="true">Aa</span>
        <strong>当前筛选下还没有词书</strong>
        <p>你可以导入 CSV、JSON 或 TXT 创建第一本词书。空状态不会填充静态示例。</p>
        <button type="button" @click="importOpen = true">导入第一本词书</button>
      </div>

      <template v-else>
        <ErrorNotice v-if="activationError" :error="activationError" :show-retry="false" />

        <section v-if="organizationBooks.length" class="wordbook-group" aria-labelledby="organization-books-heading">
          <div class="wordbook-group-heading">
            <div>
              <p class="eyebrow">共享书架</p>
              <h2 id="organization-books-heading">组织词书</h2>
            </div>
            <span class="count-pill">{{ organizationBooks.length }} 本</span>
          </div>
          <div class="wordbook-grid">
            <article v-for="book in organizationBooks" :key="book.id" class="wordbook-card wordbook-card--organization">
              <div class="wordbook-card-topline">
                <span class="wordbook-pill wordbook-pill--organization">组织</span>
                <span class="wordbook-status" :class="`wordbook-status--${book.status}`">{{ statusLabel(book.status) }}</span>
                <span v-if="book.is_active" class="wordbook-status wordbook-status--active">当前主词书</span>
              </div>
              <h3>{{ book.name }}</h3>
              <p class="wordbook-description">{{ book.description || '暂无描述' }}</p>
              <p class="wordbook-card-meta">{{ statusDescription(book) }}<span>·</span>{{ formatDate(book.updated_at) }}</p>
              <div class="wordbook-card-actions">
                <button class="button-secondary button-small" type="button" :aria-label="`查看 ${book.name} 的词条`" @click="detailId = book.id">查看词条</button>
                <button
                  v-if="canActivateWordbook(book)"
                  type="button"
                  class="button-small"
                  :aria-label="`将 ${book.name} 设为当前主词书`"
                  :disabled="activatingId === book.id"
                  @click="activate(book)"
                >{{ activatingId === book.id ? '激活中…' : '设为主词书' }}</button>
                <button
                  v-if="book.permissions.can_export && book.status === 'ready'"
                  class="button-secondary button-small"
                  type="button"
                  :aria-label="`导出 ${book.name}`"
                  @click="exportTarget = book"
                >导出</button>
                <button
                  v-if="book.permissions.can_delete && book.status !== 'deleting'"
                  class="button-danger button-small"
                  type="button"
                  :aria-label="`删除 ${book.name}`"
                  @click="deleteTarget = book"
                >删除</button>
              </div>
            </article>
          </div>
        </section>

        <section v-if="privateBooks.length" class="wordbook-group" aria-labelledby="private-books-heading">
          <div class="wordbook-group-heading">
            <div>
              <p class="eyebrow">只属于你</p>
              <h2 id="private-books-heading">我的私有词书</h2>
            </div>
            <span class="count-pill">{{ privateBooks.length }} 本</span>
          </div>
          <div class="wordbook-grid">
            <article v-for="book in privateBooks" :key="book.id" class="wordbook-card wordbook-card--private">
              <div class="wordbook-card-topline">
                <span class="wordbook-pill wordbook-pill--private">私有</span>
                <span class="wordbook-status" :class="`wordbook-status--${book.status}`">{{ statusLabel(book.status) }}</span>
                <span v-if="book.is_active" class="wordbook-status wordbook-status--active">当前主词书</span>
              </div>
              <h3>{{ book.name }}</h3>
              <p class="wordbook-description">{{ book.description || '暂无描述' }}</p>
              <p class="wordbook-card-meta">{{ statusDescription(book) }}<span>·</span>{{ formatDate(book.updated_at) }}</p>
              <div class="wordbook-card-actions">
                <button class="button-secondary button-small" type="button" :aria-label="`查看 ${book.name} 的词条`" @click="detailId = book.id">查看词条</button>
                <button
                  v-if="canActivateWordbook(book)"
                  type="button"
                  class="button-small"
                  :aria-label="`将 ${book.name} 设为当前主词书`"
                  :disabled="activatingId === book.id"
                  @click="activate(book)"
                >{{ activatingId === book.id ? '激活中…' : '设为主词书' }}</button>
                <button
                  v-if="book.permissions.can_export && book.status === 'ready'"
                  class="button-secondary button-small"
                  type="button"
                  :aria-label="`导出 ${book.name}`"
                  @click="exportTarget = book"
                >导出</button>
                <button
                  v-if="book.permissions.can_delete && book.status !== 'deleting'"
                  class="button-danger button-small"
                  type="button"
                  :aria-label="`删除 ${book.name}`"
                  @click="deleteTarget = book"
                >删除</button>
              </div>
            </article>
          </div>
        </section>

        <div class="pagination" aria-label="词书分页">
          <button
            class="button-secondary button-small"
            type="button"
            :disabled="cursorHistory.length === 0 || loading"
            @click="previousPage"
          >上一页</button>
          <span>当前页 {{ books.length }} 本</span>
          <button
            class="button-secondary button-small"
            type="button"
            :disabled="!hasMore || !nextCursor || loading"
            @click="nextPage"
          >下一页</button>
        </div>
      </template>
    </section>

    <WordbookImportDialog
      v-if="importOpen"
      :is-admin="auth.isAdmin"
      @close="importOpen = false"
      @completed="importCompleted"
    />
    <WordbookDetailDialog v-if="detailId" :wordbook-id="detailId" @close="detailId = null" />
    <WordbookExportDialog v-if="exportTarget" :wordbook="exportTarget" @close="exportTarget = null" />
    <WordbookDeleteDialog
      v-if="deleteTarget"
      :wordbook="deleteTarget"
      @close="closeDeleteDialog"
      @started="markDeleting"
      @completed="deletionCompleted"
    />
  </article>
</template>