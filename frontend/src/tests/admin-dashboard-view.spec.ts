import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import AdminDashboardView from '../views/AdminDashboardView.vue'
import { ApiError } from '../api/errors'
import type { AdminDashboardResponse } from '../api/admin-dashboard'

const dashboardMocks = vi.hoisted(() => ({
  fetchAdminDashboard: vi.fn(),
}))

vi.mock('../api/admin-dashboard', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../api/admin-dashboard')>()
  return { ...actual, ...dashboardMocks }
})

function makeDashboard(overrides: Partial<AdminDashboardResponse> = {}): AdminDashboardResponse {
  return {
    generatedAt: '2026-10-23T10:00:00Z',
    calculationVersion: 'dashboard-v1',
    filters: {
      dateFrom: '2026-10-17',
      dateTo: '2026-10-23',
      department: 'Engineering',
      learningGroup: 'Core',
      timezone: 'Asia/Shanghai',
    },
    privacy: { suppressed: false, minimumGroupSize: 3, reason: null },
    metrics: {
      totalMembers: 12, activeMembers: 8, activeMemberRate: 0.6667, studyMinutes: 412.5,
      plansTotal: 24, plansCompleted: 18, taskCompletionRate: 0.75,
      newWordsCompleted: 41, dueWordsCompleted: 17, practiceSubmissions: 9,
      practiceCorrectRate: 0.82, mistakeFlags: 6, highPriorityMistakes: 2,
      memoryEvents: 120, averageCurrentStreakDays: 3.4, membersWithStreak7d: 4,
      aiJobs: 20, aiFailed: 2, aiFailureRate: 0.1, challengesCompleted: 5,
    },
    trend: [
      { localDate: '2026-10-22', activeMembers: 5, studyMinutes: 120, plansCompleted: 6, practiceSubmissions: 3, practiceCorrectRate: 0.8, mistakes: 2, memoryEvents: 30, aiJobs: 5, aiFailed: 1, challengesCompleted: 2 },
      { localDate: '2026-10-23', activeMembers: 7, studyMinutes: 180, plansCompleted: 8, practiceSubmissions: 4, practiceCorrectRate: 0.85, mistakes: 1, memoryEvents: 44, aiJobs: 7, aiFailed: 0, challengesCompleted: 3 },
    ],
    groups: [
      { department: 'Engineering', learningGroup: 'Core', memberCount: 6, activeMembers: 4, studyMinutes: 220, taskCompletionRate: 0.8, practiceCorrectRate: 0.86, mistakeFlags: 3, aiFailureRate: 0.05 },
    ],
    groupPage: 1,
    groupPageSize: 10,
    groupHasMore: false,
    suppressedGroupCount: 1,
    quotaUsage: [{ quotaKind: 'coach_messages', consumed: 4, reserved: 1, released: 2 }],
    riskHints: { inactiveMembers3d: 2, highMistakeMembers: 1, aiFailureAlert: false },
    ...overrides,
  }
}

async function mountView() {
  const wrapper = mount(AdminDashboardView)
  await flushPromises()
  return wrapper
}

describe('admin dashboard view', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    dashboardMocks.fetchAdminDashboard.mockReset()
    dashboardMocks.fetchAdminDashboard.mockResolvedValue(makeDashboard())
  })

  it('renders aggregate metrics, accessible trend summary, groups and scope metadata', async () => {
    const wrapper = await mountView()
    expect(wrapper.text()).toContain('组织学习看板')
    expect(wrapper.text()).toContain('组织成员')
    expect(wrapper.text()).toContain('12')
    expect(wrapper.text()).toContain('66.7%')
    expect(wrapper.text()).toContain('学习分钟合计 300')
    expect(wrapper.get('.dashboard-bars').attributes('aria-label')).toContain('柱高按当前窗口内学习分钟相对值展示')
    expect(wrapper.text()).toContain('Engineering')
    expect(wrapper.text()).toContain('dashboard-v1')
    expect(wrapper.text()).toContain('Asia/Shanghai')
    expect(wrapper.text()).toContain('GET /api/v1/admin/dashboard')
  })

  it('shows privacy suppression instead of zero metrics for a small sample', async () => {
    dashboardMocks.fetchAdminDashboard.mockResolvedValue(makeDashboard({
      privacy: { suppressed: true, minimumGroupSize: 3, reason: 'aggregate sample below minimum size' },
      metrics: { ...makeDashboard().metrics, totalMembers: 2, activeMembers: null, studyMinutes: null },
    }))
    const wrapper = await mountView()
    expect(wrapper.text()).toContain('聚合结果已按隐私规则抑制')
    expect(wrapper.text()).toContain('不会把缺失值显示为 0')
    expect(wrapper.find('.dashboard-summary').exists()).toBe(false)
  })

  it('shows a normal no-members state even when the server returns zero trend points', async () => {
    const zeroTrend = makeDashboard().trend.map((point, index) => ({
      ...point,
      localDate: `2026-10-${String(17 + index).padStart(2, '0')}`,
      activeMembers: 0,
      studyMinutes: 0,
      plansCompleted: 0,
      practiceSubmissions: 0,
      practiceCorrectRate: null,
      mistakes: 0,
      memoryEvents: 0,
      aiJobs: 0,
      aiFailed: 0,
      challengesCompleted: 0,
    }))
    dashboardMocks.fetchAdminDashboard.mockResolvedValue(makeDashboard({
      privacy: { suppressed: false, minimumGroupSize: 3, reason: null },
      metrics: { ...makeDashboard().metrics, totalMembers: 0, activeMembers: 0, studyMinutes: 0 },
      trend: zeroTrend,
      groups: [],
      suppressedGroupCount: 0,
      quotaUsage: [],
    }))
    const wrapper = await mountView()
    expect(wrapper.text()).toContain('当前筛选范围内没有成员')
    expect(wrapper.text()).toContain('这不是系统故障')
    expect(wrapper.text()).not.toContain('聚合结果已按隐私规则抑制')
    expect(wrapper.find('.dashboard-summary').exists()).toBe(false)
  })

  it('applies filters with page reset and server pagination', async () => {
    const wrapper = await mountView()
    await wrapper.get('#dashboard-from').setValue('2026-10-01')
    await wrapper.get('#dashboard-to').setValue('2026-10-07')
    await wrapper.get('#dashboard-department').setValue('Sales')
    await wrapper.get('#dashboard-group').setValue('Alpha')
    dashboardMocks.fetchAdminDashboard.mockResolvedValueOnce(makeDashboard({ groupHasMore: true }))
    await wrapper.get('form').trigger('submit')
    await flushPromises()
    expect(dashboardMocks.fetchAdminDashboard).toHaveBeenLastCalledWith(expect.objectContaining({
      dateFrom: '2026-10-01', dateTo: '2026-10-07', department: 'Sales', learningGroup: 'Alpha', page: 1,
    }))

    dashboardMocks.fetchAdminDashboard.mockResolvedValueOnce(makeDashboard({ groupPage: 2, groupHasMore: false }))
    const next = wrapper.findAll('.dashboard-pagination [role="button"]').find((button) => button.text() === '下一页')!
    await next.trigger('click')
    await flushPromises()
    expect(dashboardMocks.fetchAdminDashboard).toHaveBeenLastCalledWith(expect.objectContaining({ page: 2 }))
  })

  it('surfaces server errors with request id', async () => {
    dashboardMocks.fetchAdminDashboard.mockRejectedValueOnce(
      new ApiError(429, 'RATE_LIMITED', 'Too many requests.', null, 'dashboard-429', true),
    )
    const wrapper = await mountView()
    expect(wrapper.text()).toContain('请求过于频繁')
    expect(wrapper.text()).toContain('dashboard-429')
    expect(wrapper.find('.dashboard-summary').exists()).toBe(false)
  })
})
