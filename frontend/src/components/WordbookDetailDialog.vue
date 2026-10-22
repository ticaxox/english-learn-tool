<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useDialogA11y } from '../composables/useDialogA11y'
import {
  getWordbookDetail,
  type WordbookDetail,
  type WordbookStatus,
} from '../api/wordbooks'
import ErrorNotice from './ErrorNotice.vue'
import LoadingState from './LoadingState.vue'

const props = defineProps<{
  wordbookId: string
}>()

const emit = defineEmits<{
  close: []
}>()

const detail = ref<WordbookDetail | null>(null)
const entries = ref<WordbookDetail['entries'] | null>(null)
const loading = ref(false)
const error = ref<unknown>(null)
const cursor = ref<string | null>(null)
const cursorHistory = ref<Array<string | null>>([])
const dialogRef = ref<HTMLElement | null>(null)

function statusLabel(status: WordbookStatus): string {
  return {
    importing: '导入中',
    ready: '可用',
    failed: '导入失败',
    deleting: '删除中',
  }[status]
}

function formatDate(value: string): string {
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString('zh-CN')
}

async function load(nextCursor: string | null = null): Promise<void> {
  loading.value = true
  error.value = null
  try {
    const result = await getWordbookDetail(props.wordbookId, nextCursor)
    detail.value = result
    entries.value = result.entries
    cursor.value = nextCursor
  } catch (requestError) {
    error.value = requestError
  } finally {
    loading.value = false
  }
}

async function nextPage(): Promise<void> {
  if (!entries.value?.next_cursor) {
    return
  }
  cursorHistory.value.push(cursor.value)
  await load(entries.value.next_cursor)
}

async function previousPage(): Promise<void> {
  const previous = cursorHistory.value.pop()
  if (previous === undefined) {
    return
  }
  await load(previous)
}

function close(): void {
  emit('close')
}

useDialogA11y(dialogRef, { onClose: close })

onMounted(() => {
  void load()
})
</script>

<template>
  <div class="dialog-backdrop" @click.self="close">
    <section
      ref="dialogRef"
      class="dialog-card wordbook-dialog wordbook-detail-dialog"
      tabindex="-1"
      role="dialog"
      aria-modal="true"
      aria-labelledby="wordbook-detail-title"
    >
      <header class="dialog-heading">
        <div>
          <p class="eyebrow">只读词书详情</p>
          <h2 id="wordbook-detail-title">{{ detail?.wordbook.name ?? '词书详情' }}</h2>
        </div>
        <button class="icon-button" type="button" aria-label="关闭词书详情" @click="close">×</button>
      </header>

      <LoadingState v-if="loading && !detail" label="正在读取词书与词条…" />
      <ErrorNotice v-else-if="error" :error="error" retry-label="重新读取" @retry="load(cursor)" />

      <template v-else-if="detail && entries">
        <div class="wordbook-detail-meta">
          <span class="wordbook-pill" :class="`wordbook-pill--${detail.wordbook.visibility}`">
            {{ detail.wordbook.visibility === 'organization' ? '组织词书' : '我的私有词书' }}
          </span>
          <span class="wordbook-status" :class="`wordbook-status--${detail.wordbook.status}`">
            {{ statusLabel(detail.wordbook.status) }}
          </span>
          <span v-if="detail.wordbook.is_active" class="wordbook-status wordbook-status--active">当前主词书</span>
        </div>

        <p v-if="detail.wordbook.description" class="lead">{{ detail.wordbook.description }}</p>
        <dl class="wordbook-detail-facts">
          <div>
            <dt>词条数</dt>
            <dd>{{ detail.wordbook.entry_count.toLocaleString('zh-CN') }}</dd>
          </div>
          <div>
            <dt>更新时间</dt>
            <dd>{{ formatDate(detail.wordbook.updated_at) }}</dd>
          </div>
          <div>
            <dt>所有者</dt>
            <dd>{{ detail.wordbook.owner_display_name || '组织共享' }}</dd>
          </div>
        </dl>

        <div class="section-heading wordbook-entry-heading">
          <div>
            <h3>词条</h3>
            <p class="field-hint">导入后的词条为只读，本任务不提供逐词编辑。</p>
          </div>
          <span class="count-pill">本页 {{ entries.items.length }} 条</span>
        </div>

        <div v-if="entries.items.length === 0" class="empty-state">
          <strong>暂时没有可显示词条</strong>
          <p>如果词书仍在导入，请稍后刷新；失败原因以服务端任务状态为准。</p>
        </div>

        <ol v-else class="wordbook-entry-list">
          <li v-for="entry in entries.items" :key="entry.id">
            <div class="wordbook-entry-word">
              <strong>{{ entry.headword }}</strong>
              <span v-if="entry.phonetic">{{ entry.phonetic }}</span>
            </div>
            <div class="wordbook-entry-definition">
              <span v-if="entry.part_of_speech" class="part-of-speech">{{ entry.part_of_speech }}</span>
              <p v-for="definition in entry.definitions" :key="definition">{{ definition }}</p>
            </div>
            <ul v-if="entry.examples.length" class="wordbook-examples">
              <li v-for="example in entry.examples" :key="example.sentence">
                <p>{{ example.sentence }}</p>
                <p v-if="example.translation" class="muted">{{ example.translation }}</p>
              </li>
            </ul>
          </li>
        </ol>

        <div class="pagination">
          <button
            class="button-secondary button-small"
            type="button"
            :disabled="cursorHistory.length === 0 || loading"
            @click="previousPage"
          >
            上一页
          </button>
          <button
            class="button-secondary button-small"
            type="button"
            :disabled="!entries.has_more || !entries.next_cursor || loading"
            @click="nextPage"
          >
            {{ loading ? '读取中…' : '下一页' }}
          </button>
        </div>
      </template>
    </section>
  </div>
</template>