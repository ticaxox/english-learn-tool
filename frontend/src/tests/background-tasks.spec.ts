import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import BackgroundTasksPanel from '../components/BackgroundTasksPanel.vue'
import type { BackgroundTask } from '../api/background-tasks'

const apiMocks = vi.hoisted(() => ({
  listBackgroundTasks: vi.fn(),
  retryBackgroundTask: vi.fn(),
  deleteBackgroundTask: vi.fn(),
}))

vi.mock('../api/background-tasks', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../api/background-tasks')>()
  return { ...actual, ...apiMocks }
})

function task(overrides: Partial<BackgroundTask> = {}): BackgroundTask {
  return {
    id: 'task-1',
    practiceType: 'fill_blank',
    questionCount: 3,
    status: 'generating',
    attempts: 1,
    errorCode: null,
    errorMessage: null,
    createdAt: '2026-11-05T01:00:00Z',
    updatedAt: '2026-11-05T01:00:00Z',
    ...overrides,
  }
}

async function openDialog() {
  const wrapper = mount(BackgroundTasksPanel)
  await flushPromises()
  const openButton = wrapper.findAll('[role="button"]').find((button) => button.text() === '查看后台任务')
  await openButton!.trigger('click')
  await flushPromises()
  return wrapper
}

describe('BackgroundTasksPanel', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    apiMocks.listBackgroundTasks.mockResolvedValue([
      task(),
      task({ id: 'task-2', practiceType: 'reading', questionCount: 5, status: 'ready', attempts: 2 }),
      task({ id: 'task-3', practiceType: 'writing', questionCount: 1, status: 'failed', attempts: 3, errorCode: 'AI_JOB_TIMEOUT' }),
    ])
    apiMocks.retryBackgroundTask.mockResolvedValue(task({ status: 'generating' }))
    apiMocks.deleteBackgroundTask.mockResolvedValue(undefined)
  })

  it('lists background tasks with their status', async () => {
    const wrapper = await openDialog()
    const rows = wrapper.findAll('.background-task')
    expect(rows).toHaveLength(3)
    expect(wrapper.text()).toContain('填空 · 3 题')
    expect(wrapper.text()).toContain('生成中')
    expect(wrapper.text()).toContain('已就绪')
    expect(wrapper.text()).toContain('失败')
    expect(wrapper.text()).toContain('这次生成超时了，可以重试。')
  })

  it('retries a failed task', async () => {
    const wrapper = await openDialog()
    const failedRow = wrapper.findAll('.background-task')[2]
    const retry = failedRow.findAll('[role="button"]').find((button) => button.text() === '重试')
    await retry!.trigger('click')
    await flushPromises()
    expect(apiMocks.retryBackgroundTask).toHaveBeenCalledWith('task-3')
  })

  it('deletes a task after confirmation', async () => {
    vi.spyOn(window, 'confirm').mockReturnValueOnce(true)
    const wrapper = await openDialog()
    const row = wrapper.findAll('.background-task')[0]
    const remove = row.findAll('[role="button"]').find((button) => button.text() === '删除')
    await remove!.trigger('click')
    await flushPromises()
    expect(apiMocks.deleteBackgroundTask).toHaveBeenCalledWith('task-1')
  })

  it('summarizes counts on the settings page', async () => {
    const wrapper = mount(BackgroundTasksPanel)
    await flushPromises()
    expect(wrapper.get('.background-tasks-summary').text()).toContain('生成中 1')
    expect(wrapper.get('.background-tasks-summary').text()).toContain('失败 1')
  })
})
