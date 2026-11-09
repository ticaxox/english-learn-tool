<script setup lang="ts">
/**
 * /admin/knowledge — import and maintain the reference corpus.
 *
 * Only administrators reach this page; learners see the search results the coach
 * cites, never the raw documents.
 */
import { computed, onMounted, ref } from 'vue'
import AppIcon from '../components/AppIcon.vue'
import ErrorNotice from '../components/ErrorNotice.vue'
import LoadingState from '../components/LoadingState.vue'
import {
  archiveKnowledgeDocument,
  importKnowledgeDocument,
  listKnowledgeDocuments,
  searchKnowledge,
  type KnowledgeDocument,
  type KnowledgeHit,
} from '../api/knowledge'
import '../ai-admin.css'

const documents = ref<KnowledgeDocument[]>([])
const loading = ref(false)
const loadError = ref<unknown>(null)
const actionError = ref<unknown>(null)
const importing = ref(false)

const title = ref('')
const content = ref('')
const fileInput = ref<HTMLInputElement | null>(null)

const probe = ref('')
const hits = ref<KnowledgeHit[]>([])
const searching = ref(false)
const searchError = ref<unknown>(null)

const ready = computed(() => documents.value.filter((item) => item.status === 'ready').length)

async function load(): Promise<void> {
  loading.value = true
  loadError.value = null
  try {
    documents.value = await listKnowledgeDocuments()
  } catch (error) {
    loadError.value = error
  } finally {
    loading.value = false
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

async function importDocument(): Promise<void> {
  if (importing.value) return
  actionError.value = null
  if (!title.value.trim() || !content.value.trim()) {
    actionError.value = new Error('需要标题和正文。')
    return
  }
  importing.value = true
  try {
    await importKnowledgeDocument({ title: title.value.trim(), content: content.value })
    title.value = ''
    content.value = ''
    await load()
  } catch (error) {
    actionError.value = error
  } finally {
    importing.value = false
  }
}

async function archive(document: KnowledgeDocument): Promise<void> {
  if (!window.confirm(`下架「${document.title}」？它的分块会一起删除。`)) return
  actionError.value = null
  try {
    await archiveKnowledgeDocument(document.id)
    await load()
  } catch (error) {
    actionError.value = error
  }
}

async function runSearch(): Promise<void> {
  if (!probe.value.trim() || searching.value) return
  searching.value = true
  searchError.value = null
  try {
    hits.value = await searchKnowledge(probe.value.trim())
  } catch (error) {
    searchError.value = error
    hits.value = []
  } finally {
    searching.value = false
  }
}

function statusLabel(status: KnowledgeDocument['status']): string {
  return { draft: '草稿', indexing: '索引中', ready: '已发布', failed: '失败', archived: '已下架' }[status]
}

function formatDate(value: string): string {
  const date = new Date(value)
  return Number.isNaN(date.getTime())
    ? ''
    : new Intl.DateTimeFormat('zh-CN', { month: 'numeric', day: 'numeric' }).format(date)
}

onMounted(() => {
  void load()
})
</script>

<template>
  <section class="knowledge-admin" aria-labelledby="knowledge-title">
    <header class="ia-subsection-header">
      <div>
        <p class="eyebrow">知识库</p>
        <h2 id="knowledge-title">真题与参考资料</h2>
        <p>只有管理员可以导入；学员在教练回答里看到的检索结果都来自这里。</p>
      </div>
      <span class="ia-hub-badge">{{ ready }} 份已发布</span>
    </header>

    <div class="knowledge-layout">
      <section class="panel knowledge-import" aria-labelledby="knowledge-import-title">
        <h3 id="knowledge-import-title">导入一份资料</h3>
        <p class="field-hint">纯文本即可，按题号自动切块；也可以先选一个 txt / md 文件。</p>

        <label class="field">
          <span>标题</span>
          <input v-model="title" maxlength="200" placeholder="例如 2023-06 四级阅读" />
        </label>

        <label class="field">
          <span>正文</span>
          <textarea v-model="content" rows="10" placeholder="粘贴题目、答案与解析…"></textarea>
        </label>

        <input
          ref="fileInput"
          class="visually-hidden"
          type="file"
          accept=".txt,.md,text/plain,text/markdown"
          @change="onFile"
        />
        <div class="knowledge-import__actions">
          <DivButton class="button-secondary" type="button" @click="fileInput?.click()">
            <AppIcon name="paperclip" /> 选择文件
          </DivButton>
          <DivButton type="button" :disabled="importing" @click="importDocument">
            {{ importing ? '正在索引…' : '导入并索引' }}
          </DivButton>
        </div>

        <ErrorNotice v-if="actionError" :error="actionError" :show-retry="false" />
      </section>

      <section class="panel knowledge-list" aria-labelledby="knowledge-list-title">
        <h3 id="knowledge-list-title">已导入</h3>
        <LoadingState v-if="loading && documents.length === 0" label="正在读取…" />
        <ErrorNotice v-else-if="loadError" :error="loadError" retry-label="重新读取" @retry="load" />
        <ul v-else-if="documents.length">
          <li v-for="document in documents" :key="document.id" class="knowledge-row">
            <div class="knowledge-row__main">
              <strong>{{ document.title }}</strong>
              <small>
                {{ document.chunkCount }} 块 · {{ statusLabel(document.status) }} ·
                {{ formatDate(document.createdAt) }}
                <template v-if="document.embeddingModel"> · {{ document.embeddingModel }}</template>
              </small>
            </div>
            <DivButton class="button-secondary button-small" type="button" @click="archive(document)">
              下架
            </DivButton>
          </li>
        </ul>
        <p v-else class="field-hint">还没有导入任何资料。</p>
      </section>
    </div>

    <section class="panel knowledge-probe" aria-labelledby="knowledge-probe-title">
      <h3 id="knowledge-probe-title">试检索</h3>
      <p class="field-hint">用学员会问的说法试一下，确认能命中再上线。</p>
      <form class="knowledge-probe__form" @submit.prevent="runSearch">
        <input v-model="probe" placeholder="例如 night market harbor" maxlength="500" />
        <DivButton type="submit" :disabled="searching || !probe.trim()">
          {{ searching ? '检索中…' : '检索' }}
        </DivButton>
      </form>
      <ErrorNotice v-if="searchError" :error="searchError" :show-retry="false" />
      <ul v-if="hits.length" class="knowledge-hits">
        <li v-for="(hit, index) in hits" :key="`${hit.documentId}-${index}`">
          <strong>[{{ index + 1 }}] {{ hit.title }}</strong>
          <small>相关度 {{ hit.score }}</small>
          <p>{{ hit.content }}</p>
        </li>
      </ul>
      <p v-else-if="!searching && probe && !searchError" class="field-hint">没有命中，换个说法试试。</p>
    </section>
  </section>
</template>
