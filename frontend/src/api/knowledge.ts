/** Admin-maintained reference knowledge (exam papers) and read-only search. */
import { apiClient } from './client'

export type KnowledgeSourceType = 'exam'
export type KnowledgeStatus = 'draft' | 'indexing' | 'ready' | 'failed' | 'archived'
export type KnowledgeScope = 'global' | 'personal'
export type KnowledgeDifficulty = 'GAOKAO' | 'CET4' | 'CET6' | 'POSTGRAD' | 'IELTS' | 'TOEFL'

export const KNOWLEDGE_DIFFICULTY_LABELS: Record<KnowledgeDifficulty, string> = {
  GAOKAO: '高考',
  CET4: '四级',
  CET6: '六级',
  POSTGRAD: '考研',
  IELTS: '雅思',
  TOEFL: '托福',
}

export type KnowledgeLevel = KnowledgeDifficulty

export interface KnowledgeFolder {
  id: string
  parentId: string | null
  scope: KnowledgeScope
  difficulty: KnowledgeDifficulty | null
  name: string
  documentCount: number
  writable: boolean
  isGeneral: boolean
  createdAt: string
  updatedAt: string
}

export interface KnowledgeDocument {
  id: string
  folderId: string | null
  sourceType: KnowledgeSourceType
  title: string
  metadata: Record<string, unknown>
  status: KnowledgeStatus
  chunkCount: number
  snippet: string
  embeddingModel: string | null
  errorMessage: string | null
  createdAt: string
  updatedAt: string
}

export interface KnowledgeDocumentDetail extends KnowledgeDocument {
  content: string
  folders: string | null
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

function parseFolder(value: unknown): KnowledgeFolder {
  const body = record(value, '知识库文件夹')
  return {
    id: String(body.id ?? ''),
    parentId: typeof body.parent_id === 'string' ? body.parent_id : null,
    scope: (body.scope === 'global' ? 'global' : 'personal') as KnowledgeScope,
    difficulty:
      typeof body.difficulty === 'string' ? (body.difficulty as KnowledgeDifficulty) : null,
    name: String(body.name ?? ''),
    documentCount: Number(body.document_count ?? 0),
    writable: body.writable === true,
    isGeneral: body.is_general === true,
    createdAt: String(body.created_at ?? ''),
    updatedAt: String(body.updated_at ?? ''),
  }
}

function parseDocument(value: unknown): KnowledgeDocument {
  const body = record(value, '知识库文档')
  return {
    id: String(body.id ?? ''),
    folderId: typeof body.folder_id === 'string' ? body.folder_id : null,
    sourceType: 'exam' as KnowledgeSourceType,
    title: String(body.title ?? ''),
    metadata: (body.metadata as Record<string, unknown>) ?? {},
    status: String(body.status ?? 'draft') as KnowledgeStatus,
    chunkCount: Number(body.chunk_count ?? 0),
    snippet: typeof body.snippet === 'string' ? body.snippet : '',
    embeddingModel: typeof body.embedding_model === 'string' ? body.embedding_model : null,
    errorMessage: typeof body.error_message === 'string' ? body.error_message : null,
    createdAt: String(body.created_at ?? ''),
    updatedAt: String(body.updated_at ?? ''),
  }
}

export async function listKnowledgeFolders(): Promise<KnowledgeFolder[]> {
  const payload = record(await apiClient.get('/knowledge'), '知识库书架')
  if (!Array.isArray(payload.items)) throw new Error('知识库书架缺少 items 数组。')
  return payload.items.map(parseFolder)
}

/** `level` is the exam a shelf is for; the wire calls it `difficulty`. */
export async function createKnowledgeFolder(input: {
  name: string
  scope?: KnowledgeScope
  level?: KnowledgeDifficulty | null
  parentId?: string | null
}): Promise<KnowledgeFolder> {
  const payload = await apiClient.post(
    '/knowledge/folders',
    {
      name: input.name,
      scope: input.scope ?? 'personal',
      difficulty: input.level ?? null,
      parent_id: input.parentId ?? null,
    },
    { retryCount: 0 },
  )
  return parseFolder(payload)
}

export async function renameKnowledgeFolder(id: string, name: string): Promise<KnowledgeFolder> {
  const payload = await apiClient.patch(
    `/knowledge/folders/${encodeURIComponent(id)}`,
    { name },
    { retryCount: 0 },
  )
  return parseFolder(payload)
}

export async function deleteKnowledgeFolder(id: string): Promise<void> {
  await apiClient.delete(`/knowledge/folders/${encodeURIComponent(id)}`, { retryCount: 0 })
}

export async function listFolderDocuments(folderId: string): Promise<KnowledgeDocument[]> {
  const payload = record(
    await apiClient.get(`/knowledge/folders/${encodeURIComponent(folderId)}/documents`),
    '书架文档',
  )
  if (!Array.isArray(payload.items)) throw new Error('书架文档缺少 items 数组。')
  return payload.items.map(parseDocument)
}

export async function importIntoFolder(
  folderId: string,
  input: { title: string; content: string },
): Promise<KnowledgeDocument> {
  const payload = await apiClient.post(
    `/knowledge/folders/${encodeURIComponent(folderId)}/documents`,
    {
      title: input.title,
      content: input.content,
      source_type: 'exam',
      metadata: {},
    },
    { retryCount: 0 },
  )
  return parseDocument(payload)
}

export async function getKnowledgeDocument(id: string): Promise<KnowledgeDocumentDetail> {
  const payload = record(
    await apiClient.get(`/knowledge/documents/${encodeURIComponent(id)}`),
    '知识库文档',
  )
  return {
    ...parseDocument(payload),
    content: String(payload.content ?? ''),
    folders: typeof payload.folders === 'string' ? payload.folders : null,
  }
}

export async function renameKnowledgeDocument(id: string, title: string): Promise<KnowledgeDocument> {
  const payload = await apiClient.patch(
    `/knowledge/documents/${encodeURIComponent(id)}`,
    { title },
    { retryCount: 0 },
  )
  return parseDocument(payload)
}

export async function deleteKnowledgeDocument(id: string): Promise<void> {
  await apiClient.delete(`/knowledge/documents/${encodeURIComponent(id)}`, { retryCount: 0 })
}

export async function listKnowledgeDocuments(): Promise<KnowledgeDocument[]> {
  const payload = record(await apiClient.get('/admin/knowledge'), '知识库列表')
  if (!Array.isArray(payload.items)) throw new Error('知识库列表缺少 items 数组。')
  return payload.items.map(parseDocument)
}

export async function importKnowledgeDocument(input: {
  title: string
  content: string
  metadata?: Record<string, unknown>
}): Promise<KnowledgeDocument> {
  const payload = await apiClient.post(
    '/admin/knowledge',
    {
      title: input.title,
      content: input.content,
      // Only exam papers are indexed; the server rejects anything else.
      source_type: 'exam',
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
