import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import KnowledgeBaseView from '../views/KnowledgeBaseView.vue'
import type { KnowledgeDocument, KnowledgeFolder } from '../api/knowledge'

const mocks = vi.hoisted(() => ({
  listKnowledgeFolders: vi.fn(),
  listFolderDocuments: vi.fn(),
  getKnowledgeDocument: vi.fn(),
  importIntoFolder: vi.fn(),
  deleteKnowledgeDocument: vi.fn(),
  deleteKnowledgeFolder: vi.fn(),
  createKnowledgeFolder: vi.fn(),
  renameKnowledgeDocument: vi.fn(),
  renameKnowledgeFolder: vi.fn(),
}))

vi.mock('../api/knowledge', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../api/knowledge')>()
  return { ...actual, ...mocks }
})

const folder = (over: Partial<KnowledgeFolder>): KnowledgeFolder => ({
  id: 'f',
  parentId: null,
  scope: 'global',
  difficulty: null,
  name: '书架',
  documentCount: 0,
  writable: false,
  isGeneral: false,
  createdAt: '2026-11-01T00:00:00Z',
  updatedAt: '2026-11-01T00:00:00Z',
  ...over,
})

const goals = folder({ id: 'goals', name: '学习目标', writable: true, documentCount: 0 })
const cet4 = folder({ id: 'cet4', parentId: 'goals', name: '四级', difficulty: 'CET4', writable: true, documentCount: 2 })
const mine = folder({ id: 'mine', name: '我的笔记', scope: 'personal', writable: true, documentCount: 1 })

const doc: KnowledgeDocument = {
  id: 'doc-1',
  folderId: 'cet4',
  sourceType: 'exam',
  title: '2023-06 四级阅读',
  metadata: {},
  status: 'ready',
  chunkCount: 8,
  snippet: 'Night markets bring neighbours together.',
  embeddingModel: null,
  errorMessage: null,
  createdAt: '2026-11-09T02:00:00Z',
  updatedAt: '2026-11-09T02:00:00Z',
}

function mountView() {
  return mount(KnowledgeBaseView)
}

describe('KnowledgeBaseView', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
    mocks.listKnowledgeFolders.mockResolvedValue([goals, cet4, mine])
    mocks.listFolderDocuments.mockImplementation((id: string) =>
      Promise.resolve(id === 'goals' ? [] : [doc]),
    )
    mocks.getKnowledgeDocument.mockResolvedValue({
      ...doc,
      content: '夜市把邻里聚在一起。',
      folders: '四级',
    })
    mocks.importIntoFolder.mockResolvedValue(doc)
    mocks.deleteKnowledgeDocument.mockResolvedValue(undefined)
    mocks.deleteKnowledgeFolder.mockResolvedValue(undefined)
    mocks.createKnowledgeFolder.mockResolvedValue(folder({ id: 'new', writable: true }))
    mocks.renameKnowledgeDocument.mockResolvedValue(doc)
    mocks.renameKnowledgeFolder.mockResolvedValue(goals)
  })

  it('shows the global shelves nested, and the learner’s own', async () => {
    const wrapper = mountView()
    await flushPromises()
    const rows = wrapper.findAll('.kb-row').map((row) => row.text())
    expect(rows.some((text) => text.includes('学习目标'))).toBe(true)
    expect(rows.some((text) => text.includes('四级'))).toBe(true)
    expect(rows.some((text) => text.includes('我的笔记'))).toBe(true)
  })

  it('opens the first shelf and lists its documents as cards', async () => {
    const wrapper = mountView()
    await flushPromises()
    expect(mocks.listFolderDocuments).toHaveBeenCalledWith('goals')
    expect(wrapper.find('.kb-doc__title').exists()).toBe(false)

    mocks.listFolderDocuments.mockImplementation((id: string) =>
      Promise.resolve(id === 'goals' ? [] : [doc]),
    )
    await wrapper.findAll('.kb-row')[1].trigger('click')
    await flushPromises()
    expect(wrapper.get('.kb-doc__title').text()).toBe('2023-06 四级阅读')
    expect(wrapper.get('.kb-doc__snippet').text()).toContain('Night markets')
  })

  it('opens a document as a preview', async () => {
    const wrapper = mountView()
    await flushPromises()
    await wrapper.findAll('.kb-row')[1].trigger('click')
    await flushPromises()
    await wrapper.get('.kb-doc__hit').trigger('click')
    await flushPromises()
    expect(mocks.getKnowledgeDocument).toHaveBeenCalledWith('doc-1')
    expect(wrapper.get('.kb-doc-body').text()).toContain('夜市把邻里聚在一起。')
  })

  it('offers delete on a document’s context menu and deletes it', async () => {
    const wrapper = mountView()
    await flushPromises()
    await wrapper.findAll('.kb-row')[1].trigger('click')
    await flushPromises()

    await wrapper.get('.kb-doc').trigger('contextmenu', { clientX: 10, clientY: 10 })
    const items = wrapper.findAll('.kb-ctx button').map((b) => b.text())
    expect(items).toContain('删除资料')

    await wrapper.findAll('.kb-ctx button').find((b) => b.text() === '删除资料')!.trigger('click')
    await flushPromises()
    // the confirm dialog, then its destructive button
    await wrapper.get('.kb-dialog form, form.kb-dialog').trigger('submit')
    await flushPromises()
    expect(mocks.deleteKnowledgeDocument).toHaveBeenCalledWith('doc-1')
  })

  it('imports into the open shelf from the dialog', async () => {
    const wrapper = mountView()
    await flushPromises()
    await wrapper.findAll('.kb-row')[1].trigger('click')
    await flushPromises()

    await wrapper.get('.kb-bar .kb-btn:not(.ghost)').trigger('click')
    await flushPromises()
    await wrapper.get('.kb-dialog input').setValue('2024-06 四级阅读')
    await wrapper.get('.kb-dialog textarea').setValue('1. 题目\n答案：A')
    await wrapper.get('.kb-dialog').trigger('submit')
    await flushPromises()

    expect(mocks.importIntoFolder).toHaveBeenCalledWith('cet4', {
      title: '2024-06 四级阅读',
      content: '1. 题目\n答案：A',
    })
  })

  it('keeps the edit actions away from a read-only shelf', async () => {
    mocks.listKnowledgeFolders.mockResolvedValue([folder({ id: 'ro', name: '只读', writable: false })])
    const wrapper = mountView()
    await flushPromises()
    await wrapper.get('.kb-row').trigger('contextmenu', { clientX: 10, clientY: 10 })
    const items = wrapper.findAll('.kb-ctx button').map((b) => b.text())
    expect(items).toEqual(['打开'])
  })
})
