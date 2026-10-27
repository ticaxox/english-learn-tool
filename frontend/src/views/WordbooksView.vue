<script setup lang="ts">
import '../wordbooks.css'
import { computed, onMounted, reactive, ref } from 'vue'
import { useAuthStore } from '../stores/auth'
import {
  activateWordbook,
  canActivateWordbook,
  canDeleteWordbook,
  canExportWordbook,
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
import WordbookShelfCard from '../components/WordbookShelfCard.vue'
import AppIcon from '../components/AppIcon.vue'
import CrumboMark from '../components/CrumboMark.vue'

const PAGE_SIZE = 12
const auth = useAuthStore()
const books = ref<Wordbook[]>([])
const loading = ref(false)
const error = ref<unknown>(null)
const total = ref(0)
const pageOffset = ref(0)
const pageLimit = ref(PAGE_SIZE)
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

const filteredBooks = computed(() => {
  const query = filters.search.trim().toLocaleLowerCase('zh-CN')
  return books.value.filter((book) => {
    const matchesVisibility = !filters.visibility || book.visibility === filters.visibility
    const matchesSearch = !query
      || book.name.toLocaleLowerCase('zh-CN').includes(query)
      || (book.description ?? '').toLocaleLowerCase('zh-CN').includes(query)
    return matchesVisibility && matchesSearch
  })
})
const organizationBooks = computed(() => filteredBooks.value.filter((book) => book.visibility === 'organization'))
const privateBooks = computed(() => filteredBooks.value.filter((book) => book.visibility === 'private'))
const activeBook = computed(() => books.value.find((book) => book.is_active) ?? null)
const filterActive = computed(() => Boolean(filters.search.trim() || filters.visibility))
const empty = computed(() => !loading.value && !error.value && total.value === 0)
const filteredEmpty = computed(() => !loading.value && !error.value && books.value.length > 0 && filteredBooks.value.length === 0)
const hasPrevious = computed(() => pageOffset.value > 0)
const hasNext = computed(() => pageOffset.value + books.value.length < total.value)
const pageSummary = computed(() => {
  if (total.value === 0) {
    return '0 本'
  }
  const start = pageOffset.value + 1
  const end = Math.min(pageOffset.value + books.value.length, total.value)
  return `${start}–${end} / 共 ${total.value} 本`
})

const statusLabels: Record<WordbookStatus, string> = {
  importing: '导入中',
  ready: '可用',
  failed: '导入失败',
  deleting: '删除中',
  deleted: '已删除',
}

function statusLabel(status: WordbookStatus): string {
  return statusLabels[status]
}

function statusDescription(book: Wordbook): string {
  if (book.status === 'importing') {
    return '后台正在导入，完成前不可激活'
  }
  if (book.status === 'failed') {
    return '导入失败；请删除后重新创建'
  }
  if (book.status === 'deleting') {
    return '后台正在清理，操作已暂停'
  }
  if (book.status === 'deleted') {
    return '删除处理中'
  }
  return `${book.entry_count.toLocaleString('zh-CN')} 个词条`
}

function formatDate(value: string): string {
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? value : date.toLocaleDateString('zh-CN')
}

function canExport(book: Wordbook): boolean {
  return canExportWordbook(book, auth.user?.id ?? null, auth.isAdmin)
}

function canDelete(book: Wordbook): boolean {
  return canDeleteWordbook(book, auth.user?.id ?? null, auth.isAdmin)
}

async function load(offset = pageOffset.value): Promise<void> {
  const requestId = ++loadRequestId
  loading.value = true
  error.value = null
  try {
    const result = await listWordbooks({ offset, limit: PAGE_SIZE })
    if (requestId !== loadRequestId) {
      return
    }
    books.value = result.items
    total.value = result.total
    pageOffset.value = result.offset
    pageLimit.value = result.limit
  } catch (requestError) {
    if (requestId !== loadRequestId) {
      return
    }
    books.value = []
    total.value = 0
    error.value = requestError
  } finally {
    if (requestId === loadRequestId) {
      loading.value = false
    }
  }
}

function setVisibility(visibility: WordbookVisibility | ''): void {
  filters.visibility = visibility
}

async function nextPage(): Promise<void> {
  if (!hasNext.value || loading.value) {
    return
  }
  await load(pageOffset.value + pageLimit.value)
}

async function previousPage(): Promise<void> {
  if (!hasPrevious.value || loading.value) {
    return
  }
  await load(Math.max(0, pageOffset.value - pageLimit.value))
}

async function reloadAfterMutation(): Promise<void> {
  await load(pageOffset.value)
  if (books.value.length === 0 && pageOffset.value > 0) {
    await load(Math.max(0, pageOffset.value - pageLimit.value))
  }
}

async function activate(book: Wordbook): Promise<void> {
  if (activatingId.value || !canActivateWordbook(book)) {
    return
  }
  activatingId.value = book.id
  activationError.value = null
  operationMessage.value = ''

  try {
    await activateWordbook(book.id)
    operationMessage.value = `已将「${book.name}」设为当前主词书；旧词书和学习数据不会被清除。`
    await load(pageOffset.value)
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
  operationMessage.value = '词书已删除。'
  deleteTarget.value = null
  await reloadAfterMutation()
}

async function importCompleted(): Promise<void> {
  operationMessage.value = '词书导入完成。'
  pageOffset.value = 0
  await load(0)
}

function closeDeleteDialog(): void {
  const shouldRefresh = Boolean(
    deleteTarget.value
    && books.value.find((book) => book.id === deleteTarget.value?.id)?.status === 'deleting',
  )
  deleteTarget.value = null
  if (shouldRefresh) {
    void reloadAfterMutation()
  }
}

onMounted(() => {
  void load(0)
})
</script>

<template>
  <article class="wordbooks-page member-wordbooks-page wordbooks-workspace workspace-page" :class="{ 'crumb-wordbooks': !auth.isAdmin }">
    <template v-if="auth.isAdmin">
      <header class="workspace-page-header">
        <div>
          <p class="workspace-kicker">学习内容</p>
          <h1>我的词书</h1>
          <p class="workspace-page-lead">切换主词书，或导入一套自己的词汇。</p>
        </div>
        <button class="button workspace-primary-button" type="button" @click="importOpen = true">
          <AppIcon name="plus" /> 导入词书
        </button>
      </header>
    </template>
    <header v-else class="crumb-shelf-header">
      <div class="crumb-shelf-heading">
        <CrumboMark size="medium" />
        <div>
          <p class="crumb-brand-kicker">CRUMBTRAIL LIBRARY</p>
          <h1>咬一口，多记一个词。</h1>
          <p>每一本词书，都是 Crumbo 留下的一串面包屑。</p>
        </div>
      </div>
      <button class="button crumb-import-button" type="button" @click="importOpen = true">
        <AppIcon name="plus" /> 导入词书
      </button>
    </header>

    <section class="workspace-card wordbook-active-banner wordbook-active-strip crumb-current-book" :class="{ 'wordbook-active-banner--empty': !activeBook }">
      <div class="wordbook-active-copy">
        <span class="wordbook-active-mark" aria-hidden="true">{{ activeBook?.name.slice(0, 1) ?? 'W' }}</span>
        <div>
          <p class="workspace-kicker">当前主词书</p>
          <strong>{{ activeBook?.name ?? '还没有激活词书' }}</strong>
          <p>{{ activeBook ? `${activeBook.entry_count.toLocaleString('zh-CN')} 个词条` : '从下方列表选择一本开始学习。' }}</p>
        </div>
      </div>
      <span v-if="activeBook" class="wordbook-status wordbook-status--active">使用中</span>
    </section>

    <section class="workspace-card wordbooks-panel" :class="{ 'crumb-bookshelf': !auth.isAdmin }">
      <div class="wordbook-toolbar">
        <div class="wordbook-tabs" role="group" aria-label="筛选词书">
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

        <label class="wordbook-search">
          <span class="sr-only">在当前页搜索词书</span>
          <input
            v-model="filters.search"
            type="search"
            placeholder="搜索词书"
            autocomplete="off"
          />
        </label>

        <button class="button-secondary button-small" type="button" :disabled="loading && books.length === 0" :aria-busy="loading" @click="load(pageOffset)">
          {{ loading ? '读取中…' : '刷新' }}
        </button>
      </div>

      <p v-if="filterActive" class="wordbook-filter-note" role="note">筛选仅作用于当前页。</p>
      <p v-if="operationMessage" class="alert alert-success" role="status">{{ operationMessage }}</p>

      <LoadingState v-if="loading && books.length === 0" label="正在加载词书…" />
      <ErrorNotice v-else-if="error" :error="error" retry-label="重新读取词书" @retry="load(pageOffset)" />

      <div v-else-if="empty" class="workspace-empty-state wordbook-empty">
        <span class="wordbook-empty-mark" aria-hidden="true">Aa</span>
        <strong>还没有词书</strong>
        <p>导入一套词书，今天的任务才能开始。</p>
        <button class="button workspace-primary-button" type="button" @click="importOpen = true">导入一本词书</button>
      </div>

      <template v-else>
        <ErrorNotice v-if="activationError" :error="activationError" :show-retry="false" />

        <div v-if="filteredEmpty" class="workspace-empty-state wordbook-empty">
          <span class="wordbook-empty-mark" aria-hidden="true">Aa</span>
          <strong>当前页没有匹配项</strong>
          <p>清除筛选，或翻到下一页继续查找。</p>
        </div>

        <section v-if="organizationBooks.length" class="wordbook-group" aria-labelledby="organization-books-heading">
          <div class="wordbook-group-heading">
            <h2 id="organization-books-heading">组织词书</h2>
            <span class="count-pill">{{ organizationBooks.length }} 本</span>
          </div>
          <div class="wordbook-grid">
            <WordbookShelfCard
              v-for="(book, index) in organizationBooks"
              :key="book.id"
              :book="book"
              :status-label="statusLabel(book.status)"
              :status-description="statusDescription(book)"
              :formatted-date="formatDate(book.updated_at)"
              :can-activate="canActivateWordbook(book)"
              :can-export="canExport(book)"
              :can-delete="canDelete(book)"
              :activating="activatingId === book.id"
              :compact="!auth.isAdmin"
              :sequence="pageOffset + index + 1"
              @detail="detailId = book.id"
              @activate="activate(book)"
              @export="exportTarget = book"
              @delete="deleteTarget = book"
            />
          </div>
        </section>

        <section v-if="privateBooks.length" class="wordbook-group" aria-labelledby="private-books-heading">
          <div class="wordbook-group-heading">
            <h2 id="private-books-heading">我的私有词书</h2>
            <span class="count-pill">{{ privateBooks.length }} 本</span>
          </div>
          <div class="wordbook-grid">
            <WordbookShelfCard
              v-for="(book, index) in privateBooks"
              :key="book.id"
              :book="book"
              :status-label="statusLabel(book.status)"
              :status-description="statusDescription(book)"
              :formatted-date="formatDate(book.updated_at)"
              :can-activate="canActivateWordbook(book)"
              :can-export="canExport(book)"
              :can-delete="canDelete(book)"
              :activating="activatingId === book.id"
              :compact="!auth.isAdmin"
              :sequence="pageOffset + index + 1"
              @detail="detailId = book.id"
              @activate="activate(book)"
              @export="exportTarget = book"
              @delete="deleteTarget = book"
            />
          </div>
        </section>

        <div class="pagination" aria-label="词书分页">
          <button class="button-secondary button-small" type="button" :disabled="!hasPrevious || loading" @click="previousPage">上一页</button>
          <span>{{ pageSummary }}</span>
          <button class="button-secondary button-small" type="button" :disabled="!hasNext || loading" @click="nextPage">下一页</button>
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