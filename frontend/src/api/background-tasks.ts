/**
 * Background pre-generation tasks: the practice sets being prepared ahead of
 * time. The learner can inspect, retry a failure, or delete a slot.
 */
import { apiClient } from './client'
import type { PracticeType } from './practice'

export type BackgroundTaskStatus = 'generating' | 'ready' | 'failed'

export interface BackgroundTask {
  id: string
  practiceType: PracticeType
  questionCount: number
  status: BackgroundTaskStatus
  attempts: number
  errorCode: string | null
  errorMessage: string | null
  createdAt: string
  updatedAt: string
}

function record(value: unknown, context: string): Record<string, unknown> {
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    throw new Error(`${context}格式不正确。`)
  }
  return value as Record<string, unknown>
}

function text(value: unknown, context: string): string {
  if (typeof value !== 'string') throw new Error(`${context}缺少文本字段。`)
  return value
}

function parseTask(value: unknown, index: number): BackgroundTask {
  const context = `后台任务第 ${index + 1} 条`
  const body = record(value, context)
  const status = text(body.status, context) as BackgroundTaskStatus
  if (!['generating', 'ready', 'failed'].includes(status)) {
    throw new Error(`${context}状态无法识别。`)
  }
  return {
    id: text(body.id, context),
    practiceType: text(body.practice_type, context) as BackgroundTask['practiceType'],
    questionCount: Number(body.question_count),
    status,
    attempts: Number(body.attempts),
    errorCode: typeof body.error_code === 'string' ? body.error_code : null,
    errorMessage: typeof body.error_message === 'string' ? body.error_message : null,
    createdAt: text(body.created_at, context),
    updatedAt: text(body.updated_at, context),
  }
}

function parseList(payload: unknown): BackgroundTask[] {
  const body = record(payload, '后台任务列表响应')
  return Array.isArray(body.items) ? body.items.map((item, index) => parseTask(item, index)) : []
}

export async function listBackgroundTasks(): Promise<BackgroundTask[]> {
  return parseList(await apiClient.get('/me/ai/background-tasks'))
}

export async function retryBackgroundTask(id: string): Promise<BackgroundTask> {
  const payload = await apiClient.post(
    `/me/ai/background-tasks/${encodeURIComponent(id)}/retry`,
    undefined,
    { retryCount: 0 },
  )
  return parseTask(payload, 0)
}

export async function deleteBackgroundTask(id: string): Promise<void> {
  await apiClient.delete<void>(`/me/ai/background-tasks/${encodeURIComponent(id)}`, {
    retryCount: 0,
  })
}
