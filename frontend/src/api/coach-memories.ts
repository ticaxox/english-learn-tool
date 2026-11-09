/** Typed memories the coach keeps about the learner. */
import { apiClient } from './client'

export type CoachMemoryKind = 'preference' | 'goal' | 'constraint' | 'fact' | 'note'
export type CoachMemoryStatus = 'active' | 'superseded' | 'archived'
export type CoachMemorySource = 'user_explicit' | 'coach_inferred' | 'imported'

export interface CoachMemory {
  id: string
  kind: CoachMemoryKind
  subjectKey: string | null
  content: string
  source: CoachMemorySource
  status: CoachMemoryStatus
  importance: number
  createdAt: string
  updatedAt: string
  lastUsedAt: string | null
}

export const COACH_MEMORY_KIND_LABELS: Record<CoachMemoryKind, string> = {
  preference: '偏好',
  goal: '目标',
  constraint: '约束',
  fact: '事实',
  note: '笔记',
}

export const COACH_MEMORY_SOURCE_LABELS: Record<CoachMemorySource, string> = {
  user_explicit: '你说的',
  coach_inferred: '教练推断',
  imported: '导入',
}

function record(value: unknown, context: string): Record<string, unknown> {
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    throw new Error(`${context} 格式不正确。`)
  }
  return value as Record<string, unknown>
}

function text(value: unknown, context: string): string {
  if (typeof value !== 'string') throw new Error(`${context} 缺少文本。`)
  return value
}

function parseMemory(value: unknown): CoachMemory {
  const body = record(value, '教练记忆')
  const kind = text(body.kind, 'kind') as CoachMemoryKind
  const source = text(body.source, 'source') as CoachMemorySource
  return {
    id: text(body.id, 'id'),
    kind,
    subjectKey: typeof body.subject_key === 'string' ? body.subject_key : null,
    content: text(body.content, 'content'),
    source,
    status: text(body.status, 'status') as CoachMemoryStatus,
    importance: Number(body.importance ?? 3),
    createdAt: text(body.created_at, 'created_at'),
    updatedAt: text(body.updated_at, 'updated_at'),
    lastUsedAt: typeof body.last_used_at === 'string' ? body.last_used_at : null,
  }
}

export async function listCoachMemories(includeHistory = false): Promise<CoachMemory[]> {
  const query = includeHistory ? '?include_history=true' : ''
  const payload = record(await apiClient.get(`/me/memories${query}`), '教练记忆列表')
  if (!Array.isArray(payload.items)) throw new Error('教练记忆列表缺少 items 数组。')
  return payload.items.map(parseMemory)
}

export async function createCoachMemory(input: {
  kind: CoachMemoryKind
  content: string
  subjectKey?: string | null
  importance?: number
}): Promise<CoachMemory> {
  const payload = await apiClient.post(
    '/me/memories',
    {
      kind: input.kind,
      content: input.content,
      subject_key: input.subjectKey ?? null,
      importance: input.importance ?? 3,
    },
    { retryCount: 0 },
  )
  return parseMemory(payload)
}

export async function updateCoachMemory(
  id: string,
  input: { content?: string; kind?: CoachMemoryKind; importance?: number },
): Promise<CoachMemory> {
  const payload = await apiClient.patch(`/me/memories/${encodeURIComponent(id)}`, input, {
    retryCount: 0,
  })
  return parseMemory(payload)
}

export async function deleteCoachMemory(id: string): Promise<void> {
  await apiClient.delete(`/me/memories/${encodeURIComponent(id)}`, { retryCount: 0 })
}
