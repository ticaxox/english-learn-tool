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
const CATALOG_PAGE_SIZE = 100
const auth = useAuthStore()
const catalog = ref<Wordbook[]>([])
const loading = ref(false)
const error = ref<unknown>(null)
const pageOffset = ref(0)
const operationMessage = ref('')
const activationError = ref<unknown>(null)
const activatingId = ref<string | null>(null)
let loadRequestId = 0

const filters = reactive({
  search: '',
})

const detailId = ref<string | null>(null)
const selectedBook = computed(() => visibleBooks.value.find((book) => book.id === detailId.value) ?? null)
const importOpen = ref(false)
const exportTarget = ref<Wordbook | null>(null)
const deleteTarget = ref<Wordbook | null>(null)

const filteredBooks = computed(() => {
  const query = filters.search.trim().toLocaleLowerCase('zh-CN')
  return catalog.value.filter((book) => {
    const matchesVisibility = book.visibility === 'private'
    const matchesSearch = !query
      || book.name.toLocaleLowerCase('zh-CN').includes(query)
      || (book.description ?? '').toLocaleLowerCase('zh-CN').includes(query)
    return matchesVisibility && matchesSearch
  })
})
const visibleBooks = computed(() => filteredBooks.value.slice(pageOffset.value, pageOffset.value + PAGE_SIZE))
const personalBookCount = computed(() => catalog.value.filter((book) => book.visibility === 'private').length)
const activeBook = computed(() => catalog.value.find((book) => book.visibility === 'private' && book.is_active) ?? null)
const filterActive = computed(() => Boolean(filters.search.trim()))
const empty = computed(() => !loading.value && !error.value && personalBookCount.value === 0)
const filteredEmpty = computed(() => !loading.value && !error.value && personalBookCount.value > 0 && filteredBooks.value.length === 0)
const hasPrevious = computed(() => pageOffset.value > 0)
const hasNext = computed(() => pageOffset.value + visibleBooks.value.length < filteredBooks.value.length)
const pageSummary = computed(() => {
  if (filteredBooks.value.length === 0) {
    return '0 本'
  }
  const start = pageOffset.value + 1
  const end = Math.min(pageOffset.value + visibleBooks.value.length, filteredBooks.value.length)
  return `${start}–${end} / 共 ${filteredBooks.value.length} 本`
})

const statusLabels: Record<WordbookStatus, string> = {
  importing: '导入中',
  ready: '可用',
  failed: '导入失败',
  deleting: '删除中',
  deleted: '已删除',
}

function coverMark(name: string | undefined): string {
  if (!name) return 'W'
  const lastToken = name.trim().split(/\s+/).at(-1) ?? ''
  if (/^\d{2,}$/.test(lastToken)) return lastToken.slice(-2)
  return name.trim().slice(0, 1).toUpperCase() || 'W'
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
  return canExportWordbook(book, auth.user?.id ?? null, false)
}

function canDelete(book: Wordbook): boolean {
  return canDeleteWordbook(book, auth.user?.id ?? null, false)
}

async function load(): Promise<void> {
  const requestId = ++loadRequestId
  loading.value = true
  error.value = null
  try {
    const items: Wordbook[] = []
    let offset = 0
    let total = Number.POSITIVE_INFINITY
    while (offset < total) {
      const result = await listWordbooks({ offset, limit: CATALOG_PAGE_SIZE })
      if (requestId !== loadRequestId) return
      items.push(...result.items)
      total = result.total
      if (result.items.length === 0) break
      offset += result.items.length
    }
    catalog.value = items
    pageOffset.value = 0
  } catch (requestError) {
    if (requestId !== loadRequestId) {
      return
    }
    catalog.value = []
    error.value = requestError
  } finally {
    if (requestId === loadRequestId) {
      loading.value = false
    }
  }
}

function nextPage(): void {
  if (!hasNext.value || loading.value) {
    return
  }
  pageOffset.value += PAGE_SIZE
}

function previousPage(): void {
  if (!hasPrevious.value || loading.value) {
    return
  }
  pageOffset.value = Math.max(0, pageOffset.value - PAGE_SIZE)
}

async function reloadAfterMutation(): Promise<void> {
  await load()
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
    await load()
  } catch (requestError) {
    activationError.value = requestError
  } finally {
    activatingId.value = null
  }
}

function markDeleting(wordbookId: string): void {
  const target = catalog.value.find((book) => book.id === wordbookId)
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
  await load()
}

function closeDeleteDialog(): void {
  const shouldRefresh = Boolean(
    deleteTarget.value
    && catalog.value.find((book) => book.id === deleteTarget.value?.id)?.status === 'deleting',
  )
  deleteTarget.value = null
  if (shouldRefresh) {
    void reloadAfterMutation()
  }
}

onMounted(() => {
  void load()
})
</script>

<template>
  <article class="wordbooks-page member-wordbooks-page wordbooks-workspace workspace-page crumb-wordbooks">
    <header class="crumb-shelf-header">
      <div class="crumb-shelf-heading">
        <CrumboMark size="medium" />
        <div>
          <p class="crumb-brand-kicker">CRUMBTRAIL LIBRARY</p>
          <h1>咬一口，多记一个词。</h1>
          <p>每一本词书，都是 Crumbo 留下的一串面包屑。</p>
        </div>
      </div>
      <DivButton class="button crumb-import-button" type="button" @click="importOpen = true">
        <AppIcon name="plus" /> 导入词书
      </DivButton>
    </header>

    <section class="workspace-card wordbook-active-banner wordbook-active-strip crumb-current-book" :class="{ 'wordbook-active-banner--empty': !activeBook }">
      <div class="wordbook-active-copy">
        <span class="wordbook-active-mark" aria-hidden="true">{{ coverMark(activeBook?.name) }}</span>
        <div>
          <p class="workspace-kicker">当前主词书</p>
          <strong>{{ activeBook?.name ?? '还没有激活词书' }}</strong>
          <p>{{ activeBook ? `${activeBook.entry_count.toLocaleString('zh-CN')} 个词条` : '从下方列表选择一本开始学习。' }}</p>
        </div>
      </div>
      <span v-if="activeBook" class="wordbook-status wordbook-status--active">使用中</span>
    </section>

    <section class="workspace-card wordbooks-panel crumb-bookshelf">
      <div class="wordbook-toolbar">
        <div class="wordbook-toolbar-title">
          <strong>个人词书</strong>
          <span>{{ personalBookCount }} 本</span>
        </div>

        <label class="wordbook-search">
          <span class="sr-only">搜索全部个人词书</span>
          <input
            v-model="filters.search"
            type="search"
            placeholder="搜索词书"
            autocomplete="off"
          />
        </label>

        <DivButton class="button-secondary button-small" type="button" :disabled="loading && catalog.length === 0" :aria-busy="loading" @click="load">
          {{ loading ? '读取中…' : '刷新' }}
        </DivButton>
      </div>

      <p v-if="operationMessage" class="alert alert-success" role="status">{{ operationMessage }}</p>

      <LoadingState v-if="loading && catalog.length === 0" label="正在加载词书…" />
      <ErrorNotice v-else-if="error" :error="error" retry-label="重新读取词书" @retry="load" />

      <div v-else-if="empty" class="workspace-empty-state wordbook-empty">
        <span class="wordbook-empty-mark" aria-hidden="true">Aa</span>
        <strong>还没有词书</strong>
        <p>导入一套词书，今天的任务才能开始。</p>
        <DivButton class="button workspace-primary-button" type="button" @click="importOpen = true">导入一本词书</DivButton>
      </div>

      <template v-else>
        <ErrorNotice v-if="activationError" :error="activationError" :show-retry="false" />

        <div v-if="filteredEmpty" class="workspace-empty-state wordbook-empty">
          <span class="wordbook-empty-mark" aria-hidden="true">Aa</span>
          <strong>没有匹配的词书</strong>
          <p>换一个关键词，或清除搜索后查看全部个人词书。</p>
        </div>

        <section v-if="filteredBooks.length" class="wordbook-group" aria-labelledby="private-books-heading">
          <div class="wordbook-group-heading">
            <h2 id="private-books-heading">{{ filterActive ? '搜索结果' : '词书书架' }}</h2>
            <span class="count-pill">{{ filterActive ? `${filteredBooks.length} 个结果` : `${personalBookCount} 本` }}</span>
          </div>
          <div class="wordbook-grid">
            <WordbookShelfCard
              v-for="(book, index) in visibleBooks"
              :key="book.id"
              :book="book"
              :status-label="statusLabel(book.status)"
              :status-description="statusDescription(book)"
              :formatted-date="formatDate(book.updated_at)"
              :can-activate="canActivateWordbook(book)"
              :can-export="canExport(book)"
              :can-delete="canDelete(book)"
              :activating="activatingId === book.id"
              compact
              :sequence="pageOffset + index + 1"
              @detail="detailId = book.id"
              @activate="activate(book)"
              @export="exportTarget = book"
              @delete="deleteTarget = book"
            />
          </div>
        </section>

        <div class="pagination" aria-label="词书分页">
          <DivButton class="button-secondary button-small" type="button" :disabled="!hasPrevious || loading" @click="previousPage">上一页</DivButton>
          <span>{{ pageSummary }}</span>
          <DivButton class="button-secondary button-small" type="button" :disabled="!hasNext || loading" @click="nextPage">下一页</DivButton>
        </div>
      </template>
    </section>

    <WordbookImportDialog
      v-if="importOpen"
      :is-admin="false"
      @close="importOpen = false"
      @completed="importCompleted"
    />
    <WordbookDetailDialog
      v-if="detailId"
      :wordbook-id="detailId"
      :book="selectedBook"
      :can-activate="selectedBook ? canActivateWordbook(selectedBook) : false"
      :can-export="selectedBook ? canExport(selectedBook) : false"
      :can-delete="selectedBook ? canDelete(selectedBook) : false"
      :activating="selectedBook ? activatingId === selectedBook.id : false"
      @close="detailId = null"
      @activate="selectedBook && activate(selectedBook)"
      @export="selectedBook && (exportTarget = selectedBook)"
      @delete="selectedBook && (deleteTarget = selectedBook)"
    />
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
