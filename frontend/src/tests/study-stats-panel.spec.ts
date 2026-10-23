import { mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import StudyStatsPanel from '../components/StudyStatsPanel.vue'
import { ApiError } from '../api/errors'
import type { LearningStats } from '../types/learning'

const apiMocks = vi.hoisted(() => ({ fetchLearningStats: vi.fn() }))

vi.mock('../api/learning', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../api/learning')>()
  return { ...actual, ...apiMocks }
})

function stats(overrides: Partial<LearningStats> = {}): LearningStats {
  return {
    localDate: '2026-10-23',
    activeMinutes: 6,
    goalMinutes: 30,
    goalReached: false,
    streakDays: 4,
    sources: ['heartbeat'],
    ...overrides,
  }
}

async function flush(): Promise<void> {
  await Promise.resolve()
  await Promise.resolve()
}

describe('StudyStatsPanel', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    apiMocks.fetchLearningStats.mockReset()
  })

  it('renders the server minutes and never counts them locally', async () => {
    apiMocks.fetchLearningStats.mockResolvedValue(stats())
    const wrapper = mount(StudyStatsPanel)
    await flush()

    const text = wrapper.text()
    expect(text).toContain('6')
    expect(text).toContain('30')
    expect(text).toContain('heartbeat')
    expect(text).toContain('连续学习 4 天')

    const bar = wrapper.get('[role="progressbar"]')
    expect(bar.attributes('aria-valuenow')).toBe('6')
    expect(bar.attributes('aria-valuemax')).toBe('30')
    // 6/30 = 20%
    expect(wrapper.get('.progress > span').attributes('style')).toContain('width: 20%')
  })

  it('shows the achieved badge only when the server says the goal is reached', async () => {
    apiMocks.fetchLearningStats.mockResolvedValue(stats({ activeMinutes: 30, goalReached: true }))
    const wrapper = mount(StudyStatsPanel)
    await flush()
    expect(wrapper.text()).toContain('已达标')
  })

  it('does not claim a reached goal the server did not report', async () => {
    apiMocks.fetchLearningStats.mockResolvedValue(stats({ activeMinutes: 40, goalReached: false }))
    const wrapper = mount(StudyStatsPanel)
    await flush()
    expect(wrapper.text()).not.toContain('已达标')
  })

  it('caps the bar at 100% but keeps the real number visible', async () => {
    apiMocks.fetchLearningStats.mockResolvedValue(stats({ activeMinutes: 75, goalReached: true }))
    const wrapper = mount(StudyStatsPanel)
    await flush()
    expect(wrapper.get('.progress > span').attributes('style')).toContain('width: 100%')
    expect(wrapper.text()).toContain('75')
  })

  it('surfaces a real stats failure with a retry instead of falling back to zeroes', async () => {
    apiMocks.fetchLearningStats.mockRejectedValueOnce(
      new ApiError(503, 'HTTP_503', '统计服务暂不可用', null, 'stats-request', true),
    )
    const wrapper = mount(StudyStatsPanel)
    await flush()

    expect(wrapper.text()).toContain('统计服务暂不可用')
    expect(wrapper.text()).toContain('stats-request')
    expect(wrapper.find('[role="progressbar"]').exists()).toBe(false)
    expect(wrapper.text()).not.toContain('0 / 0')

    apiMocks.fetchLearningStats.mockResolvedValueOnce(stats())
    const retry = wrapper.findAll('button').find((button) => button.text().includes('重新读取统计'))
    await retry!.trigger('click')
    await flush()
    expect(wrapper.find('[role="progressbar"]').exists()).toBe(true)
  })

  it('says so when the server labels no data source', async () => {
    apiMocks.fetchLearningStats.mockResolvedValue(stats({ sources: [], streakDays: null }))
    const wrapper = mount(StudyStatsPanel)
    await flush()
    expect(wrapper.text()).toContain('服务端未标注')
    expect(wrapper.text()).not.toContain('连续学习')
  })
})
