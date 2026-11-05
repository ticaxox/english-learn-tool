import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import AiQuotaPanel from '../components/AiQuotaPanel.vue'

const apiMocks = vi.hoisted(() => ({
  fetchLearningProfile: vi.fn(),
  updateAiQuotaLimits: vi.fn(),
  fetchPracticeUsage: vi.fn(),
}))

vi.mock('../api/learning', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../api/learning')>()
  return {
    ...actual,
    fetchLearningProfile: apiMocks.fetchLearningProfile,
    updateAiQuotaLimits: apiMocks.updateAiQuotaLimits,
  }
})
vi.mock('../api/practice', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../api/practice')>()
  return { ...actual, fetchPracticeUsage: apiMocks.fetchPracticeUsage }
})

const usage = {
  localDate: '2026-11-05',
  quotas: [
    { quotaKind: 'coach_messages', limit: 100, used: 0, reserved: 0, remaining: 100 },
    { quotaKind: 'question_generation', limit: 20, used: 20, reserved: 0, remaining: 0 },
    { quotaKind: 'subjective_grading', limit: 50, used: 0, reserved: 0, remaining: 50 },
  ],
  concurrency: { limit: 2, inUse: 0 },
}

describe('AiQuotaPanel', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    apiMocks.fetchLearningProfile.mockResolvedValue({ aiQuotaLimits: {} })
    apiMocks.fetchPracticeUsage.mockResolvedValue(usage)
    apiMocks.updateAiQuotaLimits.mockResolvedValue(undefined)
  })

  it('shows the effective limits and saves an unlimited override', async () => {
    const wrapper = mount(AiQuotaPanel)
    await flushPromises()
    const rows = wrapper.findAll('.ai-quota-row')
    expect(rows).toHaveLength(3)
    expect((rows[0].get('input[type="number"]').element as HTMLInputElement).value).toBe('100')
    expect((rows[2].get('input[type="number"]').element as HTMLInputElement).value).toBe('50')

    await rows[1].get('input[type="checkbox"]').setValue(true)
    await wrapper.findAll('[role="button"]').find((button) => button.text().includes('保存额度'))!.trigger('click')
    await flushPromises()

    expect(apiMocks.updateAiQuotaLimits).toHaveBeenCalledWith({
      coach_messages: 100,
      question_generation: -1,
      subjective_grading: 50,
    })
  })

  it('shows an unlimited limit as a label instead of a number', async () => {
    apiMocks.fetchLearningProfile.mockResolvedValue({ aiQuotaLimits: { question_generation: -1 } })
    apiMocks.fetchPracticeUsage.mockResolvedValue({
      ...usage,
      quotas: usage.quotas.map((quota) =>
        quota.quotaKind === 'question_generation'
          ? { ...quota, limit: -1, remaining: -1 }
          : quota,
      ),
    })
    const wrapper = mount(AiQuotaPanel)
    await flushPromises()
    expect(wrapper.findAll('.ai-quota-row')[1].text()).toContain('不限')
    expect(wrapper.findAll('.ai-quota-row')[1].find('input[type="number"]').exists()).toBe(false)
  })
})
