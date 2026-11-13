<script setup lang="ts">
/**
 * /settings/knowledge — the learner's knowledge shelves, and the product's.
 *
 * Left is what you can read: the global shelves filed by difficulty, then your
 * own. Right is the shelf you picked — its documents, and the one you opened.
 * Everyone reads the global shelves; only an administrator writes to them, and
 * only you write to yours. The coach retrieves from exactly these.
 */
import { computed, onMounted, ref } from 'vue'
import DivButton from '../components/DivButton.vue'
import ErrorNotice from '../components/ErrorNotice.vue'
import LoadingState from '../components/LoadingState.vue'
import {
  createKnowledgeFolder,
  deleteKnowledgeDocument,
  deleteKnowledgeFolder,
  getKnowledgeDocument,
  importIntoFolder,
  listFolderDocuments,
  listKnowledgeFolders,
  type KnowledgeDocument,
  type KnowledgeDocumentDetail,
  type KnowledgeFolder,
} from '../api/knowledge'
import '../knowledge.css'

const folders = ref<KnowledgeFolder[]>([])
const documents = ref<KnowledgeDocument[]>([])
const detail = ref<KnowledgeDocumentDetail | null>(null)
const selectedId = ref<string | null>(null)

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

const creatingFolder = ref(false)
const folderName = ref('')

const globalFolders = computed(() => folders.value.filter((folder) => folder.scope === 'global'))
const personalFolders = computed(() => folders.value.filter((folder) => folder.scope === 'personal'))
const selected = computed(
  () => folders.value.find((folder) => folder.id === selectedId.value) ?? null,
)
const totalDocuments = computed(() =>
  folders.value.reduce((sum, folder) => sum + folder.documentCount, 0),
)
const canWriteSelected = computed(() => selected.value?.writable === true)
const canDeleteSelected = computed(
  () => selected.value !== null && selected.value.scope === 'personal',
)

async function loadTree(): Promise<void> {
  loadingTree.value = true
  loadError.value = null
  try {
    folders.value = await listKnowledgeFolders()
    if (selectedId.value === null || !folders.value.some((f) => f.id === selectedId.value)) {
      selectedId.value = folders.value[0]?.id ?? null
    }
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
  showImport.value = false
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

async function submitFolder(): Promise<void> {
  const name = folderName.value.trim()
  if (!name) return
  actionError.value = null
  try {
    const folder = await createKnowledgeFolder({ name, scope: 'personal' })
    folderName.value = ''
    creatingFolder.value = false
    await loadTree()
    await selectFolder(folder)
  } catch (error) {
    actionError.value = error
  }
}

async function removeFolder(): Promise<void> {
  const folder = selected.value
  if (!folder) return
  if (!window.confirm(`删除文件夹「${folder.name}」？里面的资料会移到「综合」。`)) return
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
        <p class="lead">按难度整理的真题，和你自己的资料。教练答题时会从这里找依据。</p>
      </div>
      <span class="kb-head__count">{{ totalDocuments }} 份资料</span>
    </header>

    <ErrorNotice v-if="loadError" :error="loadError" retry-label="重新读取" @retry="loadTree" />

    <div class="kb-layout">
      <aside class="kb-tree" aria-label="知识库书架">
        <LoadingState v-if="loadingTree && folders.length === 0" label="正在读取…" />

        <div class="kb-group">
          <span class="kb-group__title">全局知识库</span>
          <button
            v-for="folder in globalFolders"
            :key="folder.id"
            class="kb-folder"
            :class="{ 'is-active': folder.id === selectedId }"
            type="button"
            @click="selectFolder(folder)"
          >
            <span class="kb-folder__name">{{ folder.name }}</span>
            <span class="kb-folder__count">{{ folder.documentCount }}</span>
          </button>
        </div>

        <div class="kb-group">
          <span class="kb-group__title">
            我的知识库
            <button class="kb-new" type="button" aria-label="新建文件夹" @click="creatingFolder = !creatingFolder">＋</button>
          </span>

          <form v-if="creatingFolder" class="kb-newform" @submit.prevent="submitFolder">
            <input v-model="folderName" maxlength="120" placeholder="文件夹名称" aria-label="文件夹名称" />
            <DivButton type="submit" :disabled="!folderName.trim()">建</DivButton>
          </form>

          <button
            v-for="folder in personalFolders"
            :key="folder.id"
            class="kb-folder"
            :class="{ 'is-active': folder.id === selectedId }"
            type="button"
            @click="selectFolder(folder)"
          >
            <span class="kb-folder__name">{{ folder.name }}</span>
            <span class="kb-folder__count">{{ folder.documentCount }}</span>
          </button>
          <p v-if="personalFolders.length === 0 && !creatingFolder" class="kb-empty">
            还没有自己的文件夹。建一个，把笔记或资料放进来。
          </p>
        </div>
      </aside>

      <div class="kb-main">
        <ErrorNotice v-if="actionError" :error="actionError" :show-retry="false" />

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
          <LoadingState v-if="loadingDetail" label="正在读取…" />
        </template>

        <template v-else-if="selected">
          <header class="kb-main__head">
            <div>
              <h2>{{ selected.name }}</h2>
              <p class="field-hint">
                {{ selected.documentCount }} 份资料<template v-if="selected.scope === 'global'"> · 全局，所有人可读</template>
              </p>
            </div>
            <div class="kb-main__acts">
              <DivButton
                v-if="canWriteSelected"
                class="button-secondary"
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
                删除文件夹
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
