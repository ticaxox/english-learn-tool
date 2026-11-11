<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import {
  getWordbookDetail,
  type Wordbook,
  type WordbookDetail,
  type WordbookStatus,
} from '../api/wordbooks'
import { useDialogA11y } from '../composables/useDialogA11y'
import ErrorNotice from './ErrorNotice.vue'
import LoadingState from './LoadingState.vue'
import SpeakButton from './SpeakButton.vue'
import ModeArt from './ModeArt.vue'
import { wordbookCover } from '../assets/halloween'

const props = withDefaults(defineProps<{
  wordbookId: string
  book?: Wordbook | null
  canActivate?: boolean
  canExport?: boolean
  canDelete?: boolean
  activating?: boolean
}>(), {
  book: null,
  canActivate: false,
  canExport: false,
  canDelete: false,
  activating: false,
})

const emit = defineEmits<{
  (event: 'close'): void
  (event: 'activate'): void
  (event: 'export'): void
  (event: 'delete'): void
}>()

const PAGE_SIZE = 50
const detail = ref<WordbookDetail | null>(null)
const loading = ref(false)
const error = ref<unknown>(null)
const dialogRef = ref<HTMLElement | null>(null)
let loadRequestId = 0

const hasPrevious = computed(() => Boolean(detail.value && detail.value.offset > 0))
const hasNext = computed(() => Boolean(
  detail.value
  && detail.value.offset + detail.value.entries.length < detail.value.total_entries,
))
const pageSummary = computed(() => {
  if (!detail.value || detail.value.total_entries === 0) {
    return '0 条'
  }
  const start = detail.value.offset + 1
  const end = Math.min(detail.value.offset + detail.value.entries.length, detail.value.total_entries)
  return `${start}–${end} / 共 ${detail.value.total_entries.toLocaleString('zh-CN')} 条`
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

function formatDate(value: string): string {
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString('zh-CN', { year: 'numeric', month: 'long', day: 'numeric', hour: '2-digit', minute: '2-digit' })
}

function ownerLabel(_ownerId: string | null, visibility: 'organization' | 'private'): string {
  return visibility === 'organization' ? '组织共享' : '仅自己可见'
}

async function load(offset = detail.value?.offset ?? 0): Promise<void> {
  const requestId = ++loadRequestId
  loading.value = true
  error.value = null
  try {
    const result = await getWordbookDetail(props.wordbookId, offset, PAGE_SIZE)
    if (requestId !== loadRequestId) {
      return
    }
    detail.value = result
  } catch (requestError) {
    if (requestId !== loadRequestId) {
      return
    }
    error.value = requestError
  } finally {
    if (requestId === loadRequestId) {
      loading.value = false
    }
  }
}

async function previousPage(): Promise<void> {
  if (!detail.value || !hasPrevious.value || loading.value) {
    return
  }
  await load(Math.max(0, detail.value.offset - PAGE_SIZE))
}

async function nextPage(): Promise<void> {
  if (!detail.value || !hasNext.value || loading.value) {
    return
  }
  await load(detail.value.offset + detail.value.limit)
}

function close(): void {
  emit('close')
}

useDialogA11y(dialogRef, { onClose: close })

onMounted(() => {
  void load(0)
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
      <header class="dialog-heading wordbook-detail-heading">
        <!-- The book itself, at a size where the drawn cover still reads. -->
        <ModeArt
          class="wordbook-detail-cover"
          :day="wordbookCover.day"
          :night="wordbookCover.night"
        />
        <div>
          <p class="eyebrow">只读词书详情</p>
          <h2 id="wordbook-detail-title">{{ detail?.wordbook.name ?? '词书详情' }}</h2>
        </div>
        <div v-if="book" class="wordbook-detail-actions">
          <DivButton v-if="canActivate" class="button-small" type="button" :disabled="activating" @click="emit('activate')">
            {{ activating ? '激活中…' : '设为主词书' }}
          </DivButton>
          <DivButton v-else class="button-secondary button-small" type="button" disabled>已在使用</DivButton>
          <DivButton v-if="canExport" class="button-secondary button-small" type="button" @click="emit('export')">导出</DivButton>
          <DivButton v-if="canDelete" class="button-danger button-small" type="button" @click="emit('delete')">删除</DivButton>
        </div>
        <DivButton class="icon-button" type="button" aria-label="关闭词书详情" @click="close">×</DivButton>
      </header>

      <LoadingState v-if="loading && !detail" label="正在读取词书与词条…" />
      <ErrorNotice v-else-if="error && !detail" :error="error" retry-label="重新读取" @retry="load(0)" />

      <template v-else-if="detail">
        <ErrorNotice v-if="error" :error="error" retry-label="重新读取当前页" @retry="load(detail.offset)" />

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

        <dl class="wordbook-detail-facts wordbook-detail-facts--four">
          <div>
            <dt>词条数</dt>
            <dd>{{ detail.wordbook.entry_count.toLocaleString('zh-CN') }}</dd>
          </div>
          <div>
            <dt>版本</dt>
            <dd>{{ detail.wordbook.version }}</dd>
          </div>
          <div>
            <dt>可见范围</dt>
            <dd>{{ ownerLabel(detail.wordbook.owner_id, detail.wordbook.visibility) }}</dd>
          </div>
          <div>
            <dt>更新时间</dt>
            <dd>{{ formatDate(detail.wordbook.updated_at) }}</dd>
          </div>
        </dl>

        <div class="section-heading wordbook-entry-heading">
          <div>
            <h3>词条</h3>
            <p class="field-hint">词条内容来自词书文件；暂不支持逐词编辑。</p>
          </div>
          <span class="count-pill">本页 {{ detail.entries.length }} 条</span>
        </div>

        <div v-if="detail.entries.length === 0" class="empty-state">
          <strong>暂时没有可显示词条</strong>
          <p>如果词书仍在导入，请稍后刷新；失败原因以服务端任务状态为准。</p>
        </div>

        <div role="list" v-else class="wordbook-entry-list" :aria-busy="loading">
          <div role="listitem" v-for="entry in detail.entries" :key="entry.id">
            <div class="wordbook-entry-word">
              <strong>{{ entry.headword }}</strong>
              <SpeakButton :text="entry.headword" />
              <span v-if="entry.phonetic">{{ entry.phonetic }}</span>
              <span class="wordbook-entry-normalized">{{ entry.normalized_headword }}</span>
            </div>

            <div class="wordbook-entry-definitions">
              <p v-if="entry.definitions.length === 0" class="muted">服务端未返回释义。</p>
              <article
                v-for="(definition, definitionIndex) in entry.definitions"
                :key="`${entry.id}-definition-${definitionIndex}`"
                class="wordbook-definition"
              >
                <span v-if="definition.part_of_speech" class="part-of-speech">{{ definition.part_of_speech }}</span>
                <p v-if="definition.definition_en" class="wordbook-definition-en">{{ definition.definition_en }}</p>
                <p v-if="definition.definition_zh" class="wordbook-definition-zh">{{ definition.definition_zh }}</p>
                <div role="list" v-if="definition.examples.length" class="wordbook-examples">
                  <div role="listitem" v-for="(example, exampleIndex) in definition.examples" :key="`${entry.id}-${definitionIndex}-example-${exampleIndex}`">
                    <p>{{ example.example_en }}</p>
                    <p v-if="example.example_zh" class="muted">{{ example.example_zh }}</p>
                  </div>
                </div>
              </article>
            </div>
          </div>
        </div>

        <div class="pagination" aria-label="词条分页">
          <DivButton class="button-secondary button-small" type="button" :disabled="!hasPrevious || loading" @click="previousPage">上一页</DivButton>
          <span>{{ pageSummary }}</span>
          <DivButton class="button-secondary button-small" type="button" :disabled="!hasNext || loading" @click="nextPage">{{ loading ? '读取中…' : '下一页' }}</DivButton>
        </div>
      </template>
    </section>
  </div>
</template>
