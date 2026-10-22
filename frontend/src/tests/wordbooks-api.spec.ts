import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { apiClient } from '../api/client'
import { ApiError, ContractError, toErrorPresentation } from '../api/errors'
import {
  activateWordbook,
  buildWordbookListQuery,
  canActivateWordbook,
  canDeleteWordbook,
  canExportWordbook,
  canManageWordbook,
  confirmWordbookImport,
  createWordbookExport,
  deleteWordbook,
  downloadWordbookExport,
  getWordbookJob,
  isPreviewExpired,
  normalizeDownloadUrl,
  parseWordbookDetail,
  parseWordbookImportPreview,
  parseWordbookJob,
  parseWordbookList,
  previewWordbookImport,
  remapWordbookPreview,
  validateRequiredMapping,
  validateWordbookFile,
  type Wordbook,
} from '../api/wordbooks'

const bookId = '0a872f28-9b2f-47f1-8492-23f982e5bf78'
const ownerId = '9ad81de0-83b0-44ba-a67c-ad817f73eb7d'
const previewId = '38d3d56d-b5fc-4c49-87bb-6678e31aa229'
const previewHash = 'a'.repeat(64)
const changedHash = 'b'.repeat(64)
const jobId = '32d8eea3-09a4-49c6-a611-2d6c4a4ab9ef'

const bookPayload = {
  id: bookId,
  name: 'Business English',
  description: 'Working English for product teams',
  visibility: 'organization',
  status: 'ready',
  version: '3',
  entry_count: 128,
  is_active: true,
  owner_id: null,
  created_by: ownerId,
  created_at: '2026-10-20T10:00:00Z',
  updated_at: '2026-10-22T10:00:00Z',
  private_body: ['must not surface'],
}

const wordbook = bookPayload as Wordbook

const previewPayload = {
  preview_id: previewId,
  preview_token: 'preview-token-with-enough-length',
  preview_hash: previewHash,
  filename: 'business.csv',
  detected_format: 'csv',
  encoding: 'utf-8-sig',
  delimiter: ',',
  columns: ['word', 'meaning_en', 'meaning_zh', 'ipa', 'ignored_note'],
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
  ignored_columns: ['ignored_note'],
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
  valid_rows: 11,
  warning_count: 1,
  error_count: 1,
  warnings: [{ line_number: null, code: 'ENCODING_NORMALIZED', message: '已按 UTF-8 读取。' }],
  errors: [{ line_number: 7, code: 'MISSING_DEFINITION', message: '释义不能为空。' }],
  expires_at: '2026-10-24T10:00:00Z',
  status: 'previewed',
  requested_name: 'Business Import',
  requested_description: null,
  requested_visibility: 'private',
}

const jobPayload = {
  job_id: jobId,
  kind: 'import',
  status: 'queued',
  progress: 0,
  wordbook_id: bookId,
  error_code: null,
  error_message: null,
  result: {},
  download_url: null,
  download_expires_at: null,
  cleanup_status: 'pending',
  created_at: '2026-10-23T01:00:00Z',
  started_at: null,
  finished_at: null,
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

  it('serializes only the documented offset pagination and sort fields', () => {
    expect(buildWordbookListQuery({ offset: 24, limit: 12, sort: 'updated_at', direction: 'desc' })).toBe(
      '?offset=24&limit=12&sort=updated_at&direction=desc',
    )
    expect(buildWordbookListQuery()).toBe('?offset=0&limit=20')
    expect(() => buildWordbookListQuery({ offset: -1 })).toThrow(ContractError)
    expect(() => buildWordbookListQuery({ limit: 101 })).toThrow(ContractError)
  })

  it('parses the OpenAPI list page and drops fields outside the contract', () => {
    const page = parseWordbookList({ items: [bookPayload], total: 31, offset: 12, limit: 12 })

    expect(page).toMatchObject({ total: 31, offset: 12, limit: 12 })
    expect(page.items[0]).toMatchObject({
      name: 'Business English',
      version: '3',
      visibility: 'organization',
      entry_count: 128,
      is_active: true,
    })
    expect(page.items[0]).not.toHaveProperty('private_body')
    expect(page.items[0]).not.toHaveProperty('permissions')
  })

  it('rejects malformed list pages instead of inventing pagination', () => {
    expect(() => parseWordbookList({ items: 'not-an-array', total: 0, offset: 0, limit: 20 })).toThrow(ContractError)
    expect(() => parseWordbookList({ items: [], offset: 0, limit: 20 })).toThrow(ContractError)
  })

  it('parses array entries with nested definitions and examples', () => {
    const detail = parseWordbookDetail({
      wordbook: bookPayload,
      entries: [
        {
          id: 'entry-1',
          headword: 'Scope',
          normalized_headword: 'scope',
          phonetic: '/skəʊp/',
          definitions: [
            {
              part_of_speech: 'noun',
              definition_en: 'the range of a subject',
              definition_zh: '范围',
              examples: [{ example_en: 'This is out of scope.', example_zh: '这超出了范围。' }],
            },
            {
              part_of_speech: null,
              definition_en: null,
              definition_zh: '机会',
              examples: [],
            },
          ],
          private_note: 'must not surface',
        },
      ],
      total_entries: 1,
      offset: 0,
      limit: 50,
    })

    expect(detail.entries).toHaveLength(1)
    expect(detail.entries[0]).toMatchObject({
      headword: 'Scope',
      normalized_headword: 'scope',
      phonetic: '/skəʊp/',
    })
    expect(detail.entries[0]?.definitions[0]?.examples[0]).toEqual({
      example_en: 'This is out of scope.',
      example_zh: '这超出了范围。',
    })
    expect(detail.entries[0]).not.toHaveProperty('private_note')
  })

  it('uploads the documented multipart preview metadata and parses structured samples', async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(previewPayload, 201))
    vi.stubGlobal('fetch', fetchMock)
    const file = new File(['word,meaning_en,meaning_zh\nscope,range,范围'], 'business.csv', { type: 'text/csv' })

    const preview = await previewWordbookImport(file, {
      visibility: 'private',
      name: 'Business Import',
      description: 'Imported set',
    })

    expect(preview).toMatchObject({
      preview_id: previewId,
      preview_hash: previewHash,
      detected_format: 'csv',
      total_rows: 12,
      valid_rows: 11,
      error_count: 1,
    })
    expect(preview.sample_rows[0]?.definitions[0]?.definition_en).toBe('the range of a subject')
    expect(preview.errors[0]).toEqual({
      line_number: 7,
      code: 'MISSING_DEFINITION',
      message: '释义不能为空。',
    })

    const call = fetchMock.mock.calls[0] as [string, RequestInit]
    expect(call[0]).toBe('/api/v1/wordbooks/import/preview')
    expect(call[1].method).toBe('POST')
    const body = call[1].body as FormData
    expect(body.get('visibility')).toBe('private')
    expect(body.get('name')).toBe('Business Import')
    expect(body.get('description')).toBe('Imported set')
    expect(body.get('file')).toBe(file)
    expect(localStorage.length).toBe(0)
    expect(sessionStorage.length).toBe(0)
  })

  it('remaps mappings and preserves the input token when the response token is empty', async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({
      ...previewPayload,
      preview_token: '',
      preview_hash: changedHash,
      error_count: 0,
      errors: [],
    }))
    vi.stubGlobal('fetch', fetchMock)

    const remapped = await remapWordbookPreview(previewId, {
      preview_token: previewPayload.preview_token,
      mapping: previewPayload.mapping,
      ignored_columns: ['ignored_note'],
    })

    expect(remapped.preview_token).toBe(previewPayload.preview_token)
    expect(remapped.preview_hash).toBe(changedHash)
    expect(remapped.error_count).toBe(0)

    const call = fetchMock.mock.calls[0] as [string, RequestInit]
    expect(call[0]).toBe(`/api/v1/wordbooks/import/previews/${previewId}`)
    expect(call[1].method).toBe('PATCH')
    expect(JSON.parse(String(call[1].body))).toEqual({
      preview_token: previewPayload.preview_token,
      mapping: previewPayload.mapping,
      ignored_columns: ['ignored_note'],
    })
  })

  it('confirms with the remapped preview hash and an idempotency key only', async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(jobPayload, 202))
    vi.stubGlobal('fetch', fetchMock)
    apiClient.setAccessToken('memory-token')
    apiClient.setCsrfToken('csrf-token')

    const result = await confirmWordbookImport({
      preview_id: previewId,
      preview_token: previewPayload.preview_token,
      preview_hash: changedHash,
      visibility: 'organization',
      name: 'Business English',
      description: null,
    }, 'stable-import-key')

    expect(result).toMatchObject({ job_id: jobId, kind: 'import', status: 'queued' })
    const call = fetchMock.mock.calls[0] as [string, RequestInit]
    expect(call[0]).toBe('/api/v1/wordbooks/import')
    expect(call[1].method).toBe('POST')
    expect(headerValue(call[1], 'Idempotency-Key')).toBe('stable-import-key')
    expect(JSON.parse(String(call[1].body))).toEqual({
      preview_id: previewId,
      preview_token: previewPayload.preview_token,
      preview_hash: changedHash,
      visibility: 'organization',
      name: 'Business English',
      description: null,
    })
    expect(JSON.parse(String(call[1].body))).not.toHaveProperty('mapping')
    expect(JSON.parse(String(call[1].body))).not.toHaveProperty('ignored_columns')
    expect(localStorage.length).toBe(0)
    expect(sessionStorage.length).toBe(0)
  })

  it('parses every job state boundary and defaults optional fields to null', () => {
    const job = parseWordbookJob({
      job_id: jobId,
      kind: 'delete',
      status: 'cancelled',
      progress: 37,
      cleanup_status: 'failed',
      created_at: '2026-10-23T01:00:00Z',
    })

    expect(job).toMatchObject({
      status: 'cancelled',
      cleanup_status: 'failed',
      progress: 37,
      wordbook_id: null,
      download_url: null,
      result: {},
    })
    expect(() => parseWordbookJob({ ...jobPayload, result: [] })).toThrow(ContractError)
    expect(() => parseWordbookJob({ ...jobPayload, status: 'completed' })).toThrow(ContractError)
  })

  it('parses real job status polling without changing state names', async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({
      ...jobPayload,
      status: 'running',
      progress: 45,
      started_at: '2026-10-23T01:00:01Z',
      cleanup_status: 'pending',
    }))
    vi.stubGlobal('fetch', fetchMock)

    const job = await getWordbookJob(jobId)
    expect(job.status).toBe('running')
    expect(job.progress).toBe(45)
    expect((fetchMock.mock.calls[0] as [string, RequestInit])[0]).toBe(`/api/v1/wordbooks/jobs/${jobId}`)
  })

  it('activates without an undocumented idempotency header and parses the activation result', async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({
      wordbook_id: bookId,
      is_active: true,
      activated_at: '2026-10-23T01:02:03Z',
    }))
    vi.stubGlobal('fetch', fetchMock)

    const result = await activateWordbook(bookId)

    expect(result).toEqual({
      wordbook_id: bookId,
      is_active: true,
      activated_at: '2026-10-23T01:02:03Z',
    })
    const call = fetchMock.mock.calls[0] as [string, RequestInit]
    expect(call[0]).toBe(`/api/v1/wordbooks/${bookId}/activate`)
    expect(headerValue(call[1], 'Idempotency-Key')).toBeNull()
  })

  it('creates a PDF export with page_rows and columns and keeps the returned full job', async () => {
    const exportJob = {
      ...jobPayload,
      kind: 'export',
      status: 'running',
      progress: 12,
      download_url: `/api/v1/exports/${jobId}/download`,
      download_expires_at: '2026-10-23T02:00:00Z',
    }
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(exportJob, 202))
    vi.stubGlobal('fetch', fetchMock)

    const creation = await createWordbookExport(bookId, {
      format: 'pdf',
      page_rows: 100,
      columns: 4,
    }, 'stable-export-key')

    expect(creation).toMatchObject({
      job_id: jobId,
      kind: 'export',
      status: 'running',
      download_expires_at: '2026-10-23T02:00:00Z',
    })
    const call = fetchMock.mock.calls[0] as [string, RequestInit]
    expect(call[0]).toBe(`/api/v1/wordbooks/${bookId}/export`)
    expect(JSON.parse(String(call[1].body))).toEqual({ format: 'pdf', page_rows: 100, columns: 4 })
    expect(headerValue(call[1], 'Idempotency-Key')).toBe('stable-export-key')
  })

  it('downloads an export as an authenticated blob request', async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response('word,meaning\nscope,range', {
      status: 200,
      headers: { 'Content-Type': 'text/csv' },
    }))
    vi.stubGlobal('fetch', fetchMock)
    apiClient.setAccessToken('memory-token')

    const blob = await downloadWordbookExport(jobId)

    expect(await blob.text()).toBe('word,meaning\nscope,range')
    const call = fetchMock.mock.calls[0] as [string, RequestInit]
    expect(call[0]).toBe(`/api/v1/exports/${jobId}/download`)
    const headers = new Headers(call[1].headers)
    expect(headers.get('Accept')).toBe('application/octet-stream')
    expect(headers.get('Authorization')).toBe('Bearer memory-token')
  })

  it('sends confirm_name for organization deletion and null for private deletion', async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(jsonResponse({ ...jobPayload, kind: 'delete' }, 202))
      .mockResolvedValueOnce(jsonResponse({ ...jobPayload, kind: 'delete' }, 202))
    vi.stubGlobal('fetch', fetchMock)

    await deleteWordbook(wordbook, 'Business English', 'stable-delete-key')
    await deleteWordbook({ ...wordbook, visibility: 'private' }, 'ignored', 'private-delete-key')

    const first = fetchMock.mock.calls[0] as [string, RequestInit]
    expect(first[0]).toBe(`/api/v1/wordbooks/${bookId}`)
    expect(first[1].method).toBe('DELETE')
    expect(JSON.parse(String(first[1].body))).toEqual({ confirm_name: 'Business English' })
    expect(headerValue(first[1], 'Idempotency-Key')).toBe('stable-delete-key')

    const second = fetchMock.mock.calls[1] as [string, RequestInit]
    expect(JSON.parse(String(second[1].body))).toEqual({ confirm_name: null })
  })

  it('validates required mappings, files, expiry and activation/export/delete permissions', () => {
    expect(validateRequiredMapping({
      headword: 'word',
      definition_en: 'meaning_en',
      definition_zh: 'meaning_zh',
    })).toBeNull()
    expect(validateRequiredMapping({ headword: 'word', definition_en: 'meaning_en' })).toContain('definition_zh')
    expect(validateRequiredMapping({
      headword: 'same',
      definition_en: 'same',
      definition_zh: 'meaning_zh',
    })).toContain('不能同时映射')

    expect(validateWordbookFile(new File(['ok'], 'words.txt', { type: 'text/plain' }))).toBeNull()
    expect(validateWordbookFile(new File(['bad'], 'words.docx'))).toContain('仅支持')
    expect(isPreviewExpired('2026-10-22T10:00:00Z', Date.parse('2026-10-22T10:00:00Z'))).toBe(true)
    expect(isPreviewExpired('2026-10-22T10:01:00Z', Date.parse('2026-10-22T10:00:00Z'))).toBe(false)

    const organization = { ...wordbook, is_active: false }
    expect(canActivateWordbook(organization)).toBe(true)
    expect(canManageWordbook(organization, ownerId, false)).toBe(false)
    expect(canManageWordbook(organization, ownerId, true)).toBe(true)
    expect(canExportWordbook(organization, ownerId, true)).toBe(true)
    expect(canDeleteWordbook({ ...organization, status: 'deleting' }, ownerId, true)).toBe(false)

    const privateBook = { ...organization, visibility: 'private' as const, owner_id: ownerId }
    expect(canManageWordbook(privateBook, ownerId, false)).toBe(true)
    expect(canManageWordbook(privateBook, 'other-user', false)).toBe(false)
  })

  it('only accepts same-origin API download paths', () => {
    expect(normalizeDownloadUrl(`/api/v1/exports/${jobId}/download`)).toBe(`/api/v1/exports/${jobId}/download`)
    expect(normalizeDownloadUrl('javascript:alert(1)')).toBeNull()
    expect(normalizeDownloadUrl('https://evil.example/api/v1/exports/1/download')).toBeNull()
  })

  it('presents auth, permission, conflict, expiry, size, format and throttling errors explicitly', () => {
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

  it('rejects a preview response missing required OpenAPI fields', () => {
    const { preview_hash: _ignored, ...incomplete } = previewPayload
    expect(() => parseWordbookImportPreview(incomplete as unknown)).toThrow(ContractError)
  })
})
