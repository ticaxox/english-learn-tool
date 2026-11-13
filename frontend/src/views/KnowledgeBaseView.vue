<script setup lang="ts">
/**
 * /settings/knowledge — the learner's knowledge shelves, and the product's.
 *
 * Left is what you can read: the global shelves, nested as deep as the
 * administrator filed them, then your own. Right is the shelf you picked — its
 * sub-shelves, its documents, and the one you opened.
 *
 * Everyone reads the global shelves; only an administrator writes to them.
 * Yours are yours alone. The coach retrieves from exactly these.
 */
import { computed, nextTick, onMounted, ref } from 'vue'
import DivButton from '../components/DivButton.vue'
import ErrorNotice from '../components/ErrorNotice.vue'
import LoadingState from '../components/LoadingState.vue'
import { useAuthStore } from '../stores/auth'
import {
  createKnowledgeFolder,
  deleteKnowledgeDocument,
  deleteKnowledgeFolder,
  getKnowledgeDocument,
  importIntoFolder,
  listFolderDocuments,
  listKnowledgeFolders,
  type KnowledgeLevel,
  type KnowledgeDocument,
  type KnowledgeDocumentDetail,
  type KnowledgeFolder,
  type KnowledgeScope,
} from '../api/knowledge'
import '../knowledge.css'

interface TreeRow {
  folder: KnowledgeFolder
  depth: number
  hasChildren: boolean
}

const auth = useAuthStore()
const isAdmin = computed(() => auth.isAdmin)

const folders = ref<KnowledgeFolder[]>([])
const documents = ref<KnowledgeDocument[]>([])
const detail = ref<KnowledgeDocumentDetail | null>(null)
const selectedId = ref<string | null>(null)
const expanded = ref<Set<string>>(new Set())

const loadingTree = ref(false)
const loadingDocs = ref(false)
const loadingDetail = ref(false)
const loadError = ref<unknown>(null)
const actionError = ref<unknown>(null)

const importing = ref(false)
const showImport = ref(false)
const title = ref('')
const content = ref('')
const fileInput = ref<HTMLInputElement | null>(null)

/** Where a new shelf goes: a root of either scope, or a child of one. */
const newFolder = ref<{ parentId: string | null; scope: KnowledgeScope } | null>(null)
const folderName = ref('')
const folderLevel = ref('')

// The exam a global shelf is for. Named `level` here so the word this project
// reserves for FSRS scheduling never appears in a view.
const LEVEL_OPTIONS = [
  ['GAOKAO', '高考'],
  ['CET4', '四级'],
  ['CET6', '六级'],
  ['POSTGRAD', '考研'],
  ['IELTS', '雅思'],
  ['TOEFL', '托福'],
] as const

const byParent = computed(() => {
  const map = new Map<string | null, KnowledgeFolder[]>()
  for (const folder of folders.value) {
    const siblings = map.get(folder.parentId) ?? []
    siblings.push(folder)
    map.set(folder.parentId, siblings)
  }
  for (const siblings of map.values()) siblings.sort((a, b) => a.name.localeCompare(b.name, 'zh'))
  return map
})

const selected = computed(
  () => folders.value.find((folder) => folder.id === selectedId.value) ?? null,
)
const canWriteSelected = computed(() => selected.value?.writable === true)
const canDeleteSelected = computed(() => {
  const folder = selected.value
  if (!folder) return false
  if (folder.isGeneral) return false
  return folder.writable
})
const totalDocuments = computed(() =>
  folders.value.reduce((sum, folder) => sum + folder.documentCount, 0),
)

function flatten(scope: KnowledgeScope): TreeRow[] {
  const rows: TreeRow[] = []
  const walk = (parentId: string | null, depth: number): void => {
    for (const folder of byParent.value.get(parentId) ?? []) {
      if (folder.scope !== scope) continue
      const children = (byParent.value.get(folder.id) ?? []).filter((f) => f.scope === scope)
      rows.push({ folder, depth, hasChildren: children.length > 0 })
      if (children.length && expanded.value.has(folder.id)) walk(folder.id, depth + 1)
    }
  }
  walk(null, 0)
  return rows
}

const globalRows = computed(() => flatten('global'))
const personalRows = computed(() => flatten('personal'))

const path = computed(() => {
  const names: string[] = []
  let cursor = selected.value
  while (cursor) {
    names.unshift(cursor.name)
    const parentId: string | null = cursor.parentId
    cursor = parentId ? (folders.value.find((f) => f.id === parentId) ?? null) : null
  }
  return names
})

function toggle(folder: KnowledgeFolder): void {
  const next = new Set(expanded.value)
  if (next.has(folder.id)) next.delete(folder.id)
  else next.add(folder.id)
  expanded.value = next
}

function expandLineage(folder: KnowledgeFolder): void {
  const next = new Set(expanded.value)
  let parentId = folder.parentId
  while (parentId) {
    next.add(parentId)
    parentId = folders.value.find((f) => f.id === parentId)?.parentId ?? null
  }
  expanded.value = next
}

async function loadTree(): Promise<void> {
  loadingTree.value = true
  loadError.value = null
  try {
    folders.value = await listKnowledgeFolders()
    if (selectedId.value === null || !folders.value.some((f) => f.id === selectedId.value)) {
      selectedId.value = folders.value[0]?.id ?? null
    }
    const current = folders.value.find((f) => f.id === selectedId.value)
    if (current) expandLineage(current)
    if (selectedId.value) await loadDocuments(selectedId.value)
  } catch (error) {
    loadError.value = error
  } finally {
    loadingTree.value = false
  }
}

async function loadDocuments(folderId: string): Promise<void> {
  loadingDocs.value = true
  detail.value = null
  try {
    documents.value = await listFolderDocuments(folderId)
  } catch (error) {
    loadError.value = error
    documents.value = []
  } finally {
    loadingDocs.value = false
  }
}

async function selectFolder(folder: KnowledgeFolder): Promise<void> {
  if (selectedId.value === folder.id && detail.value === null) return
  selectedId.value = folder.id
  expandLineage(folder)
  showImport.value = false
  newFolder.value = null
  actionError.value = null
  await loadDocuments(folder.id)
}

async function openDocument(document: KnowledgeDocument): Promise<void> {
  loadingDetail.value = true
  actionError.value = null
  try {
    detail.value = await getKnowledgeDocument(document.id)
  } catch (error) {
    actionError.value = error
  } finally {
    loadingDetail.value = false
  }
}

function closeDocument(): void {
  detail.value = null
}

async function removeDocument(document: KnowledgeDocument): Promise<void> {
  if (!window.confirm(`删除「${document.title}」？它会从检索里一起消失。`)) return
  actionError.value = null
  try {
    await deleteKnowledgeDocument(document.id)
    detail.value = null
    await loadTree()
  } catch (error) {
    actionError.value = error
  }
}

const nameInput = ref<HTMLInputElement | null>(null)

function startCreate(parentId: string | null, scope: KnowledgeScope): void {
  newFolder.value = { parentId, scope }
  folderName.value = ''
  folderLevel.value = ''
  showImport.value = false
  actionError.value = null
  void nextTick(() => nameInput.value?.focus())
}

function closeCreate(): void {
  newFolder.value = null
  folderName.value = ''
  folderLevel.value = ''
}

function parentName(parentId: string): string {
  return folders.value.find((folder) => folder.id === parentId)?.name ?? ''
}

async function submitFolder(): Promise<void> {
  const target = newFolder.value
  const name = folderName.value.trim()
  if (!target || !name) return
  actionError.value = null
  try {
    const folder = await createKnowledgeFolder({
      name,
      scope: target.scope,
      level:
        target.scope === 'global' ? ((folderLevel.value || null) as KnowledgeLevel | null) : null,
      parentId: target.parentId,
    })
    closeCreate()
    await loadTree()
    await selectFolder(folder)
  } catch (error) {
    actionError.value = error
  }
}

async function removeFolder(): Promise<void> {
  const folder = selected.value
  if (!folder) return
  if (!window.confirm(`删除「${folder.name}」？子文件夹会一起删除，资料会移到「综合」。`)) return
  actionError.value = null
  try {
    await deleteKnowledgeFolder(folder.id)
    selectedId.value = null
    await loadTree()
  } catch (error) {
    actionError.value = error
  }
}

async function onFile(event: Event): Promise<void> {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  input.value = ''
  if (!file) return
  if (file.size > 2 * 1024 * 1024) {
    actionError.value = new Error('文件不能超过 2 MB')
    return
  }
  content.value = await file.text()
  if (!title.value.trim()) title.value = file.name.replace(/\.[^.]+$/, '')
}

async function submitImport(): Promise<void> {
  const folder = selected.value
  if (!folder || importing.value) return
  actionError.value = null
  if (!title.value.trim() || !content.value.trim()) {
    actionError.value = new Error('需要标题和正文。')
    return
  }
  importing.value = true
  try {
    await importIntoFolder(folder.id, { title: title.value.trim(), content: content.value })
    title.value = ''
    content.value = ''
    showImport.value = false
    await loadTree()
  } catch (error) {
    actionError.value = error
  } finally {
    importing.value = false
  }
}

function formatDate(value: string): string {
  const date = new Date(value)
  return Number.isNaN(date.getTime())
    ? ''
    : new Intl.DateTimeFormat('zh-CN', { month: 'numeric', day: 'numeric' }).format(date)
}

onMounted(() => {
  void loadTree()
})
</script>

<template>
  <section class="kb" aria-labelledby="kb-title">
    <header class="kb-head">
      <div>
        <p class="eyebrow">知识库</p>
        <h1 id="kb-title">知识库</h1>
        <p class="lead">按难度和主题整理的真题，和你自己的资料。教练答题时会从这里找依据。</p>
      </div>
      <span class="kb-head__count">{{ totalDocuments }} 份资料</span>
    </header>

    <ErrorNotice v-if="loadError" :error="loadError" retry-label="重新读取" @retry="loadTree" />

    <div class="kb-layout">
      <aside class="kb-tree" aria-label="知识库书架">
        <LoadingState v-if="loadingTree && folders.length === 0" label="正在读取…" />

        <div class="kb-group">
          <span class="kb-group__title">
            全局知识库
            <button
              v-if="isAdmin"
              class="kb-new"
              type="button"
              aria-label="新建全局书架"
              @click="startCreate(null, 'global')"
            >
              ＋
            </button>
          </span>
          <div v-for="row in globalRows" :key="row.folder.id" class="kb-row">
            <button
              v-if="row.hasChildren"
              class="kb-caret"
              type="button"
              :aria-label="expanded.has(row.folder.id) ? '收起' : '展开'"
              :aria-expanded="expanded.has(row.folder.id)"
              :style="{ marginLeft: `${row.depth * 14}px` }"
              @click.stop="toggle(row.folder)"
            >
              {{ expanded.has(row.folder.id) ? '▾' : '▸' }}
            </button>
            <span v-else class="kb-caret kb-caret--empty" :style="{ marginLeft: `${row.depth * 14}px` }"></span>
            <button
              class="kb-folder"
              :class="{ 'is-active': row.folder.id === selectedId }"
              type="button"
              @click="selectFolder(row.folder)"
            >
              <svg
                class="kb-folder__icon"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                stroke-width="1.8"
                stroke-linejoin="round"
                aria-hidden="true"
              >
                <path d="M3 7.5A2.5 2.5 0 0 1 5.5 5h4l2 2.5h7A2.5 2.5 0 0 1 21 10v7.5A2.5 2.5 0 0 1 18.5 20h-13A2.5 2.5 0 0 1 3 17.5z" />
              </svg>
              <span class="kb-folder__name">{{ row.folder.name }}</span>
              <span class="kb-folder__count">{{ row.folder.documentCount }}</span>
            </button>
            <button
              v-if="row.folder.writable"
              class="kb-add-child"
              type="button"
              :aria-label="`在「${row.folder.name}」里新建书架`"
              @click.stop="startCreate(row.folder.id, row.folder.scope)"
            >
              ＋
            </button>
          </div>
        </div>

        <div class="kb-group">
          <span class="kb-group__title">
            我的知识库
            <button
              class="kb-new"
              type="button"
              aria-label="新建文件夹"
              @click="startCreate(null, 'personal')"
            >
              ＋
            </button>
          </span>
          <div v-for="row in personalRows" :key="row.folder.id" class="kb-row">
            <button
              v-if="row.hasChildren"
              class="kb-caret"
              type="button"
              :aria-label="expanded.has(row.folder.id) ? '收起' : '展开'"
              :aria-expanded="expanded.has(row.folder.id)"
              :style="{ marginLeft: `${row.depth * 14}px` }"
              @click.stop="toggle(row.folder)"
            >
              {{ expanded.has(row.folder.id) ? '▾' : '▸' }}
            </button>
            <span v-else class="kb-caret kb-caret--empty" :style="{ marginLeft: `${row.depth * 14}px` }"></span>
            <button
              class="kb-folder"
              :class="{ 'is-active': row.folder.id === selectedId }"
              type="button"
              @click="selectFolder(row.folder)"
            >
              <svg
                class="kb-folder__icon"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                stroke-width="1.8"
                stroke-linejoin="round"
                aria-hidden="true"
              >
                <path d="M3 7.5A2.5 2.5 0 0 1 5.5 5h4l2 2.5h7A2.5 2.5 0 0 1 21 10v7.5A2.5 2.5 0 0 1 18.5 20h-13A2.5 2.5 0 0 1 3 17.5z" />
              </svg>
              <span class="kb-folder__name">{{ row.folder.name }}</span>
              <span class="kb-folder__count">{{ row.folder.documentCount }}</span>
            </button>
            <button
              v-if="row.folder.writable"
              class="kb-add-child"
              type="button"
              :aria-label="`在「${row.folder.name}」里新建书架`"
              @click.stop="startCreate(row.folder.id, row.folder.scope)"
            >
              ＋
            </button>
          </div>
          <p v-if="personalRows.length === 0" class="kb-empty">
            还没有自己的文件夹。建一个，把笔记或资料放进来。
          </p>
        </div>
      </aside>

      <div class="kb-main">
        <ErrorNotice v-if="actionError" :error="actionError" :show-retry="false" />

        <div v-if="newFolder" class="dialog-backdrop" @click.self="closeCreate">
          <form
            class="dialog-card kb-dialog"
            role="dialog"
            aria-modal="true"
            aria-labelledby="kb-dialog-title"
            @submit.prevent="submitFolder"
            @keydown.esc="closeCreate"
          >
            <header class="dialog-heading">
              <div>
                <p class="eyebrow">{{ newFolder.scope === 'global' ? '全局知识库' : '我的知识库' }}</p>
                <h2 id="kb-dialog-title">
                  {{ newFolder.parentId ? `在「${parentName(newFolder.parentId)}」里新建书架` : newFolder.scope === 'global' ? '新建全局书架' : '新建文件夹' }}
                </h2>
              </div>
              <DivButton class="icon-button" type="button" aria-label="关闭" @click="closeCreate">✕</DivButton>
            </header>

            <label class="field">
              <span>名称</span>
              <input ref="nameInput" v-model="folderName" maxlength="120" placeholder="例如 真题、2023、阅读错题" />
            </label>

            <label v-if="newFolder.scope === 'global'" class="field">
              <span>难度（可选）</span>
              <select v-model="folderLevel">
                <option value="">通用（不分难度）</option>
                <option v-for="[code, label] in LEVEL_OPTIONS" :key="code" :value="code">
                  {{ label }}
                </option>
              </select>
            </label>

            <div class="kb-dialog__acts">
              <DivButton class="button-secondary" type="button" @click="closeCreate">取消</DivButton>
              <DivButton type="submit" :disabled="!folderName.trim()">创建</DivButton>
            </div>
          </form>
        </div>

        <template v-if="detail">
          <header class="kb-main__head">
            <button class="kb-back" type="button" @click="closeDocument">← 返回列表</button>
            <div class="kb-main__acts">
              <DivButton
                v-if="canWriteSelected"
                class="button-danger button-small"
                type="button"
                @click="removeDocument(detail)"
              >
                删除
              </DivButton>
            </div>
          </header>
          <h2 class="kb-doc-title">{{ detail.title }}</h2>
          <p class="kb-doc-meta">
            {{ detail.folders ?? '未归类' }} · {{ detail.chunkCount }} 块 · {{ formatDate(detail.createdAt) }}
          </p>
          <pre class="kb-doc-body">{{ detail.content }}</pre>
        </template>

        <template v-else-if="selected">
          <header class="kb-main__head">
            <div>
              <p class="kb-path">{{ path.join(' / ') }}</p>
              <h2>{{ selected.name }}</h2>
              <p class="field-hint">
                {{ selected.documentCount }} 份资料<template v-if="selected.scope === 'global'"> · 全局，所有人可读</template>
              </p>
            </div>
            <div class="kb-main__acts">
              <DivButton
                v-if="canWriteSelected"
                class="button-secondary button-small"
                type="button"
                @click="startCreate(selected.id, selected.scope)"
              >
                新建子书架
              </DivButton>
              <DivButton
                v-if="canWriteSelected"
                class="button-secondary button-small"
                type="button"
                @click="showImport = !showImport"
              >
                {{ showImport ? '收起' : '导入资料' }}
              </DivButton>
              <DivButton
                v-if="canDeleteSelected"
                class="button-danger button-small"
                type="button"
                @click="removeFolder"
              >
                删除书架
              </DivButton>
            </div>
          </header>

          <form v-if="showImport && canWriteSelected" class="kb-import panel" @submit.prevent="submitImport">
            <label class="field">
              <span>标题</span>
              <input v-model="title" maxlength="200" placeholder="例如 2023-06 四级阅读" />
            </label>
            <label class="field">
              <span>正文</span>
              <textarea v-model="content" rows="8" placeholder="粘贴题目、答案与解析…"></textarea>
            </label>
            <input
              ref="fileInput"
              class="visually-hidden"
              type="file"
              accept=".txt,.md,text/plain,text/markdown"
              @change="onFile"
            />
            <div class="kb-import__acts">
              <DivButton class="button-secondary button-small" type="button" @click="fileInput?.click()">
                选择文件
              </DivButton>
              <DivButton class="button-small" type="submit" :disabled="importing">
                {{ importing ? '正在索引…' : '导入并索引' }}
              </DivButton>
            </div>
          </form>

          <LoadingState v-if="loadingDocs" label="正在读取…" />
          <ul v-else-if="documents.length" class="kb-docs">
            <li v-for="document in documents" :key="document.id">
              <button class="kb-doc" type="button" @click="openDocument(document)">
                <span class="kb-doc__title">{{ document.title }}</span>
                <span class="kb-doc__meta">
                  {{ document.chunkCount }} 块 · {{ formatDate(document.createdAt) }}
                </span>
                <span class="kb-doc__arrow" aria-hidden="true">→</span>
              </button>
            </li>
          </ul>
          <p v-else class="kb-empty">这个书架还是空的。</p>
        </template>

        <p v-else class="kb-empty">左边选一个书架。</p>
      </div>
    </div>
  </section>
</template>
