import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { apiClient } from '../api/client'
import {
  createProvider,
  fetchAiUsage,
  fetchProviderModels,
  parsePromptDetail,
  parseProviderList,
  testProvider,
  updateProvider,
  updatePrompt,
  type ProviderCreateInput,
} from '../api/ai-admin'
import { ContractError } from '../api/errors'

const providerPayload = {
  id: '18bcc7e0-40ba-4df8-a63d-7b6c3ee6e377',
  name: 'Primary OpenAI-compatible',
  base_url: 'https://provider.example/v1',
  api_key_masked: 'sk-••••••••1234',
  model_id: 'model-a',
  priority: 10,
  is_default: true,
  timeout_seconds: 60,
  enabled: true,
  custom_headers: { 'X-Organization': 'learning' },
  last_test_status: 'succeeded',
  last_test_error_code: null,
  last_test_at: '2026-10-23T03:00:00Z',
  last_test_latency_ms: 88,
  created_at: '2026-10-23T02:00:00Z',
  updated_at: '2026-10-23T03:00:00Z',
}

function jsonResponse(payload: unknown, status = 200, requestId = 'req-ai-admin'): Response {
  return new Response(JSON.stringify(payload), {
    status,
    headers: { 'Content-Type': 'application/json', 'X-Request-ID': requestId },
  })
}

describe('admin AI API contract', () => {
  beforeEach(() => {
    apiClient.clearCredentials()
    localStorage.clear()
    sessionStorage.clear()
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('parses masked provider lists and rejects malformed payloads', () => {
    const providers = parseProviderList({ items: [providerPayload] })
    expect(providers[0]).toMatchObject({
      name: 'Primary OpenAI-compatible',
      apiKeyMasked: 'sk-••••••••1234',
      isDefault: true,
      timeoutSeconds: 60,
    })
    expect(providers[0]).not.toHaveProperty('api_key')
    expect(() => parseProviderList({ items: 'bad' })).toThrow(ContractError)
  })

  it('sends a new key only in the request body and never stores it', async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(providerPayload, 201))
    vi.stubGlobal('fetch', fetchMock)
    const input: ProviderCreateInput = {
      name: 'Primary OpenAI-compatible',
      baseUrl: 'https://provider.example/v1',
      apiKey: 'sk-test-secret-1234',
      modelId: 'model-a',
      priority: 10,
      isDefault: true,
      timeoutSeconds: 60,
      enabled: true,
      customHeaders: { 'X-Organization': 'learning' },
    }
    const created = await createProvider(input)
    expect(created.id).toBe(providerPayload.id)

    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit]
    expect(url).toBe('/api/v1/admin/ai/providers')
    expect(url).not.toContain(input.apiKey)
    const body = JSON.parse(String(init.body)) as Record<string, unknown>
    expect(body.api_key).toBe(input.apiKey)
    expect(body.base_url).toBe(input.baseUrl)
    expect(localStorage.length).toBe(0)
    expect(sessionStorage.length).toBe(0)
  })

  it('omits a preserved key and sends a replacement only when explicitly provided', async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(jsonResponse(providerPayload))
      .mockResolvedValueOnce(jsonResponse(providerPayload))
    vi.stubGlobal('fetch', fetchMock)

    await updateProvider(providerPayload.id, { modelId: 'model-b' })
    let body = JSON.parse(String((fetchMock.mock.calls[0][1] as RequestInit).body))
    expect(body).toEqual({ model_id: 'model-b' })
    expect(body).not.toHaveProperty('api_key')

    await updateProvider(providerPayload.id, { apiKey: 'sk-replacement-secret' })
    body = JSON.parse(String((fetchMock.mock.calls[1][1] as RequestInit).body))
    expect(body).toEqual({ api_key: 'sk-replacement-secret' })
  })

  it('surfaces real connection failure and model fallback payloads', async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(jsonResponse({
        success: false,
        status: 'failed',
        latency_ms: 15000,
        error_code: 'AI_PROVIDER_TIMEOUT',
        error_message: 'Provider timed out.',
        models: [],
      }))
      .mockResolvedValueOnce(jsonResponse({
        success: false,
        models: [],
        error_code: 'AI_MODEL_LIST_UNSUPPORTED',
        error_message: 'Manual model id required.',
      }))
    vi.stubGlobal('fetch', fetchMock)

    const test = await testProvider(providerPayload.id)
    expect(test).toMatchObject({ success: false, errorCode: 'AI_PROVIDER_TIMEOUT', latencyMs: 15000 })
    const models = await fetchProviderModels(providerPayload.id)
    expect(models).toMatchObject({ success: false, errorCode: 'AI_MODEL_LIST_UNSUPPORTED' })
  })

  it('keeps 429 and request ids visible through the shared API client', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse({
      code: 'AI_RATE_LIMITED',
      message: 'Too many requests.',
      details: null,
      request_id: 'rate-ai',
    }, 429, 'rate-ai')))

    await expect(testProvider(providerPayload.id)).rejects.toMatchObject({
      status: 429,
      code: 'AI_RATE_LIMITED',
      requestId: 'rate-ai',
    })
  })

  it('parses prompt details and sends only the documented PUT fields', async () => {
    const detail = {
      key: 'practice_generation',
      name: '练习生成',
      summary: 'Generate practice questions.',
      template: 'Return JSON: {{context}}',
      updated_at: '2026-10-23T03:00:00Z',
    }
    expect(parsePromptDetail(detail).key).toBe('practice_generation')
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(detail))
    vi.stubGlobal('fetch', fetchMock)
    await updatePrompt('practice_generation', {
      name: '练习生成',
      summary: 'Generate practice questions.',
      template: 'Return JSON: {{context}}',
    })
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit]
    expect(url).toBe('/api/v1/admin/ai/prompts/practice_generation')
    expect(init.method).toBe('PUT')
    expect(JSON.parse(String(init.body))).toEqual({
      name: '练习生成',
      summary: 'Generate practice questions.',
      template: 'Return JSON: {{context}}',
    })
  })

  it('parses privacy-safe aggregate usage', async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({
      date_from: '2026-10-01',
      date_to: '2026-10-23',
      total_jobs: 12,
      active_jobs: 2,
      quotas: [{
        quota_kind: 'question_generation',
        limit_per_user: 20,
        users_with_usage: 3,
        consumed: 9,
        reserved: 1,
        released: 0,
      }],
      tasks: [{ task_type: 'practice_generation', status: 'failed', count: 2 }],
      providers: [{ provider_id: providerPayload.id, provider_name: providerPayload.name, jobs: 12, succeeded: 10, failed: 2 }],
      private_answers: ['must not surface'],
    }))
    vi.stubGlobal('fetch', fetchMock)
    const usage = await fetchAiUsage('2026-10-01', '2026-10-23')
    expect(usage).toMatchObject({ totalJobs: 12, activeJobs: 2 })
    expect(usage.quotas[0].consumed).toBe(9)
    expect(usage).not.toHaveProperty('private_answers')
    const [url] = fetchMock.mock.calls[0] as [string]
    expect(url).toBe('/api/v1/admin/ai/usage?date_from=2026-10-01&date_to=2026-10-23')
  })
})