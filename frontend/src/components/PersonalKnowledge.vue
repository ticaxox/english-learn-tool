<script setup lang="ts">
/**
 * The learner's own notes, indexed so the coach can cite them.
 *
 * Only the owner can see or remove them; the server filters at the SQL layer.
 */
import { onMounted, ref } from 'vue'
import ErrorNotice from './ErrorNotice.vue'
import LoadingState from './LoadingState.vue'
import {
  deleteMyKnowledge,
  listMyKnowledge,
  uploadMyKnowledge,
  type PersonalDocument,
} from '../api/knowledge'

const documents = ref<PersonalDocument[]>([])
const loading = ref(false)
const busy = ref(false)
const error = ref<unknown>(null)
const title = ref('')
const content = ref('')
const fileInput = ref<HTMLInputElement | null>(null)

async function load(): Promise<void> {
  loading.value = true
  error.value = null
  try {
    documents.value = await listMyKnowledge()
  } catch (loadError) {
    error.value = loadError
  } finally {
    loading.value = false
  }
}

async function onFile(event: Event): Promise<void> {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  input.value = ''
  if (!file) return
  content.value = (await file.text()).slice(0, 200_000)
  if (!title.value.trim()) title.value = file.name.replace(/\.[^.]+$/, '')
}

async function upload(): Promise<void> {
  if (busy.value) return
  if (!title.value.trim() || !content.value.trim()) {
    error.value = new Error('需要标题和正文。')
    return
  }
  busy.value = true
  error.value = null
  try {
    await uploadMyKnowledge(title.value.trim(), content.value)
    title.value = ''
    content.value = ''
    await load()
  } catch (uploadError) {
    error.value = uploadError
  } finally {
    busy.value = false
  }
}

async function remove(document: PersonalDocument): Promise<void> {
  if (!window.confirm(`删除「${document.title}」？教练将不再引用它。`)) return
  try {
    await deleteMyKnowledge(document.id)
    await load()
  } catch (removeError) {
    error.value = removeError
  }
}

onMounted(() => {
  void load()
})
</script>

<template>
  <section class="panel personal-knowledge" aria-labelledby="personal-knowledge-title">
    <header>
      <h3 id="personal-knowledge-title">我的资料</h3>
      <p class="field-hint">粘贴或选择一份笔记，教练回答时会引用它；只有你能看到。</p>
    </header>

    <input ref="fileInput" class="visually-hidden" type="file" accept=".txt,.md,.csv,text/plain" @change="onFile" />

    <label class="field">
      <span>标题</span>
      <input v-model="title" maxlength="200" placeholder="例如 六级作文模板" />
    </label>
    <label class="field">
      <span>正文</span>
      <textarea v-model="content" rows="6" placeholder="粘贴重点、错题笔记或范文…"></textarea>
    </label>

    <div class="personal-knowledge__actions">
      <DivButton class="button-secondary" type="button" @click="fileInput?.click()">选择文件</DivButton>
      <DivButton type="button" :disabled="busy" @click="upload">
        {{ busy ? '正在索引…' : '上传并索引' }}
      </DivButton>
    </div>

    <ErrorNotice v-if="error" :error="error" :show-retry="false" />
    <LoadingState v-if="loading && documents.length === 0" label="正在读取…" />

    <ul v-else-if="documents.length" class="personal-knowledge__list">
      <li v-for="document in documents" :key="document.id">
        <span>{{ document.title }}</span>
        <small>{{ document.chunkCount }} 块</small>
        <DivButton class="button-secondary button-small" type="button" @click="remove(document)">删除</DivButton>
      </li>
    </ul>
    <p v-else-if="!loading" class="field-hint">还没有上传任何资料。</p>
  </section>
</template>
