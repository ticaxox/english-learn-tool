import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { apiClient } from '../api/client'
import {
  createPersonalProvider,
  deletePersonalProvider,
  fetchPersonalProviderModels,
  listPersonalProviders,
  testPersonalProvider,
  updatePersonalProvider,
  type ProviderCreateInput,
} from '../api/personal-ai'

const providerPayload = {
  id: '18bcc7e0-40ba-4df8-a63d-7b6c3ee6e377',
  name: 'My OpenAI Compatible',
  base_url: 'https://provider.example/v1',
  api_key_masked: 'sk-••••••••1234',
  model_id: 'model-a',
  priority: 10,
  is_default: true,
  timeout_seconds: 60,
  enabled: true,
  custom_headers: {},
  last_test_status: 'untested',
  last_test_error_code: null,
  last_test_at: null,
  last_test_latency_ms: null,
  created_at: '2026-10-28T02:00:00Z',
  updated_at: '2026-10-28T02:00:00Z',
}

function jsonResponse(payload: unknown, status = 200): Response {
  return new Response(JSON.stringify(payload), {
    status,
    headers: { 'Content-Type': 'application/json', 'X-Request-ID': 'personal-ai-request' },
  })
}

describe('personal AI provider API contract', () => {
  beforeEach(() => {
    apiClient.clearCredentials()
    localStorage.clear()
    sessionStorage.clear()
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('uses only current-user provider routes and never persists the API key', async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(jsonResponse({ items: [providerPayload] }))
      .mockResolvedValueOnce(jsonResponse(providerPayload, 201))
    vi.stubGlobal('fetch', fetchMock)

    const listed = await listPersonalProviders()
    expect(listed[0]?.apiKeyMasked).toBe('sk-••••••••1234')
    const input: ProviderCreateInput = {
      name: 'My OpenAI Compatible',
      baseUrl: 'https://provider.example/v1',
      apiKey: 'sk-test-secret-1234',
      modelId: 'model-a',
      priority: 10,
      isDefault: true,
      timeoutSeconds: 60,
      enabled: true,
      customHeaders: {},
    }
    await createPersonalProvider(input)

    expect((fetchMock.mock.calls[0][0] as string)).toBe('/api/v1/me/ai/providers')
    expect((fetchMock.mock.calls[1][0] as string)).toBe('/api/v1/me/ai/providers')
    const body = JSON.parse(String((fetchMock.mock.calls[1][1] as RequestInit).body))
    expect(body.api_key).toBe(input.apiKey)
    expect(localStorage.length).toBe(0)
    expect(sessionStorage.length).toBe(0)
  })

  it('updates, tests, lists models and deletes through the personal provider path', async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(jsonResponse(providerPayload))
      .mockResolvedValueOnce(jsonResponse({ success: true, status: 'succeeded', latency_ms: 80, error_code: null, error_message: null, models: ['model-a'] }))
      .mockResolvedValueOnce(jsonResponse({ success: true, models: ['model-a', 'model-b'], error_code: null, error_message: null }))
      .mockResolvedValueOnce(new Response(null, { status: 204 }))
    vi.stubGlobal('fetch', fetchMock)

    await updatePersonalProvider(providerPayload.id, { modelId: 'model-b' })
    await testPersonalProvider(providerPayload.id)
    const models = await fetchPersonalProviderModels(providerPayload.id)
    await deletePersonalProvider(providerPayload.id)

    expect(models.models).toEqual(['model-a', 'model-b'])
    expect(fetchMock.mock.calls.map((call) => call[0])).toEqual([
      `/api/v1/me/ai/providers/${providerPayload.id}`,
      `/api/v1/me/ai/providers/${providerPayload.id}/test`,
      `/api/v1/me/ai/providers/${providerPayload.id}/models`,
      `/api/v1/me/ai/providers/${providerPayload.id}`,
    ])
  })
})
