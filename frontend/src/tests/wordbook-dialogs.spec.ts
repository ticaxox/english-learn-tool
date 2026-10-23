import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { ApiError } from '../api/errors'
import type {
  Wordbook,
  WordbookImportPreview,
  WordbookJob,
} from '../api/wordbooks'
import WordbookDeleteDialog from '../components/WordbookDeleteDialog.vue'
import WordbookExportDialog from '../components/WordbookExportDialog.vue'
import WordbookImportDialog from '../components/WordbookImportDialog.vue'

const apiMocks = vi.hoisted(() => ({
  previewWordbookImport: vi.fn(),
  remapWordbookPreview: vi.fn(),
  confirmWordbookImport: vi.fn(),
  getWordbookJob: vi.fn(),
  createWordbookExport: vi.fn(),
  getExportJob: vi.fn(),
  downloadWordbookExport: vi.fn(),
  deleteWordbook: vi.fn(),
}))

vi.mock('../api/wordbooks', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../api/wordbooks')>()
  return { ...actual, ...apiMocks }
})

const bookId = '0a872f28-9b2f-47f1-8492-23f982e5bf78'
const previewId = '38d3d56d-b5fc-4c49-87bb-6678e31aa229'
const importJobId = '32d8eea3-09a4-49c6-a611-2d6c4a4ab9ef'
const exportJobId = 'd0c54c68-5e96-49ce-a08c-d60635779a23'
const deleteJobId = '4520aca0-47a0-4d27-b3a1-f70d3c5514f1'
const hashA = 'a'.repeat(64)
const hashB = 'b'.repeat(64)

const book: Wordbook = {
  id: bookId,
  name: 'Business English',
  description: 'Working English for product teams',
  visibility: 'organization',
  status: 'ready',
  version: '3',
  entry_count: 128,
  is_active: false,
  owner_id: null,
  created_by: null,
  created_at: '2026-10-20T10:00:00Z',
  updated_at: '2026-10-22T10:00:00Z',
}

const preview: WordbookImportPreview = {
  preview_id: previewId,
  preview_token: 'preview-token-with-enough-length',
  preview_hash: hashA,
  filename: 'new-words.csv',
  detected_format: 'csv',
  encoding: 'utf-8',
  delimiter: ',',
  columns: ['word', 'word_alt', 'meaning_en', 'meaning_zh', 'ipa', 'ignored_note'],
  suggested_mapping: {
    headword: 'word',
    definition_en: 'meaning_en',
    definition_zh: 'meaning_zh',
    phonetic: 'ipa',
    part_of_speech: null,
    example: null,
    example_translation: null,
  },
  mapping: {
    headword: 'word',
    definition_en: 'meaning_en',
    definition_zh: 'meaning_zh',
    phonetic: 'ipa',
    part_of_speech: null,
    example: null,
    example_translation: null,
  },
  ignored_columns: ['word_alt', 'ignored_note'],
  sample_rows: [
    {
      line_number: 2,
      headword: 'scope',
      normalized_headword: 'scope',
      phonetic: '/skəʊp/',
      definitions: [
        {
          part_of_speech: 'noun',
          definition_en: 'the range of a subject',
          definition_zh: '范围',
          example_en: 'This is out of scope.',
          example_translation: '这超出了范围。',
        },
      ],
    },
  ],
  total_rows: 12,
  valid_rows: 12,
  warning_count: 0,
  error_count: 0,
  warnings: [],
  errors: [],
  expires_at: '2099-10-24T10:00:00Z',
  status: 'previewed',
  requested_name: 'new-words',
  requested_description: null,
  requested_visibility: 'private',
}

function makeJob(overrides: Partial<WordbookJob> = {}): WordbookJob {
  return {
    job_id: importJobId,
    kind: 'import',
    status: 'succeeded',
    progress: 100,
    wordbook_id: bookId,
    error_code: null,
    error_message: null,
    result: {},
    download_url: null,
    download_expires_at: null,
    cleanup_status: 'completed',
    created_at: '2026-10-23T01:00:00Z',
    started_at: '2026-10-23T01:00:01Z',
    finished_at: '2026-10-23T01:00:02Z',
    ...overrides,
  }
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
  const file = new File(['word,meaning_en,meaning_zh\nscope,range,范围'], 'new-words.csv', { type: 'text/csv' })
  Object.defineProperty(input.element, 'files', {
    configurable: true,
    value: [file],
  })
  await input.trigger('change')
}

async function openImportPreview(wrapper: VueWrapper): Promise<void> {
  await selectFile(wrapper)
  await buttonByText(wrapper, '预览并检查映射').trigger('click')
  await flushPromises()
}

describe('wordbook dialogs', () => {
  afterEach(() => {
    mountedWrappers.splice(0).forEach((wrapper) => wrapper.unmount())
    document.body.innerHTML = ''
    vi.restoreAllMocks()
  })

  beforeEach(() => {
    vi.clearAllMocks()
    localStorage.clear()
    sessionStorage.clear()
    apiMocks.previewWordbookImport.mockResolvedValue(preview)
    apiMocks.remapWordbookPreview.mockResolvedValue({ ...preview, preview_hash: hashB })
    apiMocks.confirmWordbookImport.mockResolvedValue(makeJob({ status: 'queued', progress: 0 }))
    apiMocks.getWordbookJob.mockResolvedValue(makeJob())
    apiMocks.createWordbookExport.mockResolvedValue(makeJob({
      job_id: exportJobId,
      kind: 'export',
      status: 'queued',
      progress: 0,
      cleanup_status: 'pending',
    }))
    apiMocks.getExportJob.mockResolvedValue(makeJob({
      job_id: exportJobId,
      kind: 'export',
      status: 'succeeded',
      progress: 100,
      download_url: `/api/v1/exports/${exportJobId}/download`,
      download_expires_at: '2099-10-24T10:00:00Z',
    }))
    apiMocks.downloadWordbookExport.mockResolvedValue(new Blob(['word,meaning\nscope,range'], { type: 'text/csv' }))
    apiMocks.deleteWordbook.mockResolvedValue(makeJob({
      job_id: deleteJobId,
      kind: 'delete',
      status: 'queued',
      progress: 0,
      cleanup_status: 'pending',
    }))
  })

  it('shows the exact required mapping fields and member/admin visibility choices', async () => {
    const memberWrapper = track(mount(WordbookImportDialog, { props: { isAdmin: false } }))
    expect(memberWrapper.get('select').text()).toContain('我的私有词书')
    expect(memberWrapper.get('select').text()).not.toContain('组织词书')
    await openImportPreview(memberWrapper)
    expect(memberWrapper.text()).toContain('headword｜单词')
    expect(memberWrapper.text()).toContain('definition_en｜英文释义')
    expect(memberWrapper.text()).toContain('definition_zh｜中文释义')

    const adminWrapper = track(mount(WordbookImportDialog, { props: { isAdmin: true } }))
    expect(adminWrapper.get('select').text()).toContain('组织词书')
  })

  it('previews structured rows, remaps first, confirms with the new hash and polls the real job', async () => {
    const wrapper = track(mount(WordbookImportDialog, { props: { isAdmin: true } }))
    await openImportPreview(wrapper)

    expect(wrapper.text()).toContain('总行数')
    expect(wrapper.text()).toContain('the range of a subject')
    expect(wrapper.text()).toContain('This is out of scope.')
    expect(apiMocks.previewWordbookImport).toHaveBeenCalledWith(expect.any(File), {
      visibility: 'private',
      name: 'new-words',
      description: '',
    })

    await buttonByText(wrapper, '确认导入').trigger('click')
    await flushPromises()

    expect(apiMocks.remapWordbookPreview).toHaveBeenCalledWith(previewId, {
      preview_token: preview.preview_token,
      mapping: expect.objectContaining({
        headword: 'word',
        definition_en: 'meaning_en',
        definition_zh: 'meaning_zh',
      }),
      ignored_columns: ['word_alt', 'ignored_note'],
    })
    expect(apiMocks.confirmWordbookImport).toHaveBeenCalledWith(
      expect.objectContaining({
        preview_id: previewId,
        preview_token: preview.preview_token,
        preview_hash: hashB,
        visibility: 'private',
        name: 'new-words',
        description: null,
      }),
      expect.any(String),
    )
    expect(apiMocks.confirmWordbookImport.mock.calls[0]?.[0]).not.toHaveProperty('mapping')
    expect(apiMocks.getWordbookJob).toHaveBeenCalledWith(importJobId)
    expect(wrapper.emitted('completed')?.[0]).toEqual([bookId])
    expect(wrapper.text()).toContain('导入已完成')
    expect(localStorage.length).toBe(0)
    expect(sessionStorage.length).toBe(0)
  })

  it('blocks confirmation when preview errors or the preview token are unresolved', async () => {
    apiMocks.previewWordbookImport.mockResolvedValue({
      ...preview,
      error_count: 1,
      errors: [{ line_number: 7, code: 'MISSING_DEFINITION', message: '释义不能为空。' }],
    })
    const wrapper = track(mount(WordbookImportDialog, { props: { isAdmin: false } }))
    await openImportPreview(wrapper)

    expect(wrapper.text()).toContain('释义不能为空')
    expect(buttonByText(wrapper, '确认导入').attributes('disabled')).toBeDefined()
  })

  it('blocks confirmation when the in-memory preview is expired', async () => {
    apiMocks.previewWordbookImport.mockResolvedValue({ ...preview, expires_at: '2020-10-24T10:00:00Z' })
    const wrapper = track(mount(WordbookImportDialog, { props: { isAdmin: false } }))
    await openImportPreview(wrapper)

    expect(wrapper.text()).toContain('预览令牌已过期')
    expect(buttonByText(wrapper, '确认导入').attributes('disabled')).toBeDefined()
  })

  it('does not confirm when remapping introduces preview errors', async () => {
    apiMocks.remapWordbookPreview.mockResolvedValue({
      ...preview,
      preview_hash: hashB,
      error_count: 1,
      errors: [{ line_number: 4, code: 'MAPPING_CONFLICT', message: '映射后释义冲突。' }],
    })
    const wrapper = track(mount(WordbookImportDialog, { props: { isAdmin: true } }))
    await openImportPreview(wrapper)

    await buttonByText(wrapper, '确认导入').trigger('click')
    await flushPromises()

    expect(apiMocks.confirmWordbookImport).not.toHaveBeenCalled()
    expect(apiMocks.getWordbookJob).not.toHaveBeenCalled()
    expect(wrapper.text()).toContain('当前字段映射下仍有预览错误')
  })

  it('reuses the confirm key for the same remap hash and rotates it after the mapping changes', async () => {
    apiMocks.remapWordbookPreview
      .mockResolvedValueOnce({ ...preview, preview_hash: hashB })
      .mockResolvedValueOnce({ ...preview, preview_hash: hashB })
      .mockResolvedValueOnce({ ...preview, preview_hash: 'c'.repeat(64) })
    apiMocks.confirmWordbookImport.mockRejectedValue(
      new ApiError(409, 'IMPORT_CONFLICT', '导入状态冲突，请重试。'),
    )
    const wrapper = track(mount(WordbookImportDialog, { props: { isAdmin: true } }))
    await openImportPreview(wrapper)

    await buttonByText(wrapper, '确认导入').trigger('click')
    await flushPromises()
    const firstKey = apiMocks.confirmWordbookImport.mock.calls[0]?.[1]

    await buttonByText(wrapper, '确认导入').trigger('click')
    await flushPromises()
    const retryKey = apiMocks.confirmWordbookImport.mock.calls[1]?.[1]

    const mappingSelect = wrapper.findAll('.wordbook-mapping-grid select')[0]
    if (!mappingSelect) {
      throw new Error('Headword mapping select not found')
    }
    await mappingSelect.setValue('word_alt')
    await buttonByText(wrapper, '确认导入').trigger('click')
    await flushPromises()
    const changedKey = apiMocks.confirmWordbookImport.mock.calls[2]?.[1]

    expect(firstKey).toEqual(expect.any(String))
    expect(retryKey).toBe(firstKey)
    expect(changedKey).not.toBe(firstKey)
  })

  it('does not offer the consumed preview again after a terminal import failure', async () => {
    apiMocks.getWordbookJob.mockResolvedValueOnce(makeJob({
      status: 'failed',
      progress: 55,
      error_code: 'WORDBOOK_JOB_FAILED',
      error_message: '导入后台任务失败。',
    }))
    const wrapper = track(mount(WordbookImportDialog, { props: { isAdmin: true } }))
    await openImportPreview(wrapper)

    await buttonByText(wrapper, '确认导入').trigger('click')
    await flushPromises()

    expect(wrapper.text()).toContain('导入任务失败')
    expect(wrapper.text()).not.toContain('后台导入中')
    expect(wrapper.text()).toContain('预览已失效，请返回文件重新预览')
    expect(buttonByText(wrapper, '请返回文件重新预览').attributes('disabled')).toBeDefined()
  })

  it('creates an export, polls /exports and downloads through the authenticated Blob API', async () => {
    const anchorClick = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {})
    Object.defineProperty(window.URL, 'createObjectURL', {
      configurable: true,
      value: vi.fn(() => 'blob:export'),
    })
    Object.defineProperty(window.URL, 'revokeObjectURL', {
      configurable: true,
      value: vi.fn(),
    })

    const wrapper = track(mount(WordbookExportDialog, { props: { wordbook: book } }))
    await buttonByText(wrapper, '开始导出').trigger('click')
    await flushPromises()

    expect(apiMocks.createWordbookExport).toHaveBeenCalledWith(book.id, { format: 'csv' }, expect.any(String))
    expect(apiMocks.getExportJob).toHaveBeenCalledWith(exportJobId)
    expect(wrapper.text()).toContain('导出已完成')

    await buttonByText(wrapper, '下载 CSV').trigger('click')
    await flushPromises()

    expect(apiMocks.downloadWordbookExport).toHaveBeenCalledWith(exportJobId)
    expect(anchorClick).toHaveBeenCalledOnce()
    expect(window.URL.createObjectURL).toHaveBeenCalledOnce()
  })

  it('validates documented PDF limits and sends page_rows/columns', async () => {
    const wrapper = track(mount(WordbookExportDialog, { props: { wordbook: book } }))
    await wrapper.get('input[value="pdf"]').setValue(true)

    const numberInputs = wrapper.findAll('input[type="number"]')
    await numberInputs[0]?.setValue('101')
    expect(wrapper.text()).toContain('1 到 100')
    expect(buttonByText(wrapper, '开始导出').attributes('disabled')).toBeDefined()

    await numberInputs[0]?.setValue('80')
    await numberInputs[1]?.setValue('4')
    await buttonByText(wrapper, '开始导出').trigger('click')
    await flushPromises()

    expect(apiMocks.createWordbookExport).toHaveBeenCalledWith(
      book.id,
      { format: 'pdf', page_rows: 80, columns: 4 },
      expect.any(String),
    )
  })

  it('shows cancelled export as a failure, never as a completed export', async () => {
    apiMocks.getExportJob.mockResolvedValue(makeJob({
      job_id: exportJobId,
      kind: 'export',
      status: 'cancelled',
      progress: 31,
      error_code: 'EXPORT_CANCELLED',
      error_message: '导出任务已取消。',
    }))
    const wrapper = track(mount(WordbookExportDialog, { props: { wordbook: book } }))

    await buttonByText(wrapper, '开始导出').trigger('click')
    await flushPromises()

    expect(wrapper.text()).toContain('导出任务已取消。')
    expect(wrapper.text()).not.toContain('导出已完成')
  })

  it('rotates the export idempotency key after a terminal failure so retry creates a new job', async () => {
    apiMocks.getExportJob.mockResolvedValueOnce(makeJob({
      job_id: exportJobId,
      kind: 'export',
      status: 'failed',
      progress: 70,
      error_code: 'EXPORT_RENDER_FAILED',
      error_message: 'PDF render failed.',
    }))
    const wrapper = track(mount(WordbookExportDialog, { props: { wordbook: book } }))

    await buttonByText(wrapper, '开始导出').trigger('click')
    await flushPromises()
    const firstKey = apiMocks.createWordbookExport.mock.calls[0]?.[2]
    expect(wrapper.text()).toContain('PDF render failed.')

    await buttonByText(wrapper, '重新创建导出任务').trigger('click')
    await flushPromises()
    const retryKey = apiMocks.createWordbookExport.mock.calls[1]?.[2]

    expect(firstKey).toEqual(expect.any(String))
    expect(retryKey).toEqual(expect.any(String))
    expect(retryKey).not.toBe(firstKey)
  })

  it('requires the exact organization name and waits for delete job success', async () => {
    apiMocks.getWordbookJob.mockResolvedValue(makeJob({
      job_id: deleteJobId,
      kind: 'delete',
      status: 'succeeded',
      progress: 100,
      cleanup_status: 'completed',
    }))
    const wrapper = track(mount(WordbookDeleteDialog, { props: { wordbook: book } }))

    const confirmButton = buttonByText(wrapper, '确认启动删除')
    expect(confirmButton.attributes('disabled')).toBeDefined()
    await wrapper.get('input[autocomplete="off"]').setValue('Business English')
    expect(confirmButton.attributes('disabled')).toBeUndefined()

    await confirmButton.trigger('click')
    await flushPromises()

    expect(apiMocks.deleteWordbook).toHaveBeenCalledWith(book, 'Business English', expect.any(String))
    expect(apiMocks.getWordbookJob).toHaveBeenCalledWith(deleteJobId)
    expect(wrapper.emitted('started')?.[0]).toEqual([book.id])
    expect(wrapper.emitted('completed')?.[0]).toEqual([book.id])
    expect(wrapper.text()).toContain('清理已完成')
  })

  it('does not present a cancelled delete job as completed', async () => {
    apiMocks.getWordbookJob.mockResolvedValue(makeJob({
      job_id: deleteJobId,
      kind: 'delete',
      status: 'cancelled',
      progress: 10,
      error_code: 'DELETE_CANCELLED',
      error_message: '删除任务已取消。',
    }))
    const wrapper = track(mount(WordbookDeleteDialog, { props: { wordbook: book } }))
    await wrapper.get('input[autocomplete="off"]').setValue('Business English')

    await buttonByText(wrapper, '确认启动删除').trigger('click')
    await flushPromises()

    expect(wrapper.text()).toContain('删除任务已取消。')
    expect(wrapper.text()).not.toContain('清理已完成')
    expect(wrapper.emitted('completed')).toBeUndefined()
  })

  it('rotates the delete idempotency key after a terminal failure so retry starts a new task', async () => {
    apiMocks.getWordbookJob.mockResolvedValueOnce(makeJob({
      job_id: deleteJobId,
      kind: 'delete',
      status: 'failed',
      progress: 20,
      error_code: 'WORDBOOK_JOB_FAILED',
      error_message: '删除后台任务失败。',
    }))
    const wrapper = track(mount(WordbookDeleteDialog, { props: { wordbook: book } }))
    await wrapper.get('input[autocomplete="off"]').setValue('Business English')

    await buttonByText(wrapper, '确认启动删除').trigger('click')
    await flushPromises()
    const firstKey = apiMocks.deleteWordbook.mock.calls[0]?.[2]
    expect(wrapper.text()).toContain('删除后台任务失败。')

    await buttonByText(wrapper, '确认启动删除').trigger('click')
    await flushPromises()
    const retryKey = apiMocks.deleteWordbook.mock.calls[1]?.[2]

    expect(firstKey).toEqual(expect.any(String))
    expect(retryKey).toEqual(expect.any(String))
    expect(retryKey).not.toBe(firstKey)
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
})
