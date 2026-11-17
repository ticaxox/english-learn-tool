<script setup lang="ts">
import '../wordbooks.css'
import { computed, onMounted, reactive, ref } from 'vue'
import ArtImage from '../components/ArtImage.vue'
import { illustration } from '../assets/halloween'
import { useAuthStore } from '../stores/auth'
import {
  activateWordbook,
  canActivateWordbook,
  canDeleteWordbook,
  canExportWordbook,
  listWordbooks,
  type Wordbook,
} from '../api/wordbooks'
import ErrorNotice from '../components/ErrorNotice.vue'
import CrumbSearch from '../components/ui/CrumbSearch.vue'
import LoadingState from '../components/LoadingState.vue'
import WordbookDeleteDialog from '../components/WordbookDeleteDialog.vue'
import WordbookDetailDialog from '../components/WordbookDetailDialog.vue'
import WordbookExportDialog from '../components/WordbookExportDialog.vue'
import WordbookImportDialog from '../components/WordbookImportDialog.vue'
import WordbookShelfCard from '../components/WordbookShelfCard.vue'
import AppIcon from '../components/AppIcon.vue'

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
    const matchesSearch = !query
      || book.name.toLocaleLowerCase('zh-CN').includes(query)
      || (book.description ?? '').toLocaleLowerCase('zh-CN').includes(query)
    return matchesSearch
  })
})
const visibleBooks = computed(() => filteredBooks.value.slice(pageOffset.value, pageOffset.value + PAGE_SIZE))
const personalBookCount = computed(() => catalog.value.length)
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

function canExport(book: Wordbook): boolean {
  return canExportWordbook(book, auth.user?.id ?? null, auth.isAdmin)
}

function canDelete(book: Wordbook): boolean {
  return canDeleteWordbook(book, auth.user?.id ?? null, auth.isAdmin)
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
    <section class="workspace-card wordbooks-panel crumb-bookshelf">
      <div class="wordbook-toolbar">
        <h2 class="wordbook-toolbar-heading">{{ filterActive ? '搜索结果' : '词书书架' }}</h2>

        <CrumbSearch
          v-model="filters.search"
          class="wordbook-search"
          label="搜索全部个人词书"
          placeholder="搜索词书"
        />
        <span class="sr-only">个人词书</span>

        <span class="count-pill">{{ filterActive ? `${filteredBooks.length} 个结果` : `${personalBookCount} 本` }}</span>

        <div class="wordbook-toolbar-actions">
          <DivButton class="button-secondary button-small" type="button" :disabled="loading && catalog.length === 0" :aria-busy="loading" @click="load">
            {{ loading ? '读取中…' : '刷新' }}
          </DivButton>
          <DivButton class="button button-small" type="button" @click="importOpen = true">
            <AppIcon name="plus" /> 导入词书
          </DivButton>
        </div>
      </div>

      <p v-if="operationMessage" class="alert alert-success" role="status">{{ operationMessage }}</p>

      <LoadingState v-if="loading && catalog.length === 0" label="正在加载词书…" />
      <ErrorNotice v-else-if="error" :error="error" retry-label="重新读取词书" @retry="load" />

      <div v-else-if="empty" class="workspace-empty-state wordbook-empty">
        <ArtImage class="wordbook-empty-art" :set="illustration.library" />
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

        <section v-if="filteredBooks.length" class="wordbook-group" aria-label="词书书架">
          <div class="wordbook-grid">
            <WordbookShelfCard
              v-for="book in visibleBooks"
              :key="book.id"
              :book="book"
              @detail="detailId = book.id"
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
      :is-admin="auth.isAdmin"
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
      :is-admin="auth.isAdmin"
      @close="detailId = null"
      @updated="load"
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
