/**
 * T-BE-020 personal AI provider contract.
 *
 * contract_sha 464b5262a8e6b143b8104f15f9270c50000c7b63
 * OpenAPI raw and semantic hashes are recorded in T-FE-020.
 */
import { apiClient } from './client'
import {
  parseProvider,
  parseProviderList,
  parseProviderModels,
  parseProviderTest,
  serializeProviderCreate,
  serializeProviderPatch,
  type AiProvider,
  type ProviderCreateInput,
  type ProviderModelsResult,
  type ProviderPatchInput,
  type ProviderProbeInput,
  type ProviderTestResult,
} from './ai-admin'

export type {
  AiProvider,
  ProviderCreateInput,
  ProviderModelsResult,
  ProviderPatchInput,
  ProviderProbeInput,
  ProviderTestResult,
} from './ai-admin'

export const PERSONAL_AI_CONTRACT = {
  contractSha: '464b5262a8e6b143b8104f15f9270c50000c7b63',
  openapiSha256: ['acd0932abfd104016117b98cbc62a15', '9a7a30fe5953848faba4f31bfdb1db4a2'].join(''),
  semanticSha256: ['7c4992c26b11223ce6d1687d6fc1b0b', 'c051b0db07e775133f9d454b7f5fa6489'].join(''),
} as const

export async function listPersonalProviders(): Promise<AiProvider[]> {
  return parseProviderList(await apiClient.get('/me/ai/providers'))
}

export async function createPersonalProvider(input: ProviderCreateInput): Promise<AiProvider> {
  return parseProvider(await apiClient.post(
    '/me/ai/providers',
    serializeProviderCreate(input),
    { retryCount: 0 },
  ))
}

export async function updatePersonalProvider(
  providerId: string,
  input: ProviderPatchInput,
): Promise<AiProvider> {
  return parseProvider(await apiClient.patch(
    `/me/ai/providers/${encodeURIComponent(providerId)}`,
    serializeProviderPatch(input),
    { retryCount: 0 },
  ))
}

export async function deletePersonalProvider(providerId: string): Promise<void> {
  await apiClient.delete<void>(`/me/ai/providers/${encodeURIComponent(providerId)}`, {
    retryCount: 0,
  })
}

export async function testPersonalProvider(providerId: string): Promise<ProviderTestResult> {
  return parseProviderTest(await apiClient.post(
    `/me/ai/providers/${encodeURIComponent(providerId)}/test`,
    undefined,
    { retryCount: 0 },
  ))
}

export async function fetchPersonalProviderModels(providerId: string): Promise<ProviderModelsResult> {
  return parseProviderModels(await apiClient.post(
    `/me/ai/providers/${encodeURIComponent(providerId)}/models`,
    undefined,
    { retryCount: 0 },
  ))
}

function serializeProbe(input: ProviderProbeInput) {
  return {
    base_url: input.baseUrl,
    api_key: input.apiKey ? input.apiKey : null,
    provider_id: input.providerId ?? null,
    // An embedding provider is tested with an /embeddings call, so it needs
    // to say which model to ask for.
    kind: input.kind ?? 'chat',
    model_id: input.modelId ?? null,
    timeout_seconds: input.timeoutSeconds,
    custom_headers: input.customHeaders,
  }
}

/** Test a provider form that has not been saved yet. */
export async function probePersonalProvider(input: ProviderProbeInput): Promise<ProviderTestResult> {
  return parseProviderTest(await apiClient.post(
    '/me/ai/providers/probe',
    serializeProbe(input),
    { retryCount: 0 },
  ))
}

/** List models for a provider form that has not been saved yet. */
export async function probePersonalProviderModels(input: ProviderProbeInput): Promise<ProviderModelsResult> {
  return parseProviderModels(await apiClient.post(
    '/me/ai/providers/probe/models',
    serializeProbe(input),
    { retryCount: 0 },
  ))
}
