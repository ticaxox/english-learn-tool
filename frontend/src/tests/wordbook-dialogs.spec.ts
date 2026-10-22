import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { ApiError } from '../api/errors'
import type { Wordbook, WordbookImportPreview } from '../api/wordbooks'
import WordbookDeleteDialog from '../components/WordbookDeleteDialog.vue'
import WordbookExportDialog from '../components/WordbookExportDialog.vue'
import WordbookImportDialog from '../components/WordbookImportDialog.vue'

const apiMocks = vi.hoisted(() => ({
  previewWordbookImport: vi.fn(),
  confirmWordbookImport: vi.fn(),
  getWordbookDetail: vi.fn(),
  createWordbookExport: vi.fn(),
  getExportJob: vi.fn(),
  deleteWordbook: vi.fn(),
}))

vi.mock('../api/wordbooks', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../api/wordbooks')>()
  return { ...actual, ...apiMocks }
})

const book: Wordbook = {
  id: '0a872f28-9b2f-47f1-8492-23f982e5bf78',
  name: 'Business English',
  description: 'Working English for product teams',
  visibility: 'organization',
  status: 'ready',
  entry_count: 128,
  is_active: false,
  owner_id: null,
  owner_display_name: null,
  created_at: '2026-10-20T10:00:00Z',
  updated_at: '2026-10-22T10:00:00Z',
  import_progress: null,
  import_error: null,
  permissions: { can_activate: true, can_export: true, can_delete: true },
}

const preview: WordbookImportPreview = {
  preview_token: 'preview-token',
  expires_at: '2099-10-24T10:00:00Z',
  detected_format: 'csv',
  encoding: 'utf-8',
  delimiter: ',',
  columns: ['word', 'meaning', 'ipa', 'ignored_note'],
  suggested_mapping: {
    headword: 'word',
    definition: 'meaning',
    phonetic: 'ipa',
    part_of_speech: null,
    example: null,
    example_translation: null,
  },
  sample_rows: [{ word: 'scope', meaning: '范围', ipa: '/skəʊp/', ignored_note: 'note' }],
  total_rows: 12,
  importable_rows: 11,
  warning_count: 1,
  error_count: 1,
  errors: [{ row_number: 7, column: 'meaning', message: '释义不能为空。' }],
}

const mountedWrappers: VueWrapper[] = []

function track(wrapper: VueWrapper): VueWrapper {
  mountedWrappers.push(wrapper)
  return wrapper
}

function untrack(wrapper: VueWrapper): void {
  const index = mountedWrappers.indexOf(wrapper)
  if (index >= 0) {
    mountedWrappers.splice(index, 1)
  }
}

function buttonByText(wrapper: VueWrapper, text: string) {
  const button = wrapper.findAll('button').find((candidate) => candidate.text().includes(text))
  if (!button) {
    throw new Error(`Button not found: ${text}`)
  }
  return button
}

async function selectFile(wrapper: VueWrapper): Promise<void> {
  const input = wrapper.get('input[type="file"]')
  const file = new File(['word,meaning\nscope,范围'], 'new-words.csv', { type: 'text/csv' })
  Object.defineProperty(input.element, 'files', {
    configurable: true,
    value: [file],
  })
  await input.trigger('change')
}

describe('wordbook dialogs', () => {
  afterEach(() => {
    mountedWrappers.splice(0).forEach((wrapper) => wrapper.unmount())
    document.body.innerHTML = ''
  })

  beforeEach(() => {
    vi.clearAllMocks()
    localStorage.clear()
    sessionStorage.clear()
    apiMocks.previewWordbookImport.mockResolvedValue(preview)
    apiMocks.confirmWordbookImport.mockResolvedValue({
      job_id: 'import-1',
      wordbook_id: book.id,
      status: 'queued',
    })
    apiMocks.getWordbookDetail.mockResolvedValue({
      wordbook: { ...book, status: 'ready', entry_count: 12 },
      entries: { items: [], next_cursor: null, has_more: false },
    })
    apiMocks.createWordbookExport.mockResolvedValue({ job_id: 'export-1', status: 'queued' })
    apiMocks.getExportJob.mockResolvedValue({
      job_id: 'export-1',
      status: 'succeeded',
      progress: 100,
      error_code: null,
      error_message: null,
      download_url: '/api/v1/exports/export-1/download',
      expires_at: '2026-10-24T10:00:00Z',
    })
    apiMocks.deleteWordbook.mockResolvedValue({ job_id: 'delete-1', status: 'completed' })
  })

  it('previews, maps and confirms an import only after the real task becomes ready', async () => {
    const wrapper = track(mount(WordbookImportDialog, { props: { isAdmin: true } }))
    await selectFile(wrapper)
    expect((wrapper.get('input[type="text"]').element as HTMLInputElement).value).toBe('new-words')

    await buttonByText(wrapper, '预览并检查映射').trigger('click')
    await flushPromises()

    expect(wrapper.text()).toContain('总行数')
    expect(wrapper.text()).toContain('释义不能为空')
    expect(apiMocks.previewWordbookImport).toHaveBeenCalledWith(expect.any(File), {
      visibility: 'private',
      name: 'new-words',
      description: '',
    })

    await buttonByText(wrapper, '确认导入').trigger('click')
    await flushPromises()

    expect(apiMocks.confirmWordbookImport).toHaveBeenCalledWith(
      expect.objectContaining({
        preview_token: 'preview-token',
        mapping: expect.objectContaining({ headword: 'word', definition: 'meaning' }),
        ignored_columns: ['ignored_note'],
        duplicate_strategy: 'merge',
      }),
      expect.any(String),
    )
    expect(apiMocks.getWordbookDetail).toHaveBeenCalledWith(book.id, null, 1)
    expect(wrapper.emitted('completed')?.[0]).toEqual([book.id])
    expect(wrapper.text()).toContain('导入已完成')
    expect(localStorage.length).toBe(0)
    expect(sessionStorage.length).toBe(0)
  })

  it('blocks confirmation when the in-memory preview token has expired', async () => {
    apiMocks.previewWordbookImport.mockResolvedValue({
      ...preview,
      expires_at: '2020-10-24T10:00:00Z',
    })
    const wrapper = track(mount(WordbookImportDialog, { props: { isAdmin: false } }))
    await selectFile(wrapper)
    await buttonByText(wrapper, '预览并检查映射').trigger('click')
    await flushPromises()

    expect(wrapper.text()).toContain('预览令牌已过期')
    expect(buttonByText(wrapper, '确认导入').attributes('disabled')).toBeDefined()
  })

  it('polls the export task and exposes only the server-provided download URL', async () => {
    const wrapper = track(mount(WordbookExportDialog, { props: { wordbook: book } }))
    await buttonByText(wrapper, '开始导出').trigger('click')
    await flushPromises()

    expect(apiMocks.createWordbookExport).toHaveBeenCalledWith(
      book.id,
      { format: 'csv' },
      expect.any(String),
    )
    expect(apiMocks.getExportJob).toHaveBeenCalledWith('export-1')
    expect(wrapper.text()).toContain('导出已完成')
    expect(wrapper.get('a.button').attributes('href')).toBe('/api/v1/exports/export-1/download')
  })

  it('sends the exact organization name only after explicit confirmation', async () => {
    const wrapper = track(mount(WordbookDeleteDialog, { props: { wordbook: book } }))
    const input = wrapper.get('input[autocomplete="off"]')
    await input.setValue('Business English')
    await buttonByText(wrapper, '确认启动删除').trigger('click')
    await flushPromises()

    expect(apiMocks.deleteWordbook).toHaveBeenCalledWith(book, 'Business English', expect.any(String))
    expect(wrapper.emitted('started')?.[0]).toEqual([book.id])
    expect(wrapper.emitted('completed')?.[0]).toEqual([book.id])
    expect(wrapper.text()).toContain('清理已完成')
  })
  it('returns to the file stage when confirmation reports an expired preview', async () => {
    apiMocks.confirmWordbookImport.mockRejectedValue(
      new ApiError(410, 'WORDBOOK_PREVIEW_EXPIRED', '预览凭证已过期，请重新上传。', null, 'req-410'),
    )
    const wrapper = track(mount(WordbookImportDialog, { props: { isAdmin: true } }))
    await selectFile(wrapper)
    await buttonByText(wrapper, '预览并检查映射').trigger('click')
    await flushPromises()
    await buttonByText(wrapper, '确认导入').trigger('click')
    await flushPromises()

    expect(wrapper.text()).toContain('预览或下载已过期')
    expect(wrapper.text()).toContain('预览已过期、已使用或与当前映射不一致')
    expect(wrapper.text()).toContain('Request ID：req-410')
    expect(wrapper.find('input[type="file"]').exists()).toBe(true)
  })

  it('reuses an import key for the same request and rotates it after the mapping changes', async () => {
    apiMocks.confirmWordbookImport.mockRejectedValue(
      new ApiError(409, 'IMPORT_CONFLICT', '导入状态冲突，请重试。'),
    )
    const wrapper = track(mount(WordbookImportDialog, { props: { isAdmin: true } }))
    await selectFile(wrapper)
    await buttonByText(wrapper, '预览并检查映射').trigger('click')
    await flushPromises()

    await buttonByText(wrapper, '确认导入').trigger('click')
    await flushPromises()
    const firstKey = apiMocks.confirmWordbookImport.mock.calls[0]?.[1]

    await buttonByText(wrapper, '确认导入').trigger('click')
    await flushPromises()
    const retryKey = apiMocks.confirmWordbookImport.mock.calls[1]?.[1]

    const selects = wrapper.findAll('select')
    const duplicateStrategy = selects[selects.length - 1]
    if (!duplicateStrategy) {
      throw new Error('Duplicate strategy select not found')
    }
    await duplicateStrategy.setValue('reject')
    await buttonByText(wrapper, '确认导入').trigger('click')
    await flushPromises()
    const changedKey = apiMocks.confirmWordbookImport.mock.calls[2]?.[1]

    expect(firstKey).toEqual(expect.any(String))
    expect(retryKey).toBe(firstKey)
    expect(changedKey).not.toBe(firstKey)
  })

  it('reuses an export key for the same options and rotates it after a format change', async () => {
    apiMocks.createWordbookExport.mockRejectedValue(
      new ApiError(503, 'EXPORT_UNAVAILABLE', '导出服务暂不可用。'),
    )
    const wrapper = track(mount(WordbookExportDialog, { props: { wordbook: book } }))
    await buttonByText(wrapper, '开始导出').trigger('click')
    await flushPromises()
    const firstKey = apiMocks.createWordbookExport.mock.calls[0]?.[2]

    await buttonByText(wrapper, '重新创建导出任务').trigger('click')
    await flushPromises()
    const retryKey = apiMocks.createWordbookExport.mock.calls[1]?.[2]

    await wrapper.get('input[value="txt"]').setValue(true)
    await buttonByText(wrapper, '重新创建导出任务').trigger('click')
    await flushPromises()
    const changedKey = apiMocks.createWordbookExport.mock.calls[2]?.[2]

    expect(firstKey).toEqual(expect.any(String))
    expect(retryKey).toBe(firstKey)
    expect(changedKey).not.toBe(firstKey)
  })

  it('reuses a delete key when retrying the same confirmed request', async () => {
    apiMocks.deleteWordbook.mockRejectedValue(
      new ApiError(409, 'DELETE_CONFLICT', '删除状态冲突，请重试。'),
    )
    const wrapper = track(mount(WordbookDeleteDialog, { props: { wordbook: book } }))
    await wrapper.get('input[autocomplete="off"]').setValue('Business English')

    await buttonByText(wrapper, '确认启动删除').trigger('click')
    await flushPromises()
    const firstKey = apiMocks.deleteWordbook.mock.calls[0]?.[2]

    await buttonByText(wrapper, '确认启动删除').trigger('click')
    await flushPromises()
    const retryKey = apiMocks.deleteWordbook.mock.calls[1]?.[2]

    expect(firstKey).toEqual(expect.any(String))
    expect(retryKey).toBe(firstKey)
  })

  it('traps tab focus, closes on Escape and restores focus to the opener', async () => {
    const trigger = document.createElement('button')
    trigger.textContent = '打开导出窗口'
    document.body.append(trigger)
    trigger.focus()
    document.body.style.overflow = 'auto'

    const wrapper = track(mount(WordbookExportDialog, {
      props: { wordbook: book },
      attachTo: document.body,
    }))
    await flushPromises()

    const dialog = wrapper.get('[role="dialog"]').element as HTMLElement
    expect(document.activeElement).toBe(dialog)
    expect(document.body.style.overflow).toBe('hidden')

    const focusable = Array.from(dialog.querySelectorAll<HTMLElement>('button:not([disabled])'))
    const first = focusable[0]
    const last = focusable[focusable.length - 1]
    if (!first || !last) {
      throw new Error('Dialog focus targets not found')
    }

    last.focus()
    document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Tab', bubbles: true, cancelable: true }))
    expect(document.activeElement).toBe(first)

    first.focus()
    document.dispatchEvent(new KeyboardEvent('keydown', {
      key: 'Tab',
      shiftKey: true,
      bubbles: true,
      cancelable: true,
    }))
    expect(document.activeElement).toBe(last)

    document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true, cancelable: true }))
    expect(wrapper.emitted('close')).toHaveLength(1)

    untrack(wrapper)
    wrapper.unmount()
    expect(document.activeElement).toBe(trigger)
    expect(document.body.style.overflow).toBe('auto')
  })
  it('guards an export against a double click before the first request resolves', async () => {
    let resolveCreation!: (value: { job_id: string; status: 'queued' }) => void
    apiMocks.createWordbookExport.mockReturnValue(new Promise((resolve) => {
      resolveCreation = resolve
    }))
    const wrapper = track(mount(WordbookExportDialog, { props: { wordbook: book } }))
    const submit = buttonByText(wrapper, '开始导出')

    void submit.trigger('click')
    void submit.trigger('click')
    await flushPromises()
    expect(apiMocks.createWordbookExport).toHaveBeenCalledTimes(1)

    resolveCreation({ job_id: 'export-1', status: 'queued' })
    await flushPromises()
    expect(apiMocks.getExportJob).toHaveBeenCalledTimes(1)
  })

  it('shows a failed export without presenting a success state', async () => {
    apiMocks.getExportJob.mockResolvedValue({
      job_id: 'export-1',
      status: 'failed',
      progress: 42,
      error_code: 'EXPORT_RENDER_FAILED',
      error_message: 'PDF 渲染失败，请重试。',
      download_url: null,
      expires_at: null,
    })
    const wrapper = track(mount(WordbookExportDialog, { props: { wordbook: book } }))

    await buttonByText(wrapper, '开始导出').trigger('click')
    await flushPromises()

    expect(wrapper.text()).toContain('PDF 渲染失败，请重试。')
    expect(wrapper.text()).toContain('导出失败')
    expect(wrapper.text()).not.toContain('导出已完成')
  })
})
