import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import AiProviderForm from '../components/AiProviderForm.vue'
import AdminAiProvidersView from '../views/AdminAiProvidersView.vue'
import AdminAiPromptsView from '../views/AdminAiPromptsView.vue'
import AdminAiUsageView from '../views/AdminAiUsageView.vue'
import { apiClient } from '../api/client'
import { ApiError } from '../api/errors'
import type { AiProvider, AiUsage, PromptDetail, PromptSummary } from '../api/ai-admin'

const apiMocks = vi.hoisted(() => ({
  listProviders: vi.fn(),
  createProvider: vi.fn(),
  updateProvider: vi.fn(),
  deleteProvider: vi.fn(),
  testProvider: vi.fn(),
  fetchProviderModels: vi.fn(),
  listPrompts: vi.fn(),
  getPrompt: vi.fn(),
  updatePrompt: vi.fn(),
  fetchAiUsage: vi.fn(),
}))

vi.mock('../api/ai-admin', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../api/ai-admin')>()
  return { ...actual, ...apiMocks }
})

const defaultProvider: AiProvider = {
  id: 'provider-default',
  name: 'Default Provider',
  baseUrl: 'https://default.example/v1',
  apiKeyMasked: 'sk-••••1234',
  modelId: 'model-a',
  priority: 100,
  isDefault: true,
  timeoutSeconds: 60,
  enabled: true,
  customHeaders: { 'X-Team': 'learning' },
  lastTestStatus: 'succeeded',
  lastTestErrorCode: null,
  lastTestAt: '2026-10-23T03:00:00Z',
  lastTestLatencyMs: 88,
  createdAt: '2026-10-23T02:00:00Z',
  updatedAt: '2026-10-23T03:00:00Z',
}

const backupProvider: AiProvider = {
  ...defaultProvider,
  id: 'provider-backup',
  name: 'Backup Provider',
  baseUrl: 'https://backup.example/v1',
  apiKeyMasked: 'sk-••••5678',
  modelId: 'model-b',
  priority: 5,
  isDefault: false,
  enabled: true,
  lastTestStatus: 'untested',
  lastTestLatencyMs: null,
  lastTestAt: null,
}

const promptSummary: PromptSummary = {
  key: 'practice_generation',
  name: '练习生成',
  summary: '生成练习题目',
  updatedAt: '2026-10-23T03:00:00Z',
}

const promptDetail: PromptDetail = {
  ...promptSummary,
  template: 'Generate questions for {{context}}',
}

const usage: AiUsage = {
  dateFrom: '2026-10-01',
  dateTo: '2026-10-23',
  totalJobs: 12,
  activeJobs: 2,
  providers: [{ providerId: defaultProvider.id, providerName: defaultProvider.name, jobs: 12, succeeded: 10, failed: 2 }],
  quotas: [{
    quotaKind: 'question_generation',
    limitPerUser: 20,
    usersWithUsage: 3,
    consumed: 9,
    reserved: 1,
    released: 0,
  }],
  tasks: [{ taskType: 'practice_generation', status: 'failed', count: 2 }],
}

describe('admin AI views', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    apiMocks.listProviders.mockResolvedValue([backupProvider, defaultProvider])
    apiMocks.updateProvider.mockImplementation(async (id: string, patch: object) => ({ ...defaultProvider, id, ...patch }))
    apiMocks.deleteProvider.mockResolvedValue(undefined)
    apiMocks.testProvider.mockResolvedValue({ success: true, status: 'succeeded', latencyMs: 40, errorCode: null, errorMessage: null, models: ['model-a'] })
    apiMocks.fetchProviderModels.mockResolvedValue({ success: true, models: ['model-a', 'model-b'], errorCode: null, errorMessage: null })
    apiMocks.listPrompts.mockResolvedValue([promptSummary])
    apiMocks.getPrompt.mockResolvedValue(promptDetail)
    apiMocks.updatePrompt.mockResolvedValue(promptDetail)
    apiMocks.fetchAiUsage.mockResolvedValue(usage)
  })

  it('shows a real 403 instead of an empty or fabricated provider list', async () => {
    apiMocks.listProviders.mockRejectedValueOnce(new ApiError(403, 'ADMIN_REQUIRED', 'Administrator permission is required.', null, 'forbidden-ai', false))
    const wrapper = mount(AdminAiProvidersView)
    await flushPromises()
    expect(wrapper.text()).toContain('权限不足或操作被拒绝')
    expect(wrapper.text()).toContain('forbidden-ai')
    expect(wrapper.find('.provider-card').exists()).toBe(false)
  })

  it('renders default first, then backup priority, and never exposes a plaintext key', async () => {
    const wrapper = mount(AdminAiProvidersView)
    await flushPromises()
    const names = wrapper.findAll('.provider-card h2').map((item) => item.text())
    expect(names).toEqual(['Default Provider', 'Backup Provider'])
    expect(wrapper.text()).toContain('sk-••••1234')
    expect(wrapper.text()).toContain('默认提供商')
    expect(wrapper.text()).toContain('备用提供商')
    expect(wrapper.text()).not.toContain('sk-test-secret')
  })

  it('sets a backup provider as default only through the server', async () => {
    const wrapper = mount(AdminAiProvidersView)
    await flushPromises()
    const backupCard = wrapper.findAll('.provider-card')[1]
    await backupCard.findAll('[role="button"]').find((button) => button.text() === '设为默认')!.trigger('click')
    await flushPromises()
    expect(apiMocks.updateProvider).toHaveBeenCalledWith('provider-backup', { isDefault: true })
  })

  it('deletes a provider only after explicit confirmation', async () => {
    vi.spyOn(window, 'confirm').mockReturnValueOnce(true)
    const wrapper = mount(AdminAiProvidersView)
    await flushPromises()
    const firstCard = wrapper.findAll('.provider-card')[0]
    await firstCard.findAll('[role="button"]').find((button) => button.text() === '删除')!.trigger('click')
    await flushPromises()
    expect(apiMocks.deleteProvider).toHaveBeenCalledWith(defaultProvider.id)
  })

  it('shows a real provider timeout result with request id and retry boundary', async () => {
    apiMocks.testProvider.mockResolvedValueOnce({
      success: false,
      status: 'failed',
      latencyMs: 15000,
      errorCode: 'AI_PROVIDER_TIMEOUT',
      errorMessage: 'Provider timed out.',
      models: [],
    })
    vi.spyOn(apiClient, 'getLastRequestId').mockReturnValue('test-request-id')
    const wrapper = mount(AdminAiProvidersView)
    await flushPromises()
    const firstCard = wrapper.findAll('.provider-card')[0]
    const testButton = firstCard.findAll('[role="button"]').find((button) => button.text() === '连接检查')
    await testButton!.trigger('click')
    await flushPromises()
    expect(wrapper.text()).toContain('真实连接检查失败')
    expect(wrapper.text()).toContain('AI_PROVIDER_TIMEOUT')
    expect(wrapper.text()).toContain('test-request-id')
  })

  it('offers manual model entry when the model-list endpoint fails', async () => {
    apiMocks.fetchProviderModels.mockResolvedValueOnce({
      success: false,
      models: [],
      errorCode: 'AI_MODEL_LIST_UNSUPPORTED',
      errorMessage: 'Manual model id required.',
    })
    const wrapper = mount(AdminAiProvidersView)
    await flushPromises()
    const firstCard = wrapper.findAll('.provider-card')[0]
    await firstCard.findAll('[role="button"]').find((button) => button.text() === '获取模型')!.trigger('click')
    await flushPromises()
    expect(wrapper.text()).toContain('AI_MODEL_LIST_UNSUPPORTED')
    expect(wrapper.text()).toContain('可打开编辑表单手填模型 ID')
  })

  it('preserves an existing key when editing without a replacement', async () => {
    const wrapper = mount(AiProviderForm, { props: { provider: defaultProvider } })
    await wrapper.get('#provider-model').setValue('model-c')
    await wrapper.get('form').trigger('submit')
    const emitted = wrapper.emitted('update')!
    expect(emitted).toHaveLength(1)
    const [providerId, patch] = emitted[0] as [string, Record<string, unknown>]
    expect(providerId).toBe(defaultProvider.id)
    expect(patch.modelId).toBe('model-c')
    expect(patch).not.toHaveProperty('apiKey')
    // The stored key is never sent to the browser; only its mask is shown as a hint.
    const keyInput = wrapper.get('#provider-api-key').element as HTMLInputElement
    expect(keyInput.value).toBe('')
    expect(keyInput.placeholder).toContain(defaultProvider.apiKeyMasked)
  })

  it('requires a new key only when creating or explicitly replacing it', async () => {
    const wrapper = mount(AiProviderForm)
    await wrapper.get('#provider-name').setValue('New Provider')
    await wrapper.get('#provider-base-url').setValue('https://new.example/v1')
    await wrapper.get('#provider-model').setValue('model-new')
    await wrapper.get('#provider-api-key').setValue('short')
    await wrapper.get('form').trigger('submit')
    expect(wrapper.text()).toContain('至少需要 8 个字符')
    expect(wrapper.emitted('create')).toBeUndefined()

    await wrapper.get('#provider-api-key').setValue('sk-new-secret-1234')
    await wrapper.get('form').trigger('submit')
    expect(wrapper.emitted('create')![0][0]).toMatchObject({ apiKey: 'sk-new-secret-1234', modelId: 'model-new' })
  })

  it('shows prompt save failures without claiming success', async () => {
    apiMocks.updatePrompt.mockRejectedValueOnce(new ApiError(422, 'PROMPT_INVALID', '模板不能为空。', null, 'prompt-request', false))
    const wrapper = mount(AdminAiPromptsView)
    await flushPromises()
    await wrapper.get('#prompt-template').setValue('Changed prompt template')
    await wrapper.get('form').trigger('submit')
    await flushPromises()
    expect(wrapper.text()).toContain('请检查填写内容后重试')
    expect(wrapper.text()).toContain('prompt-request')
    expect(wrapper.text()).not.toContain('已保存')
  })

  it('renders privacy-safe aggregate usage and task status', async () => {
    const wrapper = mount(AdminAiUsageView)
    await flushPromises()
    expect(wrapper.text()).toContain('12')
    expect(wrapper.text()).toContain('题目生成')
    expect(wrapper.text()).toContain('练习生成')
    expect(wrapper.text()).toContain('失败')
    const tables = wrapper.findAll('table').map((table) => table.text()).join(' ')
    expect(tables).not.toContain('用户答案')
    expect(tables).not.toContain('私密词书正文')
  })
})

describe('AiProviderForm draft probe', () => {
  it('tests an unsaved provider with the typed key and normalized URL', async () => {
    const wrapper = mount(AiProviderForm, { props: { compact: true, canFetchModels: true } })
    await wrapper.get('#provider-base-url').setValue('https://draft.example/v1/')
    await wrapper.get('#provider-api-key').setValue('sk-draft-secret-1234')
    const testButton = wrapper.findAll('[role="button"]').find((button) => button.text() === '测试连接')
    expect(testButton).toBeTruthy()
    await testButton!.trigger('click')

    const [payload] = wrapper.emitted('test')?.[0] ?? []
    expect(payload).toMatchObject({
      baseUrl: 'https://draft.example/v1',
      apiKey: 'sk-draft-secret-1234',
      providerId: null,
      timeoutSeconds: 120,
      customHeaders: {},
    })
  })

  it('refuses to probe before a key is typed in the create dialog', async () => {
    const wrapper = mount(AiProviderForm, { props: { compact: true, canFetchModels: true } })
    await wrapper.get('#provider-base-url').setValue('https://draft.example/v1')
    const fetchButton = wrapper.findAll('[role="button"]').find((button) => button.text() === '获取模型')
    await fetchButton!.trigger('click')

    expect(wrapper.emitted('fetch-models')).toBeUndefined()
    expect(wrapper.text()).toContain('先填写 API Key 才能测试连接。')
  })

  it('reuses a stored key in edit mode by sending only the provider id', async () => {
    const wrapper = mount(AiProviderForm, {
      props: { compact: true, canFetchModels: true, provider: defaultProvider },
    })
    const fetchButton = wrapper.findAll('[role="button"]').find((button) => button.text() === '获取模型')
    await fetchButton!.trigger('click')

    const [payload] = wrapper.emitted('fetch-models')?.[0] ?? []
    expect(payload).toMatchObject({
      baseUrl: 'https://default.example/v1',
      apiKey: null,
      providerId: defaultProvider.id,
    })
  })
})
