import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import ProgressCard from '../components/ProgressCard.vue'
import { parseProgress, parseWeekly } from '../api/progress'

const progressMocks = vi.hoisted(() => ({
  fetchProgress: vi.fn(),
}))

vi.mock('../api/progress', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../api/progress')>()
  return { ...actual, fetchProgress: progressMocks.fetchProgress }
})

const payload = {
  xp: 480,
  crumbs: 120,
  level: { level: 2, title: '余烬', xp_into_level: 160, xp_for_next_level: 400 },
  streak: 3,
  streak_best: 5,
  active_today: true,
  local_date: '2026-11-09',
  quests: [
    { key: 'review_due', progress: 12, target: 20, completed: false, reward_crumbs: 30 },
    { key: 'practice_one', progress: 1, target: 1, completed: true, reward_crumbs: 40 },
    { key: 'challenge_done', progress: 0, target: 1, completed: false, reward_crumbs: 60 },
  ],
}

describe('gamification', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    progressMocks.fetchProgress.mockResolvedValue(parseProgress(payload))
  })

  it('parses level, streak and the three quests', () => {
    const progress = parseProgress(payload)
    expect(progress.level.level).toBe(2)
    expect(progress.level.title).toBe('余烬')
    expect(progress.streak).toBe(3)
    expect(progress.quests.map((quest) => quest.key)).toEqual([
      'review_due',
      'practice_one',
      'challenge_done',
    ])
  })

  it('marks only active days in the weekly summary', () => {
    const weekly = parseWeekly({
      days: [
        { date: '2026-11-08', xp: 0, crumbs: 0, active: false },
        { date: '2026-11-09', xp: 40, crumbs: 20, active: true },
      ],
      xp: 40,
      active_days: 1,
      streak: 1,
    })
    expect(weekly.days.filter((day) => day.active)).toHaveLength(1)
    expect(weekly.activeDays).toBe(1)
  })

  it('renders the level ring, streak and quest states', async () => {
    const wrapper = mount(ProgressCard)
    await flushPromises()
    expect(wrapper.text()).toContain('Lv.2')
    expect(wrapper.text()).toContain('3')
    expect(wrapper.text()).toContain('清空今日到期')
    expect(wrapper.findAll('.progress-card__quests li.is-done')).toHaveLength(1)
    const bars = wrapper.findAll('.progress-card__bar span')
    expect(bars[0].attributes('style')).toContain('60%')
  })
})
