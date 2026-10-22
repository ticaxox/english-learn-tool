import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { apiClient } from '../api/client'
import { ApiError, ContractError, toErrorPresentation } from '../api/errors'
import {
  activateWordbook,
  buildWordbookListQuery,
  confirmWordbookImport,
  createWordbookExport,
  deleteWordbook,
  isPreviewExpired,
  normalizeDownloadUrl,
  parseExportJob,
  parseWordbookDetail,
  parseWordbookImportPreview,
  parseWordbookList,
  previewWordbookImport,
  validateRequiredMapping,
  validateWordbookFile,
  type Wordbook,
} from '../api/wordbooks'

const bookPayload = {
  id: '0a872f28-9b2f-47f1-8492-23f982e5bf78',
  name: 'Business English',
  description: 'Working English for product teams',
  visibility: 'organization',
  status: 'ready',
  entry_count: 128,
  is_active: true,
  owner_id: null,
  owner_display_name: null,
  created_at: '2026-10-20T10:00:00Z',
  updated_at: '2026-10-22T10:00:00Z',
  import_progress: null,
  import_error: null,
  permissions: {
    can_activate: false,
    can_export: true,
    can_delete: true,
    private_teacher_notes: 'must not surface',
  },
  private_body: ['must not surface'],
}

const wordbook = bookPayload as Wordbook

const previewPayload = {
  preview_token: 'preview-token',
  expires_at: '2026-10-24T10:00:00Z',
  detected_format: 'csv',
  encoding: 'utf-8-sig',
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
  sample_rows: [{ word: 'scope', meaning: '范围', ipa: '/skəʊp/', ignored_note: 'ignore me' }],
  total_rows: 12,
  importable_rows: 11,
  warning_count: 1,
  error_count: 1,
  errors: [{ row_number: 7, column: 'meaning', message: '释义不能为空。' }],
}

function jsonResponse(payload: unknown, status = 200, headers: Record<string, string> = {}): Response {
  return new Response(JSON.stringify(payload), {
    status,
    headers: { 'Content-Type': 'application/json', ...headers },
  })
}

function headerValue(init: RequestInit, name: string): string | null {
  return new Headers(init.headers).get(name)
}

describe('wordbook API contracts', () => {
  beforeEach(() => {
    apiClient.clearCredentials()
    localStorage.clear()
    sessionStorage.clear()
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('serializes documented list search, visibility, cursor and limit', () => {
    expect(buildWordbookListQuery({ search: '  business  ', visibility: 'private', cursor: 'next', limit: 12 })).toBe(
      '?search=business&visibility=private&cursor=next&limit=12',
    )
  })

  it('parses visible wordbooks and drops private fields outside the contract', () => {
    const page = parseWordbookList({ items: [bookPayload], next_cursor: null, has_more: false })

    expect(page.items[0]).toMatchObject({
      name: 'Business English',
      visibility: 'organization',
      entry_count: 128,
      is_active: true,
    })
    expect(page.items[0]).not.toHaveProperty('private_body')
    expect(page.items[0].permissions).not.toHaveProperty('private_teacher_notes')
  })

  it('rejects malformed list data instead of fabricating a wordbook', () => {
    expect(() => parseWordbookList({ items: 'not-an-array', has_more: false })).toThrow(ContractError)
  })

  it('parses read-only detail entries with definitions and examples', () => {
    const detail = parseWordbookDetail({
      wordbook: bookPayload,
      entries: {
        items: [
          {
            id: 'entry-1',
            headword: 'Scope',
            phonetic: '/skəʊp/',
            part_of_speech: 'noun',
            definitions: ['范围', '机会'],
            examples: [{ sentence: 'This is out of scope.', translation: '这超出了范围。' }],
            private_note: 'must not surface',
          },
        ],
        next_cursor: null,
        has_more: false,
      },
    })

    expect(detail.wordbook.name).toBe('Business English')
    expect(detail.entries.items[0]).toMatchObject({
      headword: 'Scope',
      phonetic: '/skəʊp/',
      definitions: ['范围', '机会'],
    })
    expect(detail.entries.items[0]).not.toHaveProperty('private_note')
  })

  it('uploads preview metadata and parses all server-detected fields', async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(previewPayload))
    vi.stubGlobal('fetch', fetchMock)
    const file = new File(['word,meaning\nscope,范围'], 'words.csv', { type: 'text/csv' })

    const preview = await previewWordbookImport(file, {
      visibility: 'private',
      name: 'My Words',
      description: 'Imported set',
    })

    expect(preview.importable_rows).toBe(11)
    expect(preview.suggested_mapping.headword).toBe('word')
    expect(preview.errors[0].row_number).toBe(7)

    const call = fetchMock.mock.calls[0] as [string, RequestInit]
    expect(call[0]).toBe('/api/v1/wordbooks/import/preview')
    expect(call[1].method).toBe('POST')
    const body = call[1].body as FormData
    expect(body.get('file')).toBeInstanceOf(File)
    expect(body.get('visibility')).toBe('private')
    expect(body.get('name')).toBe('My Words')
  })

  it('limits preview errors to the first 100 while retaining the total count', () => {
    const errors = Array.from({ length: 105 }, (_, index) => ({
      row_number: index + 2,
      column: 'meaning',
      message: `错误 ${index + 1}`,
    }))
    const preview = parseWordbookImportPreview({ ...previewPayload, error_count: 105, errors })

    expect(preview.error_count).toBe(105)
    expect(preview.errors).toHaveLength(100)
  })

  it('validates file extension, 10 MiB boundary, required mapping and preview expiry', () => {
    expect(validateWordbookFile(new File(['x'], 'words.CSV'))).toBeNull()
    expect(validateWordbookFile(new File(['x'], 'words.pdf'))).toContain('仅支持')
    expect(validateWordbookFile(new File([new Uint8Array(10 * 1024 * 1024 + 1)], 'words.csv'))).toContain('10 MiB')
    expect(validateRequiredMapping({ headword: 'word', definition: null })).toContain('definition')
    expect(validateRequiredMapping({ headword: 'word', definition: 'meaning' })).toBeNull()
    expect(validateRequiredMapping({ headword: 'word', definition: 'word' })).toContain('同一个源列')
    expect(isPreviewExpired('2026-10-22T10:00:00Z', Date.parse('2026-10-22T10:00:00Z'))).toBe(true)
    expect(isPreviewExpired('2026-10-22T10:01:00Z', Date.parse('2026-10-22T10:00:00Z'))).toBe(false)
  })

  it('confirms the same in-memory preview and sends an idempotency key', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      jsonResponse({ job_id: 'job-1', wordbook_id: bookPayload.id, status: 'queued' }, 202),
    )
    vi.stubGlobal('fetch', fetchMock)
    apiClient.setAccessToken('memory-token')
    apiClient.setCsrfToken('csrf-token')

    const result = await confirmWordbookImport({
      preview_token: 'preview-token',
      visibility: 'organization',
      name: 'Business English',
      description: '',
      mapping: { headword: 'word', definition: 'meaning', phonetic: null },
      ignored_columns: ['ignored_note'],
      duplicate_strategy: 'merge',
    }, 'stable-import-key')

    expect(result).toEqual({ job_id: 'job-1', wordbook_id: bookPayload.id, status: 'queued' })
    const call = fetchMock.mock.calls[0] as [string, RequestInit]
    expect(call[0]).toBe('/api/v1/wordbooks/import')
    expect(headerValue(call[1], 'Idempotency-Key')).toBe('stable-import-key')
    expect(JSON.parse(String(call[1].body))).toMatchObject({
      preview_token: 'preview-token',
      ignored_columns: ['ignored_note'],
      duplicate_strategy: 'merge',
    })
    expect(localStorage.length).toBe(0)
    expect(sessionStorage.length).toBe(0)
  })

  it('uses the same activation key on a retry and rejects unsafe download URLs', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      jsonResponse({ active_wordbook_id: bookPayload.id }),
    )
    vi.stubGlobal('fetch', fetchMock)

    await activateWordbook(bookPayload.id, 'stable-activation-key')

    const call = fetchMock.mock.calls[0] as [string, RequestInit]
    expect(call[0]).toBe(`/api/v1/wordbooks/${bookPayload.id}/activate`)
    expect(headerValue(call[1], 'Idempotency-Key')).toBe('stable-activation-key')
    expect(normalizeDownloadUrl('javascript:alert(1)')).toBeNull()
    expect(normalizeDownloadUrl('/api/v1/exports/job/download')).toBe('/api/v1/exports/job/download')
  })

  it('creates an async export and parses progress plus a short-lived download', async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(jsonResponse({ job_id: 'export-1', status: 'queued' }, 202))
      .mockResolvedValueOnce(jsonResponse({
        job_id: 'export-1',
        status: 'completed',
        progress: 100,
        download_url: '/api/v1/exports/export-1/download',
        expires_at: '2026-10-23T12:00:00Z',
      }))
    vi.stubGlobal('fetch', fetchMock)

    const creation = await createWordbookExport(wordbook.id, {
      format: 'pdf',
      pdf_rows_per_page: 20,
      pdf_words_per_line: 5,
    }, 'stable-export-key')
    expect(creation).toEqual({ job_id: 'export-1', status: 'queued' })

    const job = parseExportJob({
      job_id: 'export-1',
      status: 'completed',
      progress: 100,
      download_url: '/api/v1/exports/export-1/download',
      expires_at: '2026-10-23T12:00:00Z',
    })
    expect(job.status).toBe('succeeded')
    expect(job.progress).toBe(100)
    expect(job.download_url).toContain('/download')

    const call = fetchMock.mock.calls[0] as [string, RequestInit]
    expect(JSON.parse(String(call[1].body))).toEqual({
      format: 'pdf',
      pdf_rows_per_page: 20,
      pdf_words_per_line: 5,
    })
    expect(headerValue(call[1], 'Idempotency-Key')).toBe('stable-export-key')
  })

  it('sends exact organization-name confirmation in a real DELETE request', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      jsonResponse({ job_id: 'delete-1', status: 'deleting' }, 202),
    )
    vi.stubGlobal('fetch', fetchMock)

    const receipt = await deleteWordbook(wordbook, wordbook.name, 'stable-delete-key')
    expect(receipt).toEqual({ job_id: 'delete-1', status: 'deleting' })

    const call = fetchMock.mock.calls[0] as [string, RequestInit]
    expect(call[1].method).toBe('DELETE')
    expect(JSON.parse(String(call[1].body))).toEqual({ confirmation_name: 'Business English' })
    expect(headerValue(call[1], 'Idempotency-Key')).toBe('stable-delete-key')
  })

  it('presents permission, conflict, size, format and throttling errors explicitly', () => {
    const cases: Array<[number, string]> = [
      [401, '认证状态已失效'],
      [403, '权限不足或操作被拒绝'],
      [404, '资源不存在或不可见'],
      [409, '当前状态不允许此操作'],
      [410, '预览或下载已过期'],
      [413, '文件超过服务端限制'],
      [415, '文件格式或媒体类型不受支持'],
      [429, '请求过于频繁'],
    ]
    for (const [status, title] of cases) {
      const presentation = toErrorPresentation(
        new ApiError(status, `HTTP_${status}`, '服务端消息', null, 'req-1'),
      )
      expect(presentation.title).toBe(title)
    }
  })
})