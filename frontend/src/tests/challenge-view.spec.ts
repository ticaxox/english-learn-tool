import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createMemoryHistory, createRouter } from 'vue-router'
import { defineComponent, h, ref } from 'vue'
import ChallengeView from '../views/ChallengeView.vue'
import { ApiError } from '../api/errors'
import type { ChallengeNode, ChallengeNodeDetail, ChallengePlan } from '../api/challenge'

const challengeMocks = vi.hoisted(() => ({
  getTodayChallenge: vi.fn(),
  generateTodayChallenge: vi.fn(),
  getChallengeJob: vi.fn(),
  getChallenge: vi.fn(),
  getChallengeNodeDetail: vi.fn(),
  startChallengeNode: vi.fn(),
  submitChallengeBoss: vi.fn(),
  getChallengeHistory: vi.fn(),
}))

vi.mock('../api/challenge', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../api/challenge')>()
  return { ...actual, ...challengeMocks }
})

vi.mock('../components/ChallengeBossPanel.vue', () => ({
  default: defineComponent({
    props: ['challengeId', 'nodeId', 'sessionId'],
    emits: ['completed'],
    setup(_, { emit }) {
      const completed = ref(false)
      return () => h('div', { 'data-test': 'boss-panel' }, [
        h('span', completed.value ? 'BOSS completed' : 'BOSS ready'),
        h('div', {
          class: 'emit-boss-completed',
          role: 'button',
          tabindex: 0,
          onClick: () => {
            completed.value = true
            emit('completed', {
              challengeId: makePlan().id,
              nodeId: mainNodes[2].id,
              status: 'completed',
              score: 80,
              completed: true,
              submissionId: 'submission-1',
              result: { question_stats: { total: 5, correct: 4, mistakes: 1 } },
              errorCode: null,
              errorMessage: null,
              message: 'The final challenge is complete.',
            })
          },
        }, 'emit completed'),
      ])
    },
  }),
}))

const StubPage = defineComponent({ render: () => h('div') })
function makeRouter() {
  return createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/challenges', name: 'challenges', component: StubPage },
      { path: '/challenges/:challengeId', name: 'challenge-detail', component: StubPage },
      { path: '/overview', name: 'overview', component: StubPage },
      { path: '/memory', name: 'memory', component: StubPage },
      { path: '/practice/:sessionId', name: 'practice-session', component: StubPage },
    ],
  })
}

async function mountView(path = '/challenges') {
  const router = makeRouter()
  await router.push(path)
  await router.isReady()
  const wrapper = mount(ChallengeView, { global: { plugins: [router] } })
  await flushPromises()
  return { wrapper, router }
}

function makeNode(overrides: Partial<ChallengeNode> = {}): ChallengeNode {
  return {
    id: '11111111-1111-4111-8111-111111111111', clientKey: 'review-1', nodeType: 'REVIEW', orderIndex: 1,
    title: '复习回廊', description: '复习到期单词。', estimatedMinutes: 8, wordEntryIds: [], practiceSpec: {},
    optional: false, status: 'unlocked', resourceType: null, resourceId: null,
    startedAt: null, completedAt: null, errorCode: null, errorMessage: null, ...overrides,
  }
}

const mainNodes = [
  makeNode(),
  makeNode({ id: '22222222-2222-4222-8222-222222222222', clientKey: 'new-1', nodeType: 'NEW_WORDS', orderIndex: 2, title: '新词营地', status: 'locked' }),
  makeNode({ id: '33333333-3333-4333-8333-333333333333', clientKey: 'boss-1', nodeType: 'BOSS', orderIndex: 3, title: '终点挑战', status: 'locked', practiceSpec: { practice_type: 'fill_blank', count: 5 } }),
]
const optionalNode = makeNode({ id: '44444444-4444-4444-8444-444444444444', clientKey: 'side-1', nodeType: 'OPTIONAL_SIDE', orderIndex: 4, title: '可选支线', optional: true, status: 'unlocked' })

function mapStatusLabel(status: ChallengeNode['status']): string {
  return { locked: '未解锁', unlocked: '已解锁', in_progress: '进行中', completed: '已完成', failed: '失败' }[status]
}

function makeMapDsl(nodes: ChallengeNode[] = [...mainNodes, optionalNode]): string {
  const section = (
    key: string,
    title: string,
    type: string,
    questionType: string,
    status: string,
    minutes: number,
    previous: string,
    next: string,
    optional: boolean,
  ): string => `## [${key}] ${title}
- 类型: ${type}
- 题目类型: ${questionType}
- 状态: ${status}
- 时长: ${minutes} 分钟
- 说明: ${title}的说明。
- 链接: 待开始
- 前置: ${previous}
- 分支: ${next}
- 可选: ${optional ? '是' : '否'}
`
  const [review, fresh, boss, side] = nodes
  return [
    '# 今日闯关',
    '> 先复习，再学习，最后完成挑战。',
    '',
    section('review-1', review.title, '复习', '翻卡记忆', mapStatusLabel(review.status), 8, '开始', 'new-1', false),
    section('new-1', fresh.title, '学习新词', '翻卡记忆', mapStatusLabel(fresh.status), 5, 'review-1', 'boss-1', false),
    section('boss-1', boss.title, '终点挑战', '填空', mapStatusLabel(boss.status), 4, 'new-1', '终点', false),
    ...(side
      ? [section('side-1', side.title, '可选支线', '可选练习', mapStatusLabel(side.status), 4, 'boss-1', '终点', true)]
      : []),
  ].join(String.fromCharCode(10))
}

function shanghaiToday(): string {
  return new Intl.DateTimeFormat('en-CA', { timeZone: 'Asia/Shanghai' }).format(new Date())
}

const currentLocalDate = shanghaiToday()

function makePlan(overrides: Partial<ChallengePlan> = {}): ChallengePlan {
  return {
    id: 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa', localDate: currentLocalDate, status: 'ready', title: '今日闯关',
    summary: '先复习，再学习，最后完成挑战。', targetMinutes: 30, dailyPlanId: 'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb',
    aiJobId: null, generatedAt: '2026-10-23T08:00:00Z', lockedAt: '2026-10-23T08:00:00Z', challengeCompletedAt: null,
    expiresAt: '2099-10-24T00:00:00Z', errorCode: null, errorMessage: null, mainCompleted: 0, mainTotal: 3, mapDsl: makeMapDsl(overrides.nodes ?? [...mainNodes, optionalNode]),
    nodes: [...mainNodes, optionalNode], ...overrides,
  }
}

function detail(node: ChallengeNode, actions: ChallengeNodeDetail['allowedActions']): ChallengeNodeDetail {
  return { challengeId: makePlan().id, node, allowedActions: actions }
}

describe('challenge view', () => {
  beforeEach(() => {
    vi.useFakeTimers({ toFake: ['Date'] })
    vi.setSystemTime(new Date('2026-10-23T12:00:00+08:00'))
    vi.clearAllMocks()
    challengeMocks.getTodayChallenge.mockResolvedValue(makePlan())
    challengeMocks.getChallenge.mockResolvedValue(makePlan())
    challengeMocks.generateTodayChallenge.mockResolvedValue({ challengeId: makePlan().id, status: 'ready', jobId: null, statusUrl: null, replayed: false })
    challengeMocks.getChallengeJob.mockResolvedValue({ jobId: 'job-1', challengeId: makePlan().id, status: 'succeeded', errorCode: null, errorMessage: null, retryable: false })
    challengeMocks.getChallengeHistory.mockResolvedValue({ items: [{ id: makePlan().id, localDate: currentLocalDate, status: 'ready', title: '今日闯关', summary: '地图已生成', targetMinutes: 30, mainCompleted: 0, mainTotal: 3, challengeCompletedAt: null }], nextCursor: null, hasMore: false })
    challengeMocks.getChallengeNodeDetail.mockResolvedValue(detail(mainNodes[0], ['start']))
    challengeMocks.startChallengeNode.mockResolvedValue({ challengeId: makePlan().id, nodeId: mainNodes[0].id, status: 'in_progress', resourceType: 'memory', resourceId: 'memory-session-1', jobId: null, message: 'The memory task is ready.' })
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('renders the server map, statuses, progress, optional branch, and history', async () => {
    const { wrapper } = await mountView()
    expect(wrapper.text()).toContain('今日闯关')
    expect(wrapper.findAll('.challenge-dsl-card')).toHaveLength(4)
    expect(wrapper.findAll('.challenge-dsl-card.is-branch')).toHaveLength(1)
    expect(wrapper.text()).toContain('复习回廊')
    expect(wrapper.text()).toContain('新词营地')
    expect(wrapper.text()).toContain('终点挑战')
    expect(wrapper.text()).toContain('可选支线')
    expect(wrapper.text()).toContain('主线 0 / 3')
    expect(wrapper.text()).toContain('闯关历史')
    expect(wrapper.get('.challenge-progress').attributes('aria-valuenow')).toBe('0')
  })

  it('does not repeat the date when a history title already starts with it', async () => {
    challengeMocks.getChallengeHistory.mockResolvedValue({
      items: [{ id: makePlan().id, localDate: currentLocalDate, status: 'ready', title: `${currentLocalDate} 到期单词巩固闯关`, summary: '', targetMinutes: 30, mainCompleted: 0, mainTotal: 3, challengeCompletedAt: null }],
      nextCursor: null,
      hasMore: false,
    })
    const { wrapper } = await mountView()
    expect(wrapper.get('.challenge-history__item strong').text()).toBe(`${currentLocalDate} · 到期单词巩固闯关`)
  })

  it('generates a missing map through the 202 flow', async () => {
    challengeMocks.getTodayChallenge
      .mockRejectedValueOnce(new ApiError(404, 'CHALLENGE_NOT_GENERATED', 'Not generated.', null, 'not-generated', false))
      .mockResolvedValueOnce(makePlan())
    const { wrapper } = await mountView()
    expect(wrapper.text()).toContain('今日地图尚未生成')
    await wrapper.get('.challenge-generate .button').trigger('click')
    await flushPromises()
    expect(challengeMocks.generateTodayChallenge).toHaveBeenCalledOnce()
    expect(wrapper.text()).toContain('复习回廊')
  })

  it('lets the learner stop waiting for a slow map job', async () => {
    challengeMocks.getTodayChallenge.mockRejectedValueOnce(
      new ApiError(404, 'CHALLENGE_NOT_GENERATED', 'Not generated.', null, 'not-generated', false),
    )
    challengeMocks.generateTodayChallenge.mockResolvedValueOnce({
      challengeId: makePlan().id,
      status: 'generating',
      jobId: 'job-1',
      statusUrl: null,
      replayed: false,
    })
    challengeMocks.getChallengeJob.mockResolvedValue({
      jobId: 'job-1',
      challengeId: makePlan().id,
      status: 'running',
      errorCode: null,
      errorMessage: null,
      retryable: false,
    })
    const { wrapper } = await mountView()
    await wrapper.get('.challenge-generate .button').trigger('click')
    await flushPromises()
    expect(wrapper.text()).toContain('先不等了')
    await wrapper.get('.challenge-generate__waiting [role="button"]').trigger('click')
    await new Promise((resolve) => setTimeout(resolve, 1100))
    await flushPromises()
    expect(wrapper.text()).toContain('已停止等待')
    expect(challengeMocks.getChallengeJob).not.toHaveBeenCalled()
  })

  it('starts a memory node and preserves the server session in the route', async () => {
    const { wrapper, router } = await mountView()
    await wrapper.findAll('.challenge-dsl-card')[0].trigger('click')
    await flushPromises()
    expect(wrapper.text()).toContain('开始节点')
    await wrapper.findAll('.challenge-node-dialog [role="button"]').find((button) => button.text() === '开始节点')!.trigger('click')
    await flushPromises()
    expect(challengeMocks.startChallengeNode).toHaveBeenCalledWith(makePlan().id, mainNodes[0].id)
    expect(router.currentRoute.value.name).toBe('memory')
    expect(router.currentRoute.value.query).toMatchObject({ sessionId: 'memory-session-1', module: 'choice', challengeId: makePlan().id })
  })

  it('shows locked nodes without a start action', async () => {
    challengeMocks.getChallengeNodeDetail.mockResolvedValueOnce(detail(mainNodes[1], []))
    const { wrapper } = await mountView()
    await wrapper.findAll('.challenge-dsl-card')[1].trigger('click')
    await flushPromises()
    expect(wrapper.text()).toContain('完成前一个节点后解锁')
    expect(wrapper.findAll('.challenge-node-dialog [role="button"]').some((button) => button.text() === '开始节点')).toBe(false)
  })

  it('opens the BOSS panel only after a real BOSS start', async () => {
    challengeMocks.getChallengeNodeDetail.mockResolvedValueOnce(detail(mainNodes[2], ['start']))
    challengeMocks.startChallengeNode.mockResolvedValueOnce({ challengeId: makePlan().id, nodeId: mainNodes[2].id, status: 'in_progress', resourceType: 'practice', resourceId: 'boss-session-1', jobId: 'job-1', message: 'The practice task is ready.' })
    const { wrapper } = await mountView()
    await wrapper.findAll('.challenge-dsl-card')[2].trigger('click')
    await flushPromises()
    await wrapper.findAll('.challenge-node-dialog [role="button"]').find((button) => button.text() === '开始节点')!.trigger('click')
    await flushPromises()
    expect(challengeMocks.startChallengeNode).toHaveBeenCalled()
    expect(wrapper.find('[data-test="boss-panel"]').exists()).toBe(true)
  })

  it('keeps the BOSS result panel mounted while the completed map refreshes from the server', async () => {
    const initial = makePlan({
      mainCompleted: 2,
      nodes: [
        { ...mainNodes[0], status: 'completed', completedAt: '2026-10-23T09:00:00Z' },
        { ...mainNodes[1], status: 'completed', completedAt: '2026-10-23T09:10:00Z' },
        { ...mainNodes[2], status: 'in_progress', resourceType: 'practice', resourceId: 'boss-session-1' },
        optionalNode,
      ],
    })
    const completed = makePlan({
      status: 'completed', mainCompleted: 3, challengeCompletedAt: '2026-10-23T09:30:00Z',
      nodes: [
        { ...mainNodes[0], status: 'completed', completedAt: '2026-10-23T09:00:00Z' },
        { ...mainNodes[1], status: 'completed', completedAt: '2026-10-23T09:10:00Z' },
        { ...mainNodes[2], status: 'completed', resourceType: 'practice', resourceId: 'boss-session-1', completedAt: '2026-10-23T09:30:00Z' },
        optionalNode,
      ],
    })
    challengeMocks.getTodayChallenge.mockResolvedValueOnce(initial).mockResolvedValueOnce(completed)
    challengeMocks.getChallengeNodeDetail.mockResolvedValueOnce(detail(initial.nodes[2], ['resume']))
    challengeMocks.startChallengeNode.mockResolvedValueOnce({ challengeId: initial.id, nodeId: mainNodes[2].id, status: 'in_progress', resourceType: 'practice', resourceId: 'boss-session-1', jobId: 'job-1', message: 'The practice task is ready.' })
    const { wrapper } = await mountView()
    await wrapper.findAll('.challenge-dsl-card')[2].trigger('click')
    await flushPromises()
    await wrapper.findAll('.challenge-node-dialog [role="button"]').find((button) => button.text() === '继续节点')!.trigger('click')
    await flushPromises()
    expect(wrapper.find('[data-test="boss-panel"]').exists()).toBe(true)
    await wrapper.get('.emit-boss-completed').trigger('click')
    await flushPromises()
    expect(wrapper.find('[data-test="boss-panel"]').exists()).toBe(true)
    expect(wrapper.text()).toContain('BOSS completed')
    expect(wrapper.text()).not.toContain('BOSS ready')
    expect(wrapper.text()).toContain('主线 3 / 3')
    expect(challengeMocks.getTodayChallenge).toHaveBeenCalledTimes(2)
  })

  it('opens the real completed BOSS result from an already completed node', async () => {
    const completedBoss = makeNode({
      id: mainNodes[2].id,
      clientKey: 'boss-1',
      nodeType: 'BOSS',
      orderIndex: 3,
      title: '终点挑战',
      status: 'completed',
      resourceType: 'practice',
      resourceId: 'boss-session-1',
      completedAt: '2026-10-23T09:30:00Z',
      practiceSpec: { practice_type: 'fill_blank', count: 5 },
    })
    const completedPlan = makePlan({
      status: 'completed', mainCompleted: 3, challengeCompletedAt: '2026-10-23T09:30:00Z',
      nodes: [
        { ...mainNodes[0], status: 'completed', completedAt: '2026-10-23T09:00:00Z' },
        { ...mainNodes[1], status: 'completed', completedAt: '2026-10-23T09:10:00Z' },
        completedBoss,
        optionalNode,
      ],
    })
    challengeMocks.getTodayChallenge.mockResolvedValueOnce(completedPlan)
    challengeMocks.getChallengeNodeDetail.mockResolvedValueOnce(detail(completedBoss, ['view_result']))
    const { wrapper, router } = await mountView()
    await wrapper.findAll('.challenge-dsl-card')[2].trigger('click')
    await flushPromises()
    expect(wrapper.text()).toContain('终点挑战已完成，可查看结果')
    await wrapper.findAll('.challenge-node-dialog [role="button"]').find((button) => button.text() === '查看节点结果')!.trigger('click')
    await flushPromises()
    expect(router.currentRoute.value.fullPath).toBe('/practice/boss-session-1')
    expect(challengeMocks.startChallengeNode).not.toHaveBeenCalled()
  })
  it('keeps a past map read-only even when the server allows no mutation', async () => {
    challengeMocks.getTodayChallenge.mockResolvedValueOnce(makePlan({ localDate: '2026-10-20' }))
    const { wrapper } = await mountView()
    expect(wrapper.text()).toContain('跨日地图只读')
    await wrapper.findAll('.challenge-dsl-card')[0].trigger('click')
    await flushPromises()
    expect(wrapper.text()).toContain('跨日地图只读，不能开始或重做节点')
    const start = wrapper.findAll('.challenge-node-dialog [role="button"]').find((button) => button.text() === '开始节点')
    expect(start?.attributes('aria-disabled')).toBeDefined()
  })

  it('refreshes server-owned completion state and surfaces quota errors', async () => {
    const completed = makePlan({ mainCompleted: 1, nodes: [{ ...mainNodes[0], status: 'completed' }, mainNodes[1], mainNodes[2], optionalNode] })
    challengeMocks.getTodayChallenge.mockResolvedValueOnce(makePlan()).mockResolvedValueOnce(completed)
    const { wrapper } = await mountView()
    await wrapper.findAll('[role="button"]').find((button) => button.text() === '刷新地图')!.trigger('click')
    await flushPromises()
    expect(wrapper.text()).toContain('已完成')
    expect(wrapper.text()).toContain('主线 1 / 3')

    challengeMocks.getTodayChallenge.mockRejectedValueOnce(new ApiError(429, 'AI_QUOTA_EXHAUSTED', 'Quota exhausted.', null, 'challenge-429', true))
    await wrapper.findAll('[role="button"]').find((button) => button.text() === '刷新地图')!.trigger('click')
    await flushPromises()
    expect(wrapper.text()).toContain('今天的 AI 次数已用完')
    expect(wrapper.text()).toContain('challenge-429')
  })
})


