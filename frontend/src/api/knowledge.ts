/** Admin-maintained reference knowledge (exam papers) and read-only search. */
import { apiClient } from './client'

export type KnowledgeSourceType = 'exam' | 'wordbook'
export type KnowledgeStatus = 'draft' | 'indexing' | 'ready' | 'failed' | 'archived'

export interface KnowledgeDocument {
  id: string
  sourceType: KnowledgeSourceType
  title: string
  metadata: Record<string, unknown>
  status: KnowledgeStatus
  chunkCount: number
  embeddingModel: string | null
  errorMessage: string | null
  createdAt: string
  updatedAt: string
}

export interface KnowledgeHit {
  documentId: string
  title: string
  content: string
  score: number
}

function record(value: unknown, context: string): Record<string, unknown> {
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    throw new Error(`${context} 格式不正确。`)
  }
  return value as Record<string, unknown>
}

function parseDocument(value: unknown): KnowledgeDocument {
  const body = record(value, '知识库文档')
  return {
    id: String(body.id ?? ''),
    sourceType: (body.source_type === 'wordbook' ? 'wordbook' : 'exam') as KnowledgeSourceType,
    title: String(body.title ?? ''),
    metadata: (body.metadata as Record<string, unknown>) ?? {},
    status: String(body.status ?? 'draft') as KnowledgeStatus,
    chunkCount: Number(body.chunk_count ?? 0),
    embeddingModel: typeof body.embedding_model === 'string' ? body.embedding_model : null,
    errorMessage: typeof body.error_message === 'string' ? body.error_message : null,
    createdAt: String(body.created_at ?? ''),
    updatedAt: String(body.updated_at ?? ''),
  }
}

export async function listKnowledgeDocuments(): Promise<KnowledgeDocument[]> {
  const payload = record(await apiClient.get('/admin/knowledge'), '知识库列表')
  if (!Array.isArray(payload.items)) throw new Error('知识库列表缺少 items 数组。')
  return payload.items.map(parseDocument)
}

export async function importKnowledgeDocument(input: {
  title: string
  content: string
  sourceType?: KnowledgeSourceType
  metadata?: Record<string, unknown>
}): Promise<KnowledgeDocument> {
  const payload = await apiClient.post(
    '/admin/knowledge',
    {
      title: input.title,
      content: input.content,
      source_type: input.sourceType ?? 'exam',
      metadata: input.metadata ?? {},
    },
    { retryCount: 0 },
  )
  return parseDocument(payload)
}

export async function updateKnowledgeDocument(
  id: string,
  input: { title?: string; content?: string; published?: boolean },
): Promise<KnowledgeDocument> {
  const payload = await apiClient.patch(
    `/admin/knowledge/${encodeURIComponent(id)}`,
    input,
    { retryCount: 0 },
  )
  return parseDocument(payload)
}

export async function archiveKnowledgeDocument(id: string): Promise<void> {
  await apiClient.delete(`/admin/knowledge/${encodeURIComponent(id)}`, { retryCount: 0 })
}

export async function searchKnowledge(query: string, limit = 6): Promise<KnowledgeHit[]> {
  const params = new URLSearchParams({ query, limit: String(limit) })
  const payload = record(await apiClient.get(`/knowledge/search?${params}`), '检索结果')
  if (!Array.isArray(payload.items)) throw new Error('检索结果缺少 items 数组。')
  return payload.items.map((item) => {
    const body = record(item, '检索命中')
    return {
      documentId: String(body.document_id ?? ''),
      title: String(body.title ?? ''),
      content: String(body.content ?? ''),
      score: Number(body.score ?? 0),
    }
  })
}
