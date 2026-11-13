import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import KnowledgeBaseView from '../views/KnowledgeBaseView.vue'
import type { KnowledgeDocument, KnowledgeFolder } from '../api/knowledge'

const knowledgeMocks = vi.hoisted(() => ({
  listKnowledgeFolders: vi.fn(),
  listFolderDocuments: vi.fn(),
  getKnowledgeDocument: vi.fn(),
  importIntoFolder: vi.fn(),
  deleteKnowledgeDocument: vi.fn(),
  deleteKnowledgeFolder: vi.fn(),
  createKnowledgeFolder: vi.fn(),
}))

vi.mock('../api/knowledge', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../api/knowledge')>()
  return { ...actual, ...knowledgeMocks }
})

const generalFolder: KnowledgeFolder = {
  id: 'f-general',
  parentId: null,
  scope: 'global',
  difficulty: null,
  name: '综合',
  documentCount: 1,
  writable: false,
  isGeneral: true,
  createdAt: '2026-11-01T00:00:00Z',
  updatedAt: '2026-11-01T00:00:00Z',
}

const cet4Folder: KnowledgeFolder = {
  ...generalFolder,
  id: 'f-cet4',
  difficulty: 'CET4',
  name: '四级',
  documentCount: 0,
  isGeneral: false,
}

const myFolder: KnowledgeFolder = {
  ...generalFolder,
  id: 'f-mine',
  scope: 'personal',
  name: '我的笔记',
  documentCount: 2,
  writable: true,
  isGeneral: false,
}

const document: KnowledgeDocument = {
  id: 'doc-1',
  folderId: 'f-general',
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

describe('KnowledgeBaseView', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
    knowledgeMocks.listKnowledgeFolders.mockResolvedValue([generalFolder, cet4Folder, myFolder])
    knowledgeMocks.listFolderDocuments.mockResolvedValue([document])
    knowledgeMocks.getKnowledgeDocument.mockResolvedValue({
      ...document,
      content: '夜市把邻里聚在一起。',
      folders: '综合',
    })
    knowledgeMocks.deleteKnowledgeDocument.mockResolvedValue(undefined)
    knowledgeMocks.deleteKnowledgeFolder.mockResolvedValue(undefined)
    knowledgeMocks.createKnowledgeFolder.mockResolvedValue(myFolder)
  })

  it('shows the global shelves by difficulty and the learner’s own', async () => {
    const wrapper = mount(KnowledgeBaseView)
    await flushPromises()
    const text = wrapper.text()
    expect(text).toContain('全局知识库')
    expect(text).toContain('综合')
    expect(text).toContain('四级')
    expect(text).toContain('我的知识库')
    expect(text).toContain('我的笔记')
  })

  it('nests a child shelf under its parent, collapsed until asked', async () => {
    const child: KnowledgeFolder = {
      ...generalFolder,
      id: 'f-cet4-papers',
      parentId: cet4Folder.id,
      difficulty: null,
      name: '真题',
      documentCount: 4,
    }
    knowledgeMocks.listKnowledgeFolders.mockResolvedValue([
      generalFolder,
      cet4Folder,
      child,
      myFolder,
    ])
    const wrapper = mount(KnowledgeBaseView)
    await flushPromises()

    const shelfNames = (): string[] => wrapper.findAll('.kb-folder').map((b) => b.text())

    // The parent is there, the shelf under it is not — until the caret is used.
    expect(shelfNames().some((name) => name.startsWith('四级'))).toBe(true)
    expect(shelfNames().some((name) => name.startsWith('真题'))).toBe(false)

    const caret = wrapper
      .findAll('.kb-caret')
      .find((b) => b.attributes('aria-label') === '展开')!
    await caret.trigger('click')
    expect(shelfNames().some((name) => name.startsWith('真题'))).toBe(true)
  })

  it('opens the first shelf and lists its documents', async () => {
    const wrapper = mount(KnowledgeBaseView)
    await flushPromises()
    expect(knowledgeMocks.listFolderDocuments).toHaveBeenCalledWith('f-general')
    expect(wrapper.text()).toContain('2023-06 四级阅读')
  })

  it('reads a document when it is clicked', async () => {
    const wrapper = mount(KnowledgeBaseView)
    await flushPromises()
    await wrapper.get('.kb-doc').trigger('click')
    await flushPromises()
    expect(knowledgeMocks.getKnowledgeDocument).toHaveBeenCalledWith('doc-1')
    expect(wrapper.get('.kb-doc-body').text()).toContain('夜市把邻里聚在一起。')
  })

  it('does not offer import on a shelf the learner cannot write to', async () => {
    const wrapper = mount(KnowledgeBaseView)
    await flushPromises()
    expect(wrapper.findAll('[role="button"]').some((b) => b.text().includes('导入资料'))).toBe(false)
  })

  it('offers import when the shelf is the learner’s own', async () => {
    const wrapper = mount(KnowledgeBaseView)
    await flushPromises()
    await wrapper.findAll('.kb-folder').find((b) => b.text().includes('我的笔记'))!.trigger('click')
    await flushPromises()
    expect(wrapper.findAll('[role="button"]').some((b) => b.text().includes('导入资料'))).toBe(true)
  })

  it('deletes a document from the learner’s own shelf', async () => {
    vi.spyOn(window, 'confirm').mockReturnValue(true)
    const wrapper = mount(KnowledgeBaseView)
    await flushPromises()
    // A global shelf is read-only, so the delete control only exists here.
    await wrapper.findAll('.kb-folder').find((b) => b.text().includes('我的笔记'))!.trigger('click')
    await flushPromises()
    await wrapper.get('.kb-doc').trigger('click')
    await flushPromises()
    await wrapper.findAll('[role="button"]').find((b) => b.text() === '删除')!.trigger('click')
    await flushPromises()
    expect(knowledgeMocks.deleteKnowledgeDocument).toHaveBeenCalledWith('doc-1')
  })
})
