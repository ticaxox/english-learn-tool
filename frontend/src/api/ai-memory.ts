/**
 * AI memory: durable notes the coach reads before answering.
 *
 * Every field is validated at the boundary so a schema drift shows up as a
 * readable error instead of a half-rendered panel.
 */
import { apiClient } from './client'

export type AiMemoryKind = 'profile' | 'practice' | 'chat' | 'preference' | 'custom'
export type AiMemorySource = 'auto' | 'user'

export interface AiMemory {
  id: string
  kind: AiMemoryKind
  content: string
  source: AiMemorySource
  pinned: boolean
  createdAt: string
  updatedAt: string
  lastUsedAt: string | null
}

export interface AiMemoryList {
  items: AiMemory[]
  counts: Record<string, number>
}

export interface AiMemoryCreateInput {
  kind: AiMemoryKind
  content: string
}

export interface AiMemoryUpdateInput {
  kind?: AiMemoryKind
  content?: string
  pinned?: boolean
}

const KINDS: AiMemoryKind[] = ['profile', 'practice', 'chat', 'preference', 'custom']
const SOURCES: AiMemorySource[] = ['auto', 'user']

function record(value: unknown, context: string): Record<string, unknown> {
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    throw new Error(`${context}格式不正确。`)
  }
  return value as Record<string, unknown>
}

function text(value: unknown, context: string, key: string): string {
  if (typeof value !== 'string') {
    throw new Error(`${context}缺少 ${key}。`)
  }
  return value
}

function nullableText(value: unknown): string | null {
  return typeof value === 'string' ? value : null
}

function parseMemory(value: unknown, index: number): AiMemory {
  const context = `AI 记忆第 ${index + 1} 条`
  const body = record(value, context)
  const kind = text(body.kind, context, 'kind')
  const source = text(body.source, context, 'source')
  if (!KINDS.includes(kind as AiMemoryKind)) {
    throw new Error(`${context}的类型无法识别。`)
  }
  if (!SOURCES.includes(source as AiMemorySource)) {
    throw new Error(`${context}的来源无法识别。`)
  }
  return {
    id: text(body.id, context, 'id'),
    kind: kind as AiMemoryKind,
    content: text(body.content, context, 'content'),
    source: source as AiMemorySource,
    pinned: body.pinned === true,
    createdAt: text(body.created_at, context, 'created_at'),
    updatedAt: text(body.updated_at, context, 'updated_at'),
    lastUsedAt: nullableText(body.last_used_at),
  }
}

function parseList(payload: unknown): AiMemoryList {
  const body = record(payload, 'AI 记忆列表响应')
  const items = Array.isArray(body.items)
    ? body.items.map((item, index) => parseMemory(item, index))
    : []
  const counts: Record<string, number> = {}
  if (body.counts && typeof body.counts === 'object') {
    for (const [key, value] of Object.entries(body.counts as Record<string, unknown>)) {
      if (typeof value === 'number') counts[key] = value
    }
  }
  return { items, counts }
}

export async function listAiMemories(kind?: AiMemoryKind): Promise<AiMemoryList> {
  const query = kind ? `?kind=${encodeURIComponent(kind)}` : ''
  return parseList(await apiClient.get(`/me/ai/memories${query}`))
}

export async function createAiMemory(input: AiMemoryCreateInput): Promise<AiMemory> {
  const payload = await apiClient.post('/me/ai/memories', {
    kind: input.kind,
    content: input.content,
  }, { retryCount: 0 })
  return parseMemory(payload, 0)
}

export async function updateAiMemory(id: string, input: AiMemoryUpdateInput): Promise<AiMemory> {
  const payload = await apiClient.patch(`/me/ai/memories/${encodeURIComponent(id)}`, {
    kind: input.kind,
    content: input.content,
    pinned: input.pinned,
  }, { retryCount: 0 })
  return parseMemory(payload, 0)
}

export async function deleteAiMemory(id: string): Promise<void> {
  await apiClient.delete<void>(`/me/ai/memories/${encodeURIComponent(id)}`, { retryCount: 0 })
}

export async function clearAutoAiMemories(): Promise<number> {
  const payload = record(
    await apiClient.post('/me/ai/memories/clear-auto', undefined, { retryCount: 0 }),
    'AI 记忆清理响应',
  )
  return typeof payload.deleted_count === 'number' ? payload.deleted_count : 0
}
