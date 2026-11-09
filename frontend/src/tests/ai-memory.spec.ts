import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import AiMemoryPanel from '../components/AiMemoryPanel.vue'
import type { CoachMemory } from '../api/coach-memories'

const memoryMocks = vi.hoisted(() => ({
  listCoachMemories: vi.fn(),
  createCoachMemory: vi.fn(),
  deleteCoachMemory: vi.fn(),
}))

vi.mock('../api/coach-memories', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../api/coach-memories')>()
  return { ...actual, ...memoryMocks }
})

const memory: CoachMemory = {
  id: 'memory-1',
  kind: 'preference',
  subjectKey: 'study_time',
  content: '我习惯早上背单词',
  source: 'user_explicit',
  status: 'active',
  importance: 3,
  createdAt: '2026-11-09T01:00:00Z',
  updatedAt: '2026-11-09T01:00:00Z',
  lastUsedAt: null,
}

async function openPanel() {
  const wrapper = mount(AiMemoryPanel)
  await flushPromises()
  await wrapper.findAll('[role="button"]').find((button) => button.text().includes('管理'))!.trigger('click')
  await flushPromises()
  return wrapper
}

describe('AiMemoryPanel', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    memoryMocks.listCoachMemories.mockResolvedValue([memory])
    memoryMocks.createCoachMemory.mockResolvedValue({ ...memory, id: 'memory-2' })
    memoryMocks.deleteCoachMemory.mockResolvedValue(undefined)
  })

  it('lists typed memories with their source', async () => {
    const wrapper = await openPanel()
    expect(wrapper.text()).toContain('我习惯早上背单词')
    expect(wrapper.text()).toContain('偏好')
    expect(wrapper.text()).toContain('你说的')
    // The old single-document textarea is gone.
    expect(wrapper.find('#ai-memory-document').exists()).toBe(false)
  })

  it('adds a memory with the chosen kind', async () => {
    const wrapper = await openPanel()
    await wrapper.get('#ai-memory-content').setValue('目标雅思 7.0')
    await wrapper.get('#ai-memory-kind').setValue('goal')
    await wrapper.get('form.ai-memory-add').trigger('submit')
    await flushPromises()
    expect(memoryMocks.createCoachMemory).toHaveBeenCalledWith({
      kind: 'goal',
      content: '目标雅思 7.0',
    })
  })

  it('forgets a memory after confirmation', async () => {
    const confirm = vi.spyOn(window, 'confirm').mockReturnValue(true)
    const wrapper = await openPanel()
    await wrapper.findAll('[role="button"]').find((button) => button.text().includes('忘记'))!.trigger('click')
    await flushPromises()
    expect(confirm).toHaveBeenCalledTimes(1)
    expect(memoryMocks.deleteCoachMemory).toHaveBeenCalledWith('memory-1')
    expect(wrapper.text()).not.toContain('我习惯早上背单词')
  })
})
