import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import PersonalAiConfigView from '../views/PersonalAiConfigView.vue'

const apiMocks = vi.hoisted(() => ({
  listPersonalProviders: vi.fn(),
  createPersonalProvider: vi.fn(),
  updatePersonalProvider: vi.fn(),
  deletePersonalProvider: vi.fn(),
  testPersonalProvider: vi.fn(),
  fetchPersonalProviderModels: vi.fn(),
}))

vi.mock('../api/personal-ai', () => apiMocks)

describe('PersonalAiConfigView', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    localStorage.clear()
    sessionStorage.clear()
    apiMocks.listPersonalProviders.mockResolvedValue([])
  })

  it('shows a real empty state and opens the blank provider form', async () => {
    const wrapper = mount(PersonalAiConfigView)
    await flushPromises()

    expect(wrapper.text()).toContain('还没有 AI 提供商')
    await wrapper.get('.personal-ai-empty [role="button"]').trigger('click')
    expect(wrapper.find('.ai-form-panel').exists()).toBe(true)
    expect(wrapper.get('#provider-name').element).toHaveProperty('value', '')
    expect(wrapper.get('#provider-api-key').element).toHaveProperty('value', '')
    expect(localStorage.length).toBe(0)
    expect(sessionStorage.length).toBe(0)
  })

  it('keeps the provider list and the form in separate desktop columns', async () => {
    const wrapper = mount(PersonalAiConfigView)
    await flushPromises()

    expect(wrapper.find('.personal-ai-main').exists()).toBe(true)
    expect(wrapper.find('.personal-ai-aside').exists()).toBe(false)

    await wrapper.get('.personal-ai-empty [role="button"]').trigger('click')
    // The provider form opens as a floating dialog, not inside the column.
    expect(wrapper.find('.ai-provider-dialog .ai-form-panel').exists()).toBe(true)
    expect(wrapper.find('.personal-ai-aside').exists()).toBe(false)
  })

  it('keeps provider data on the server list rather than embedding fixtures', async () => {
    apiMocks.listPersonalProviders.mockResolvedValue([{
      id: 'provider-1',
      name: 'Primary',
      baseUrl: 'https://provider.example/v1',
      apiKeyMasked: 'sk-••••1234',
      modelId: 'model-a',
      priority: 10,
      isDefault: true,
      timeoutSeconds: 60,
      enabled: true,
      customHeaders: {},
      lastTestStatus: 'untested',
      lastTestErrorCode: null,
      lastTestAt: null,
      lastTestLatencyMs: null,
      createdAt: '2026-10-28T00:00:00Z',
      updatedAt: '2026-10-28T00:00:00Z',
    }])
    const wrapper = mount(PersonalAiConfigView)
    await flushPromises()

    expect(wrapper.text()).toContain('Primary')
    expect(wrapper.text()).toContain('model-a')
    // The list no longer prints the masked key; it lives in the edit dialog.
    expect(wrapper.text()).not.toContain('sk-••••1234')
    expect(wrapper.text()).not.toContain('sk-test-secret')
  })
})
