<script setup lang="ts">
/**
 * /settings/knowledge — the knowledge shelves, read and maintained here.
 *
 * A file manager: shelves on the left, the open shelf on the right as folders
 * and documents. Everyone reads the global shelves; only an administrator
 * writes to them. Your own shelves are yours alone, and the coach retrieves
 * from exactly what this page shows you.
 *
 * Adding, importing, renaming and deleting sit on the right-click menu of a
 * shelf or a document and on the ⋯ of every card; the toolbar keeps only the
 * two actions a newcomer needs.
 */
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from 'vue'
import DivButton from '../components/DivButton.vue'
import ErrorNotice from '../components/ErrorNotice.vue'
import { useAuthStore } from '../stores/auth'
import {
  createKnowledgeFolder,
  deleteKnowledgeDocument,
  deleteKnowledgeFolder,
  getKnowledgeDocument,
  importIntoFolder,
  listFolderDocuments,
  listKnowledgeFolders,
  renameKnowledgeDocument,
  renameKnowledgeFolder,
  type KnowledgeDocument,
  type KnowledgeDocumentDetail,
  type KnowledgeFolder,
  type KnowledgeScope,
} from '../api/knowledge'
import '../knowledge.css'

type IconName = 'open' | 'folder' | 'upload' | 'pencil' | 'trash'

interface MenuItem {
  label?: string
  icon?: IconName
  danger?: boolean
  separator?: boolean
  run?: () => void
}

interface DialogState {
  title: string
  hint?: string
  value: string
  content?: string
  multiline?: boolean
  danger?: boolean
  confirmLabel: string
  resolve: (result: { name: string; content: string } | null) => void
}

const ICONS: Record<IconName, string> = {
  open: 'M5 12h14M13 6l6 6-6 6',
  folder:
    'M3 7.5A2.5 2.5 0 0 1 5.5 5h4l2 2.5h7A2.5 2.5 0 0 1 21 10v7.5A2.5 2.5 0 0 1 18.5 20h-13A2.5 2.5 0 0 1 3 17.5z',
  upload: 'M12 16V4M7 9l5-5 5 5M4 16v3a1 1 0 0 0 1 1h14a1 1 0 0 0 1-1v-3',
  pencil: 'M4 20h4l10-10-4-4L4 16z',
  trash: 'M4 7h16M9 7V5h6v2M6 7l1 13h10l1-13',
}

const FOLDER_PATH =
  'M3 7.5A2.5 2.5 0 0 1 5.5 5h4l2 2.5h7A2.5 2.5 0 0 1 21 10v7.5A2.5 2.5 0 0 1 18.5 20h-13A2.5 2.5 0 0 1 3 17.5z'

const auth = useAuthStore()
const isAdmin = computed(() => auth.isAdmin)

const folders = ref<KnowledgeFolder[]>([])
const documents = ref<KnowledgeDocument[]>([])
const currentId = ref<string | null>(null)
const view = ref<'grid' | 'list'>('grid')
const sort = ref<'name' | 'updated' | 'count'>('name')
const query = ref('')
const loadingTree = ref(false)
const loadingDocs = ref(false)
const error = ref<unknown>(null)

const menu = ref<{ x: number; y: number; label: string; items: MenuItem[] } | null>(null)
const dialog = ref<DialogState | null>(null)
const dialogInput = ref<HTMLInputElement | null>(null)
const preview = ref<KnowledgeDocumentDetail | null>(null)

const byParent = computed(() => {
  const map = new Map<string | null, KnowledgeFolder[]>()
  for (const folder of folders.value) {
    const list = map.get(folder.parentId) ?? []
    list.push(folder)
    map.set(folder.parentId, list)
  }
  for (const list of map.values()) list.sort((a, b) => a.name.localeCompare(b.name, 'zh'))
  return map
})

const rootFolders = computed(() => byParent.value.get(null) ?? [])
const childrenOf = (id: string): KnowledgeFolder[] => byParent.value.get(id) ?? []

const current = computed(
  () => folders.value.find((folder) => folder.id === currentId.value) ?? null,
)
const trail = computed(() => {
  const out: KnowledgeFolder[] = []
  let cursor = current.value
  while (cursor) {
    out.unshift(cursor)
    const parentId: string | null = cursor.parentId
    cursor = parentId ? (folders.value.find((f) => f.id === parentId) ?? null) : null
  }
  return out
})

const matches = (text: string): boolean =>
  !query.value || text.toLowerCase().includes(query.value.toLowerCase())

const children = computed(() => {
  const list = (current.value ? childrenOf(current.value.id) : []).filter((folder) =>
    matches(folder.name),
  )
  const copy = [...list]
  if (sort.value === 'name') copy.sort((a, b) => a.name.localeCompare(b.name, 'zh'))
  if (sort.value === 'count') copy.sort((a, b) => b.documentCount - a.documentCount)
  return copy
})

const visibleDocuments = computed(() => {
  const copy = documents.value.filter(
    (doc) => matches(doc.title) || matches(doc.snippet),
  )
  if (sort.value === 'name') copy.sort((a, b) => a.title.localeCompare(b.title, 'zh'))
  if (sort.value === 'updated') copy.sort((a, b) => b.updatedAt.localeCompare(a.updatedAt))
  if (sort.value === 'count') copy.sort((a, b) => b.chunkCount - a.chunkCount)
  return copy
})

const canWrite = computed(() => current.value?.writable === true)
const empty = computed(
  () => children.value.length === 0 && visibleDocuments.value.length === 0 && !loadingDocs.value,
)

function typeOf(doc: KnowledgeDocument): { label: string; color: string } {
  const kind = typeof doc.metadata?.type === 'string' ? doc.metadata.type : ''
  if (kind.includes('词')) return { label: kind, color: 'var(--kb-type-vocab)' }
  if (kind.includes('笔记')) return { label: kind, color: 'var(--kb-type-notes)' }
  return { label: kind || '资料', color: 'var(--kb-type-exam)' }
}

function formatDate(value: string): string {
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return ''
  return new Intl.DateTimeFormat('zh-CN', { month: '2-digit', day: '2-digit' }).format(date)
}

/* --------------------------------------------------------------- loading */

async function loadTree(): Promise<void> {
  loadingTree.value = true
  error.value = null
  try {
    folders.value = await listKnowledgeFolders()
    if (currentId.value === null || !folders.value.some((f) => f.id === currentId.value)) {
      currentId.value = folders.value[0]?.id ?? null
    }
    if (currentId.value) await loadDocuments(currentId.value)
  } catch (cause) {
    error.value = cause
  } finally {
    loadingTree.value = false
  }
}

async function loadDocuments(folderId: string): Promise<void> {
  loadingDocs.value = true
  try {
    documents.value = await listFolderDocuments(folderId)
  } catch (cause) {
    error.value = cause
    documents.value = []
  } finally {
    loadingDocs.value = false
  }
}

function openFolder(id: string): void {
  if (currentId.value === id) return
  currentId.value = id
  documents.value = []
  void loadDocuments(id)
}

/* ------------------------------------------------------------------ menu */

function showMenu(event: MouseEvent, label: string, items: MenuItem[]): void {
  event.preventDefault()
  event.stopPropagation()
  const list = items.filter(Boolean)
  if (!list.length) return
  menu.value = { x: event.clientX, y: event.clientY, label, items: list }
  void nextTick(() => document.querySelector<HTMLElement>('.kb-ctx button')?.focus())
}

function closeMenu(): void {
  menu.value = null
}

function folderMenu(folder: KnowledgeFolder): MenuItem[] {
  if (!folder.writable) return [{ label: '打开', icon: 'open', run: () => openFolder(folder.id) }]
  return [
    { label: '打开', icon: 'open', run: () => openFolder(folder.id) },
    { separator: true },
    { label: '新建子书架…', icon: 'folder', run: () => createFolder(folder.id, folder.scope) },
    { label: '导入资料…', icon: 'upload', run: () => importDocument(folder.id) },
    { separator: true },
    { label: '重命名…', icon: 'pencil', run: () => renameFolder(folder) },
    { label: '删除书架', icon: 'trash', danger: true, run: () => removeFolder(folder) },
  ]
}

function docMenu(doc: KnowledgeDocument): MenuItem[] {
  const items: MenuItem[] = [{ label: '打开', icon: 'open', run: () => openDocument(doc) }]
  if (current.value?.writable) {
    items.push(
      { separator: true },
      { label: '重命名…', icon: 'pencil', run: () => renameDocument(doc) },
      { label: '删除资料', icon: 'trash', danger: true, run: () => removeDocument(doc) },
    )
  }
  return items
}

function emptyMenu(): MenuItem[] {
  const folder = current.value
  if (!folder?.writable) return []
  return [
    { label: '新建书架…', icon: 'folder', run: () => createFolder(folder.id, folder.scope) },
    { label: '导入资料…', icon: 'upload', run: () => importDocument(folder.id) },
  ]
}

function onBodyContextMenu(event: MouseEvent): void {
  const target = event.target as HTMLElement
  if (target.closest('.kb-folder, .kb-doc, .kb-trow, .kb-row')) return
  const items = emptyMenu()
  if (!items.length) return
  showMenu(event, current.value?.name ?? '操作', items)
}

function onMenuKey(event: KeyboardEvent): void {
  const buttons = [...document.querySelectorAll<HTMLElement>('.kb-ctx button')]
  const at = buttons.indexOf(document.activeElement as HTMLElement)
  if (event.key === 'Escape') closeMenu()
  else if (event.key === 'ArrowDown') {
    event.preventDefault()
    buttons[(at + 1) % buttons.length]?.focus()
  } else if (event.key === 'ArrowUp') {
    event.preventDefault()
    buttons[(at - 1 + buttons.length) % buttons.length]?.focus()
  } else if (event.key === 'Tab') closeMenu()
}

/* --------------------------------------------------------------- dialog */

function ask(
  state: Omit<DialogState, 'resolve' | 'confirmLabel'> & { confirmLabel?: string },
): Promise<{ name: string; content: string } | null> {
  return new Promise((resolve) => {
    dialog.value = { ...state, confirmLabel: state.confirmLabel ?? '确定', resolve }
    void nextTick(() => dialogInput.value?.focus())
  })
}

function submitDialog(): void {
  const state = dialog.value
  if (!state) return
  dialog.value = null
  state.resolve({ name: state.value.trim(), content: state.content ?? '' })
}

function cancelDialog(): void {
  const state = dialog.value
  dialog.value = null
  state?.resolve(null)
}

/* ------------------------------------------------------------ mutations */

async function createFolder(parentId: string, scope: KnowledgeScope): Promise<void> {
  const parent = folders.value.find((f) => f.id === parentId)
  const result = await ask({
    title: '新建书架',
    hint: parent ? `建在「${parent.name}」里面。` : undefined,
    value: '',
    confirmLabel: '创建',
  })
  if (!result?.name) return
  try {
    const folder = await createKnowledgeFolder({ name: result.name, scope, parentId, level: null })
    await loadTree()
    openFolder(folder.id)
  } catch (cause) {
    error.value = cause
  }
}

async function importDocument(folderId: string): Promise<void> {
  const target = folders.value.find((f) => f.id === folderId)
  const result = await ask({
    title: '导入资料',
    hint: `导入到「${target?.name ?? ''}」。正文会按题号自动切块。`,
    value: '',
    content: '',
    multiline: true,
    confirmLabel: '导入',
  })
  if (!result?.name) return
  if (!result.content.trim()) {
    error.value = new Error('需要正文。')
    return
  }
  try {
    await importIntoFolder(folderId, { title: result.name, content: result.content })
    await loadTree()
  } catch (cause) {
    error.value = cause
  }
}

async function renameFolder(folder: KnowledgeFolder): Promise<void> {
  const result = await ask({ title: '重命名书架', value: folder.name })
  if (!result?.name) return
  try {
    await renameKnowledgeFolder(folder.id, result.name)
    await loadTree()
  } catch (cause) {
    error.value = cause
  }
}

async function renameDocument(doc: KnowledgeDocument): Promise<void> {
  const result = await ask({ title: '重命名资料', value: doc.title })
  if (!result?.name) return
  try {
    await renameKnowledgeDocument(doc.id, result.name)
    if (doc.folderId) await loadDocuments(doc.folderId)
  } catch (cause) {
    error.value = cause
  }
}

async function removeFolder(folder: KnowledgeFolder): Promise<void> {
  const result = await ask({
    title: '删除书架',
    hint: `「${folder.name}」和里面的所有书架、资料都会被删除；资料会移回「综合」。`,
    value: folder.name,
    danger: true,
    confirmLabel: '删除',
  })
  if (!result) return
  try {
    await deleteKnowledgeFolder(folder.id)
    if (trail.value.some((part) => part.id === folder.id)) currentId.value = null
    await loadTree()
  } catch (cause) {
    error.value = cause
  }
}

async function removeDocument(doc: KnowledgeDocument): Promise<void> {
  const result = await ask({
    title: '删除资料',
    hint: `「${doc.title}」会从检索里一起消失。`,
    value: doc.title,
    danger: true,
    confirmLabel: '删除',
  })
  if (!result) return
  try {
    await deleteKnowledgeDocument(doc.id)
    await loadTree()
  } catch (cause) {
    error.value = cause
  }
}

async function openDocument(doc: KnowledgeDocument): Promise<void> {
  try {
    preview.value = await getKnowledgeDocument(doc.id)
  } catch (cause) {
    error.value = cause
  }
}

/* --------------------------------------------------------------- wiring */

function onGlobalKey(event: KeyboardEvent): void {
  if (event.key !== 'Escape') return
  if (menu.value) closeMenu()
  else if (preview.value) preview.value = null
}

onMounted(() => {
  void loadTree()
  document.addEventListener('click', closeMenu)
  document.addEventListener('keydown', onGlobalKey)
})

onBeforeUnmount(() => {
  document.removeEventListener('click', closeMenu)
  document.removeEventListener('keydown', onGlobalKey)
})
</script>

<template>
  <section class="kb" aria-label="知识库">
    <div class="kb-bar">
      <button
        class="kb-back"
        type="button"
        aria-label="返回上一级"
        :disabled="trail.length <= 1"
        @click="trail.length > 1 && openFolder(trail[trail.length - 2].id)"
      >
        <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m15 18-6-6 6-6" /></svg>
      </button>

      <nav class="kb-nav" aria-label="路径">
        <template v-for="(part, index) in trail" :key="part.id">
          <button
            type="button"
            :aria-current="index === trail.length - 1 ? 'page' : undefined"
            @click="openFolder(part.id)"
          >
            {{ part.name }}
          </button>
          <span v-if="index < trail.length - 1" class="sep">/</span>
        </template>
      </nav>

      <label class="kb-search">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="7" /><path d="m20 20-3.5-3.5" /></svg>
        <input v-model="query" placeholder="搜索书架与资料" aria-label="搜索书架与资料" />
      </label>

      <div class="kb-seg" role="group" aria-label="视图">
        <button type="button" :aria-pressed="view === 'grid'" aria-label="网格视图" @click="view = 'grid'">
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3.5" y="3.5" width="7" height="7" rx="1.5" /><rect x="13.5" y="3.5" width="7" height="7" rx="1.5" /><rect x="3.5" y="13.5" width="7" height="7" rx="1.5" /><rect x="13.5" y="13.5" width="7" height="7" rx="1.5" /></svg>
        </button>
        <button type="button" :aria-pressed="view === 'list'" aria-label="列表视图" @click="view = 'list'">
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M4 6h16M4 12h16M4 18h16" /></svg>
        </button>
      </div>

      <DivButton
        v-if="isAdmin && current"
        class="kb-btn ghost"
        type="button"
        @click="createFolder(current.id, current.scope)"
      >新建书架</DivButton>
      <DivButton
        v-if="canWrite && current"
        class="kb-btn"
        type="button"
        @click="importDocument(current.id)"
      >导入资料</DivButton>
    </div>

    <ErrorNotice v-if="error" :error="error" :show-retry="false" />

    <div class="kb-shell">
      <aside class="kb-sidebar" aria-label="书架">
        <div
          v-for="group in [
            { scope: 'global', title: '全局知识库' },
            { scope: 'personal', title: '我的知识库' },
          ]"
          :key="group.scope"
          class="kb-group"
        >
          <div class="kb-group__title"><span>{{ group.title }}</span></div>
          <template v-for="root in rootFolders" :key="root.id">
            <template v-if="root.scope === group.scope">
              <button
                type="button"
                class="kb-row d0"
                :aria-current="root.id === currentId ? 'true' : 'false'"
                @click="openFolder(root.id)"
                @contextmenu="showMenu($event, root.name, folderMenu(root))"
              >
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linejoin="round"><path :d="FOLDER_PATH" /></svg>
                <span class="kb-row__name">{{ root.name }}</span>
                <span class="kb-row__count">{{ root.documentCount || '' }}</span>
              </button>
              <button
                v-for="child in childrenOf(root.id)"
                :key="child.id"
                type="button"
                class="kb-row d1"
                :aria-current="child.id === currentId ? 'true' : 'false'"
                @click="openFolder(child.id)"
                @contextmenu="showMenu($event, child.name, folderMenu(child))"
              >
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linejoin="round"><path :d="FOLDER_PATH" /></svg>
                <span class="kb-row__name">{{ child.name }}</span>
                <span class="kb-row__count">{{ child.documentCount || '' }}</span>
              </button>
              <button
                v-for="grand in childrenOf(root.id).flatMap((c) => childrenOf(c.id))"
                :key="grand.id"
                type="button"
                class="kb-row d2"
                :aria-current="grand.id === currentId ? 'true' : 'false'"
                @click="openFolder(grand.id)"
                @contextmenu="showMenu($event, grand.name, folderMenu(grand))"
              >
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linejoin="round"><path :d="FOLDER_PATH" /></svg>
                <span class="kb-row__name">{{ grand.name }}</span>
                <span class="kb-row__count">{{ grand.documentCount || '' }}</span>
              </button>
            </template>
          </template>
        </div>
      </aside>

      <div class="kb-main" @contextmenu="onBodyContextMenu">
        <div class="kb-head">
          <h1>{{ current?.name ?? '知识库' }}</h1>
          <span class="meta">
            {{ current?.documentCount ?? 0 }} 份资料<template v-if="current?.scope === 'global'"> · 全局，所有人可读</template><template v-else-if="current"> · 私有</template>
          </span>
          <span class="spacer"></span>
          <label class="kb-sort">
            排序
            <select v-model="sort">
              <option value="name">名称</option>
              <option value="updated">最近更新</option>
              <option value="count">资料数</option>
            </select>
          </label>
        </div>

        <div class="kb-body">
          <p v-if="loadingTree && folders.length === 0" class="kb-loading">正在读取…</p>

          <template v-else-if="current">
            <template v-if="view === 'grid'">
              <template v-if="children.length">
                <p class="kb-section">书架</p>
                <div class="kb-folders">
                  <div
                    v-for="folder in children"
                    :key="folder.id"
                    class="kb-folder"
                    @contextmenu="showMenu($event, folder.name, folderMenu(folder))"
                  >
                    <button class="kb-folder__hit" type="button" @click="openFolder(folder.id)">
                      <svg class="kb-folder__icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linejoin="round"><path :d="FOLDER_PATH" /></svg>
                      <span class="kb-folder__text">
                        <span class="kb-folder__name">{{ folder.name }}</span>
                        <span class="kb-folder__meta">{{ folder.documentCount }} 份资料</span>
                      </span>
                    </button>
                    <button
                      v-if="folder.writable"
                      class="kb-more"
                      type="button"
                      aria-label="更多操作"
                      @click.stop="showMenu($event, folder.name, folderMenu(folder))"
                    >⋯</button>
                  </div>
                </div>
              </template>

              <template v-if="visibleDocuments.length">
                <p class="kb-section">资料</p>
                <div class="kb-docs">
                  <div
                    v-for="doc in visibleDocuments"
                    :key="doc.id"
                    class="kb-doc"
                    :style="{ '--kb-type': typeOf(doc).color }"
                    @contextmenu="showMenu($event, doc.title, docMenu(doc))"
                  >
                    <button class="kb-doc__hit" type="button" @click="openDocument(doc)">
                      <span class="kb-doc__title">{{ doc.title }}</span>
                      <span class="kb-doc__snippet">{{ doc.snippet || '尚无正文摘要' }}</span>
                      <span class="kb-doc__foot">
                        <span class="kb-doc__dot"></span>{{ typeOf(doc).label }} · {{ doc.chunkCount }} 块 · {{ formatDate(doc.updatedAt) }}
                      </span>
                    </button>
                    <button
                      v-if="current.writable"
                      class="kb-more"
                      type="button"
                      aria-label="更多操作"
                      @click.stop="showMenu($event, doc.title, docMenu(doc))"
                    >⋯</button>
                  </div>
                </div>
              </template>
            </template>

            <template v-else>
              <div v-if="children.length || visibleDocuments.length" class="kb-table">
                <div class="kb-thead"><span>名称</span><span>资料</span><span>更新</span><span></span></div>
                <button
                  v-for="folder in children"
                  :key="folder.id"
                  class="kb-trow"
                  type="button"
                  @click="openFolder(folder.id)"
                  @contextmenu="showMenu($event, folder.name, folderMenu(folder))"
                >
                  <span class="name">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linejoin="round" style="color: var(--g-orange)"><path :d="FOLDER_PATH" /></svg>
                    <span>{{ folder.name }}</span>
                  </span>
                  <span class="meta">{{ folder.documentCount }} 份</span>
                  <span class="meta"></span>
                  <span></span>
                </button>
                <button
                  v-for="doc in visibleDocuments"
                  :key="doc.id"
                  class="kb-trow"
                  type="button"
                  :style="{ '--kb-type': typeOf(doc).color }"
                  @click="openDocument(doc)"
                  @contextmenu="showMenu($event, doc.title, docMenu(doc))"
                >
                  <span class="name">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linejoin="round"><path d="M6 3.5h7l5 5V20a1 1 0 0 1-1 1H6a1 1 0 0 1-1-1V4.5a1 1 0 0 1 1-1z" /><path d="M13 3.5V9h5" /></svg>
                    <span>{{ doc.title }}</span>
                  </span>
                  <span class="meta">{{ doc.chunkCount }} 块</span>
                  <span class="meta">{{ formatDate(doc.updatedAt) }}</span>
                  <span></span>
                </button>
              </div>
            </template>

            <div v-if="empty" class="kb-empty">
              <template v-if="query">
                <strong>没有匹配「{{ query }}」的内容</strong>
                <span>试试书架名或资料里的关键词。</span>
                <DivButton class="kb-btn ghost" type="button" @click="query = ''">清除搜索</DivButton>
              </template>
              <template v-else>
                <strong>这个书架还是空的</strong>
                <span>导入真题或笔记，教练答题时就能引用它。</span>
                <DivButton v-if="canWrite" class="kb-btn" type="button" @click="importDocument(current.id)">导入资料</DivButton>
              </template>
            </div>
          </template>

          <p v-else class="kb-loading">左边选一个书架。</p>
        </div>
      </div>
    </div>

    <div
      v-if="menu"
      class="kb-ctx"
      role="menu"
      :aria-label="menu.label"
      :style="{ left: `${menu.x}px`, top: `${menu.y}px` }"
      @click.stop
      @contextmenu.prevent.stop
      @keydown="onMenuKey"
    >
      <div class="kb-ctx__label">{{ menu.label }}</div>
      <template v-for="(item, index) in menu.items" :key="index">
        <hr v-if="item.separator" />
        <button
          v-else
          type="button"
          role="menuitem"
          :class="{ 'is-danger': item.danger }"
          @click="closeMenu(); item.run?.()"
        >
          <svg v-if="item.icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path :d="ICONS[item.icon]" /></svg>
          <span>{{ item.label }}</span>
        </button>
      </template>
    </div>

    <div v-if="dialog" class="kb-backdrop" @click.self="cancelDialog">
      <form class="kb-dialog" role="dialog" aria-modal="true" :aria-label="dialog.title" @submit.prevent="submitDialog">
        <h2>{{ dialog.title }}</h2>
        <p v-if="dialog.hint">{{ dialog.hint }}</p>
        <input
          ref="dialogInput"
          v-model="dialog.value"
          :aria-label="dialog.title"
          :readonly="dialog.danger"
          @keydown.esc.prevent="cancelDialog"
        />
        <textarea v-if="dialog.multiline" v-model="dialog.content" aria-label="正文" placeholder="粘贴正文…"></textarea>
        <div class="kb-dialog__acts">
          <DivButton class="kb-btn ghost" type="button" @click="cancelDialog">取消</DivButton>
          <DivButton
            class="kb-btn"
            :class="{ danger: dialog.danger }"
            type="submit"
            :disabled="!dialog.danger && !dialog.value.trim()"
          >{{ dialog.confirmLabel }}</DivButton>
        </div>
      </form>
    </div>

    <div v-if="preview" class="kb-backdrop" @click.self="preview = null">
      <div class="kb-dialog" role="dialog" aria-modal="true" :aria-label="preview.title">
        <h2>{{ preview.title }}</h2>
        <p>{{ preview.folders ?? '未归类' }} · {{ preview.chunkCount }} 块 · {{ formatDate(preview.updatedAt) }}</p>
        <pre class="kb-doc-body">{{ preview.content }}</pre>
        <div class="kb-dialog__acts">
          <DivButton class="kb-btn" type="button" @click="preview = null">关闭</DivButton>
        </div>
      </div>
    </div>
  </section>
</template>
