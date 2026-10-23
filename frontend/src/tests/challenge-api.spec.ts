import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { apiClient } from '../api/client'
import { ContractError } from '../api/errors'
import {
  generateTodayChallenge,
  getChallengeHistory,
  getChallengeNodeDetail,
  parseChallengePlan,
  parseChallengeStart,
  serializeChallengeBossAnswers,
  startChallengeNode,
  submitChallengeBoss,
} from '../api/challenge'

const node = {
  id: '11111111-1111-4111-8111-111111111111',
  client_key: 'review-1',
  node_type: 'REVIEW',
  order_index: 1,
  title: '复习回廊',
  description: '复习到期单词。',
  estimated_minutes: 8,
  word_entry_ids: ['22222222-2222-4222-8222-222222222222'],
  practice_spec: {},
  optional: false,
  status: 'unlocked',
  resource_type: null,
  resource_id: null,
  started_at: null,
  completed_at: null,
  error_code: null,
  error_message: null,
}

const planPayload = {
  id: '33333333-3333-4333-8333-333333333333',
  local_date: '2026-10-23',
  status: 'ready',
  title: '今日闯关',
  summary: '先复习，再学习，最后完成挑战。',
  target_minutes: 30,
  daily_plan_id: '44444444-4444-4444-8444-444444444444',
  ai_job_id: null,
  generated_at: '2026-10-23T08:00:00Z',
  locked_at: '2026-10-23T08:00:00Z',
  challenge_completed_at: null,
  expires_at: '2026-10-24T00:00:00Z',
  error_code: null,
  error_message: null,
  main_completed: 1,
  main_total: 3,
  nodes: [node, { ...node, id: '55555555-5555-4555-8555-555555555555', client_key: 'boss-1', node_type: 'BOSS', order_index: 3, title: '终点挑战', status: 'locked' }, { ...node, id: '66666666-6666-4666-8666-666666666666', client_key: 'side-1', node_type: 'OPTIONAL_SIDE', order_index: 4, title: '可选支线', optional: true, status: 'unlocked' }],
}

function jsonResponse(payload: unknown, status = 200): Response {
  return new Response(JSON.stringify(payload), {
    status,
    headers: { 'Content-Type': 'application/json', 'X-Request-ID': 'challenge-request' },
  })
}

describe('challenge API contract', () => {
  beforeEach(() => {
    apiClient.clearCredentials()
    localStorage.clear()
    sessionStorage.clear()
  })
  afterEach(() => {
    vi.restoreAllMocks()
    vi.unstubAllGlobals()
  })

  it('parses map nodes, optional branches, and statuses without deriving progress', () => {
    const plan = parseChallengePlan(planPayload)
    expect(plan).toMatchObject({ id: planPayload.id, status: 'ready', mainCompleted: 1, mainTotal: 3 })
    expect(plan.nodes.map((item) => item.nodeType)).toEqual(['REVIEW', 'BOSS', 'OPTIONAL_SIDE'])
    expect(plan.nodes[2].optional).toBe(true)
    expect(plan.nodes[1].status).toBe('locked')
  })

  it('rejects unknown node types and malformed maps', () => {
    expect(() => parseChallengePlan({ ...planPayload, nodes: [{ ...node, node_type: 'UNKNOWN' }] })).toThrow(ContractError)
    expect(() => parseChallengePlan({ ...planPayload, nodes: null })).toThrow(ContractError)
  })

  it('generates through the 202 endpoint', async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({
      challenge_id: planPayload.id, status: 'generating', job_id: '77777777-7777-4777-8777-777777777777', status_url: '/api/v1/challenges/jobs/77777777-7777-4777-8777-777777777777', replayed: false,
    }, 202))
    vi.stubGlobal('fetch', fetchMock)
    const result = await generateTodayChallenge()
    expect(result.status).toBe('generating')
    expect(result.jobId).toBe('77777777-7777-4777-8777-777777777777')
    expect(fetchMock.mock.calls[0]?.[0]).toBe('/api/v1/challenges/today/generate')
  })

  it('starts a node and preserves server resource routing fields', async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({
      challenge_id: planPayload.id, node_id: node.id, status: 'in_progress', resource_type: 'memory', resource_id: '88888888-8888-4888-8888-888888888888', job_id: null, message: 'The memory task is ready.',
    }))
    vi.stubGlobal('fetch', fetchMock)
    const result = await startChallengeNode(planPayload.id, node.id)
    expect(result).toMatchObject({ resourceType: 'memory', resourceId: '88888888-8888-4888-8888-888888888888' })
    expect(parseChallengeStart({ ...result, challenge_id: result.challengeId, node_id: result.nodeId, resource_type: result.resourceType, resource_id: result.resourceId, job_id: null, message: result.message }).status).toBe('in_progress')
  })

  it('loads node legal actions from the server', async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({ challenge_id: planPayload.id, node, allowed_actions: ['start'] }))
    vi.stubGlobal('fetch', fetchMock)
    const detail = await getChallengeNodeDetail(planPayload.id, node.id)
    expect(detail.allowedActions).toEqual(['start'])
    expect(fetchMock.mock.calls[0]?.[0]).toBe(`/api/v1/challenges/${planPayload.id}/nodes/${node.id}`)
  })

  it('submits BOSS answers with snake_case payload and idempotency key', async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({
      challenge_id: planPayload.id, node_id: node.id, status: 'completed', score: 80, completed: true, submission_id: '99999999-9999-4999-8999-999999999999', result: { question_stats: { total: 5, correct: 4, mistakes: 1 } }, error_code: null, error_message: null, message: 'The final challenge is complete.',
    }))
    vi.stubGlobal('fetch', fetchMock)
    const result = await submitChallengeBoss(planPayload.id, node.id, [
      { questionId: 'q-1', answer: 'a' }, { questionId: 'q-2', answer: 'b' }, { questionId: 'q-3', answer: 'c' }, { questionId: 'q-4', answer: 'd' }, { questionId: 'q-5', answer: 'a' },
    ], 'boss-key')
    expect(result).toMatchObject({ status: 'completed', score: 80, completed: true })
    const [, init] = fetchMock.mock.calls[0] as [string, RequestInit]
    expect((init.headers as Headers).get('Idempotency-Key')).toBe('boss-key')
    expect(JSON.parse(String(init.body))).toEqual({ answers: [
      { question_id: 'q-1', answer: 'a' }, { question_id: 'q-2', answer: 'b' }, { question_id: 'q-3', answer: 'c' }, { question_id: 'q-4', answer: 'd' }, { question_id: 'q-5', answer: 'a' },
    ] })
    expect(serializeChallengeBossAnswers([{ questionId: 'q-1', answer: 'a' }])).toEqual([{ question_id: 'q-1', answer: 'a' }])
  })

  it('loads offset-paginated history', async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({
      items: [{ id: planPayload.id, local_date: '2026-10-23', status: 'completed', title: '今日闯关', summary: '完成', target_minutes: 30, main_completed: 3, main_total: 3, challenge_completed_at: '2026-10-23T09:00:00Z' }],
      next_cursor: '20', has_more: true,
    }))
    vi.stubGlobal('fetch', fetchMock)
    const history = await getChallengeHistory(20, 0)
    expect(history.items[0].status).toBe('completed')
    expect(history.hasMore).toBe(true)
    expect(fetchMock.mock.calls[0]?.[0]).toBe('/api/v1/challenges/history?limit=20&offset=0')
  })
})
