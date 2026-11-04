import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import AiMemoryPanel from '../components/AiMemoryPanel.vue'
import type { AiMemory } from '../api/ai-memory'

const apiMocks = vi.hoisted(() => ({
  listAiMemories: vi.fn(),
  createAiMemory: vi.fn(),
  updateAiMemory: vi.fn(),
  deleteAiMemory: vi.fn(),
  clearAutoAiMemories: vi.fn(),
}))

vi.mock('../api/ai-memory', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../api/ai-memory')>()
  return { ...actual, ...apiMocks }
})

function memory(overrides: Partial<AiMemory> = {}): AiMemory {
  return {
    id: 'memory-1',
    kind: 'practice',
    content: '填空练习 · 3 题 · 正确 2，错误 1 · 得分 67',
    source: 'auto',
    pinned: false,
    createdAt: '2026-11-04T02:00:00Z',
    updatedAt: '2026-11-04T02:00:00Z',
    lastUsedAt: null,
    ...overrides,
  }
}

describe('AiMemoryPanel', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    apiMocks.listAiMemories.mockResolvedValue({
      items: [
        memory(),
        memory({
          id: 'memory-2',
          kind: 'custom',
          content: '我容易混淆 affect 和 effect。',
          source: 'user',
        }),
      ],
      counts: { practice: 1, custom: 1 },
    })
    apiMocks.createAiMemory.mockResolvedValue(memory({ id: 'memory-3', kind: 'custom' }))
    apiMocks.updateAiMemory.mockResolvedValue(memory({ content: '更新后的记忆' }))
    apiMocks.deleteAiMemory.mockResolvedValue(undefined)
    apiMocks.clearAutoAiMemories.mockResolvedValue(1)
  })

  it('lists memories with their kind and source', async () => {
    const wrapper = mount(AiMemoryPanel)
    await flushPromises()
    expect(wrapper.findAll('.ai-memory-item')).toHaveLength(2)
    expect(wrapper.text()).toContain('填空练习')
    expect(wrapper.text()).toContain('自动记录')
    expect(wrapper.text()).toContain('我要求记住')
  })

  it('filters by kind and counts the visible memories', async () => {
    const wrapper = mount(AiMemoryPanel)
    await flushPromises()
    const customChip = wrapper.findAll('.ai-memory-chip').find((chip) => chip.text().startsWith('指定记忆'))
    await customChip!.trigger('click')
    const items = wrapper.findAll('.ai-memory-item')
    expect(items).toHaveLength(1)
    expect(items[0].text()).toContain('affect 和 effect')
  })

  it('adds a memory the learner typed', async () => {
    const wrapper = mount(AiMemoryPanel)
    await flushPromises()
    await wrapper.get('#ai-memory-draft').setValue('请多给我固定搭配的题。')
    await wrapper.get('form.ai-memory-form').trigger('submit')
    await flushPromises()
    expect(apiMocks.createAiMemory).toHaveBeenCalledWith({ kind: 'custom', content: '请多给我固定搭配的题。' })
  })

  it('deletes only the selected memory', async () => {
    const wrapper = mount(AiMemoryPanel)
    await flushPromises()
    const firstItem = wrapper.findAll('.ai-memory-item')[0]
    const deleteButton = firstItem.findAll('[role="button"]').find((button) => button.text() === '删除')
    await deleteButton!.trigger('click')
    await flushPromises()
    expect(apiMocks.deleteAiMemory).toHaveBeenCalledWith('memory-1')
  })

  it('edits a memory and saves the new content', async () => {
    const wrapper = mount(AiMemoryPanel)
    await flushPromises()
    const firstItem = wrapper.findAll('.ai-memory-item')[0]
    const editButton = firstItem.findAll('[role="button"]').find((button) => button.text() === '编辑')
    await editButton!.trigger('click')
    await firstItem.get('textarea').setValue('更新后的记忆')
    const saveButton = firstItem.findAll('[role="button"]').find((button) => button.text() === '保存')
    await saveButton!.trigger('click')
    await flushPromises()
    expect(apiMocks.updateAiMemory).toHaveBeenCalledWith('memory-1', { content: '更新后的记忆' })
  })
})
