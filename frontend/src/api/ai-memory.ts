/**
 * AI memory: one editable document the coach reads before answering.
 */
import { apiClient } from './client'

export interface AiMemoryDocument {
  content: string
  updatedAt: string | null
}

function parseDocument(payload: unknown): AiMemoryDocument {
  if (!payload || typeof payload !== 'object' || Array.isArray(payload)) {
    throw new Error('AI 记忆文档响应格式不正确。')
  }
  const body = payload as Record<string, unknown>
  if (typeof body.content !== 'string') {
    throw new Error('AI 记忆文档响应缺少内容。')
  }
  return {
    content: body.content,
    updatedAt: typeof body.updated_at === 'string' ? body.updated_at : null,
  }
}

export async function getAiMemoryDocument(): Promise<AiMemoryDocument> {
  return parseDocument(await apiClient.get('/me/ai/memory'))
}

export async function saveAiMemoryDocument(content: string): Promise<AiMemoryDocument> {
  return parseDocument(await apiClient.put('/me/ai/memory', { content }, { retryCount: 0 }))
}
