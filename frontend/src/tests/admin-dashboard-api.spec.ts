import { afterEach, describe, expect, it, vi } from 'vitest'
import { ContractError } from '../api/errors'
import {
  fetchAdminDashboard,
  parseAdminDashboard,
} from '../api/admin-dashboard'

function payload() {
  return {
    generated_at: '2026-10-23T10:00:00Z',
    calculation_version: 'dashboard-v1',
    filters: {
      date_from: '2026-10-17',
      date_to: '2026-10-23',
      department: 'Engineering',
      learning_group: 'Core',
      timezone: 'Asia/Shanghai',
    },
    privacy: { suppressed: false, minimum_group_size: 3, reason: null },
    metrics: {
      total_members: 12,
      active_members: 8,
      active_member_rate: 0.6667,
      study_minutes: 412.5,
      plans_total: 24,
      plans_completed: 18,
      task_completion_rate: 0.75,
      new_words_completed: 41,
      due_words_completed: 17,
      practice_submissions: 9,
      practice_correct_rate: 0.82,
      mistake_flags: 6,
      high_priority_mistakes: 2,
      memory_events: 120,
      average_current_streak_days: 3.4,
      members_with_streak_7d: 4,
      ai_jobs: 20,
      ai_failed: 2,
      ai_failure_rate: 0.1,
      challenges_completed: 5,
    },
    trend: [
      { local_date: '2026-10-22', active_members: 5, study_minutes: 120, plans_completed: 6, practice_submissions: 3, practice_correct_rate: 0.8, mistakes: 2, memory_events: 30, ai_jobs: 5, ai_failed: 1, challenges_completed: 2 },
      { local_date: '2026-10-23', active_members: 7, study_minutes: 180, plans_completed: 8, practice_submissions: 4, practice_correct_rate: 0.85, mistakes: 1, memory_events: 44, ai_jobs: 7, ai_failed: 0, challenges_completed: 3 },
    ],
    groups: [
      { department: 'Engineering', learning_group: 'Core', member_count: 6, active_members: 4, study_minutes: 220, task_completion_rate: 0.8, practice_correct_rate: 0.86, mistake_flags: 3, ai_failure_rate: 0.05 },
    ],
    group_page: 1,
    group_page_size: 10,
    group_has_more: false,
    suppressed_group_count: 1,
    quota_usage: [
      { quota_kind: 'coach_messages', consumed: 4, reserved: 1, released: 2 },
    ],
    risk_hints: { inactive_members_3d: 2, high_mistake_members: 1, ai_failure_alert: false },
  }
}

function jsonResponse(value: unknown, status = 200): Response {
  return new Response(JSON.stringify(value), {
    status,
    headers: { 'Content-Type': 'application/json', 'X-Request-ID': 'dashboard-request' },
  })
}

describe('admin dashboard API contract', () => {
  afterEach(() => {
    vi.restoreAllMocks()
    vi.unstubAllGlobals()
  })

  it('maps aggregate fields without inventing missing values', () => {
    const response = parseAdminDashboard(payload())
    expect(response).toMatchObject({
      generatedAt: '2026-10-23T10:00:00Z',
      calculationVersion: 'dashboard-v1',
      filters: { department: 'Engineering', learningGroup: 'Core', timezone: 'Asia/Shanghai' },
      privacy: { suppressed: false, minimumGroupSize: 3 },
      metrics: { totalMembers: 12, activeMembers: 8, studyMinutes: 412.5 },
      groupPage: 1,
      groupHasMore: false,
      suppressedGroupCount: 1,
    })
    expect(response.trend).toHaveLength(2)
    expect(response.groups[0].taskCompletionRate).toBe(0.8)
    expect(response.quotaUsage[0].quotaKind).toBe('coach_messages')
  })

  it('preserves null aggregate values and empty optional arrays', () => {
    const value = payload()
    const metrics = value.metrics as Record<string, unknown>
    metrics.active_members = null
    metrics.practice_correct_rate = null
    value.trend = []
    value.groups = []
    value.quota_usage = []
    const response = parseAdminDashboard(value)
    expect(response.metrics.activeMembers).toBeNull()
    expect(response.metrics.practiceCorrectRate).toBeNull()
    expect(response.trend).toEqual([])
    expect(response.groups).toEqual([])
    expect(response.quotaUsage).toEqual([])
  })

  it('rejects malformed dates and unknown quota kinds', () => {
    const badDate = payload()
    badDate.filters.date_from = '2026/10/17'
    expect(() => parseAdminDashboard(badDate)).toThrow(ContractError)

    const badQuota = payload()
    badQuota.quota_usage[0].quota_kind = 'unknown'
    expect(() => parseAdminDashboard(badQuota)).toThrow(ContractError)
  })

  it('sends only the dashboard whitelist filters and pagination', async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(payload()))
    vi.stubGlobal('fetch', fetchMock)
    const response = await fetchAdminDashboard({
      dateFrom: '2026-10-17',
      dateTo: '2026-10-23',
      department: 'Engineering & Ops',
      learningGroup: 'Core',
      page: 2,
      pageSize: 20,
    })
    expect(response.metrics.totalMembers).toBe(12)
    expect(fetchMock.mock.calls[0]?.[0]).toBe(
      '/api/v1/admin/dashboard?date_from=2026-10-17&date_to=2026-10-23&department=Engineering+%26+Ops&learning_group=Core&page=2&page_size=20',
    )
  })
})
