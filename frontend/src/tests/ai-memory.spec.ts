import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import AiMemoryPanel from '../components/AiMemoryPanel.vue'

const apiMocks = vi.hoisted(() => ({
  getAiMemoryDocument: vi.fn(),
  saveAiMemoryDocument: vi.fn(),
}))

vi.mock('../api/ai-memory', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../api/ai-memory')>()
  return { ...actual, ...apiMocks }
})

const documentBody = {
  content: '用户信息：目标考试：四级\n做题：填空练习 · 3 题 · 全部答对',
  updatedAt: '2026-11-04T12:00:00Z',
}

function saveButton(wrapper: ReturnType<typeof mount>) {
  return wrapper.findAll('[role="button"]').find((button) => button.text().includes('保存记忆'))
}

describe('AiMemoryPanel', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    apiMocks.getAiMemoryDocument.mockResolvedValue(documentBody)
    apiMocks.saveAiMemoryDocument.mockResolvedValue(documentBody)
  })

  it('shows the one memory document in an editable box', async () => {
    const wrapper = mount(AiMemoryPanel)
    await flushPromises()
    const textarea = wrapper.get('#ai-memory-document').element as HTMLTextAreaElement
    expect(textarea.value).toBe(documentBody.content)
    expect(wrapper.text()).toContain('最近更新')
    expect(wrapper.findAll('.ai-memory-item')).toHaveLength(0)
  })

  it('saves the edited document as a whole', async () => {
    const wrapper = mount(AiMemoryPanel)
    await flushPromises()
    await wrapper.get('#ai-memory-document').setValue('用户信息：目标考试：六级\n手动笔记：多练长难句。')
    await saveButton(wrapper)!.trigger('click')
    await flushPromises()
    expect(apiMocks.saveAiMemoryDocument).toHaveBeenCalledWith(
      '用户信息：目标考试：六级\n手动笔记：多练长难句。',
    )
  })

  it('keeps the save action disabled until something changes', async () => {
    const wrapper = mount(AiMemoryPanel)
    await flushPromises()
    expect(saveButton(wrapper)!.attributes('aria-disabled')).toBeDefined()
    await wrapper.get('#ai-memory-document').setValue('新的内容')
    expect(saveButton(wrapper)!.attributes('aria-disabled')).toBeUndefined()
  })
})
