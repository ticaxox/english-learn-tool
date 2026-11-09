import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import AdminKnowledgeView from '../views/AdminKnowledgeView.vue'
import type { KnowledgeDocument } from '../api/knowledge'

const knowledgeMocks = vi.hoisted(() => ({
  listKnowledgeDocuments: vi.fn(),
  importKnowledgeDocument: vi.fn(),
  archiveKnowledgeDocument: vi.fn(),
  searchKnowledge: vi.fn(),
}))

vi.mock('../api/knowledge', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../api/knowledge')>()
  return { ...actual, ...knowledgeMocks }
})

const document: KnowledgeDocument = {
  id: 'doc-1',
  sourceType: 'exam',
  title: '2023-06 四级阅读',
  metadata: {},
  status: 'ready',
  chunkCount: 3,
  embeddingModel: null,
  errorMessage: null,
  createdAt: '2026-11-09T02:00:00Z',
  updatedAt: '2026-11-09T02:00:00Z',
}

describe('AdminKnowledgeView', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    knowledgeMocks.listKnowledgeDocuments.mockResolvedValue([document])
    knowledgeMocks.importKnowledgeDocument.mockResolvedValue({ ...document, id: 'doc-2' })
    knowledgeMocks.archiveKnowledgeDocument.mockResolvedValue(undefined)
    knowledgeMocks.searchKnowledge.mockResolvedValue([
      { documentId: 'doc-1', title: '2023-06 四级阅读', content: '夜市…', score: 0.8 },
    ])
  })

  it('lists imported documents with their status', async () => {
    const wrapper = mount(AdminKnowledgeView)
    await flushPromises()
    expect(wrapper.text()).toContain('2023-06 四级阅读')
    expect(wrapper.text()).toContain('3 块')
    expect(wrapper.text()).toContain('已发布')
  })

  it('imports the pasted text', async () => {
    const wrapper = mount(AdminKnowledgeView)
    await flushPromises()
    const inputs = wrapper.findAll('input')
    await inputs[0].setValue('新资料')
    await wrapper.get('textarea').setValue('1. 题目\n答案：A')
    await wrapper.findAll('[role="button"]').find((b) => b.text().includes('导入并索引'))!.trigger('click')
    await flushPromises()
    expect(knowledgeMocks.importKnowledgeDocument).toHaveBeenCalledWith({
      title: '新资料',
      content: '1. 题目\n答案：A',
    })
  })

  it('runs a probe search and shows the hits', async () => {
    const wrapper = mount(AdminKnowledgeView)
    await flushPromises()
    await wrapper.get('.knowledge-probe__form input').setValue('night market')
    await wrapper.get('.knowledge-probe__form').trigger('submit')
    await flushPromises()
    expect(knowledgeMocks.searchKnowledge).toHaveBeenCalledWith('night market')
    expect(wrapper.get('.knowledge-hits').text()).toContain('夜市')
  })

  it('archives a document after confirmation', async () => {
    vi.spyOn(window, 'confirm').mockReturnValue(true)
    const wrapper = mount(AdminKnowledgeView)
    await flushPromises()
    await wrapper.findAll('[role="button"]').find((b) => b.text().includes('下架'))!.trigger('click')
    await flushPromises()
    expect(knowledgeMocks.archiveKnowledgeDocument).toHaveBeenCalledWith('doc-1')
  })
})
