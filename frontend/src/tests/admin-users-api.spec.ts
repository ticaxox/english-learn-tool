import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import {
  buildAdminUserQuery,
  confirmAdminUserImport,
  createAdminUser,
  getAdminUserDetail,
  getAdminUserImportStatus,
  parseAdminUserList,
  parseImportPreview,
  previewAdminUserImport,
  redactImportSecrets,
} from '../api/admin-users'
import { apiClient } from '../api/client'
import { ContractError } from '../api/errors'

const memberPayload = {
  id: '76a6ec5c-e2d8-46f2-85c1-ff24c3c014a9',
  username: 'learner_one',
  display_name: '学习者一号',
  role: 'member',
  status: 'active',
  must_change_password: true,
  department: '产品组',
  learning_group: '一组',
  last_login_at: null,
  created_at: '2026-10-22T12:00:00Z',
  updated_at: '2026-10-22T12:00:00Z',
}

const previewHash = 'a'.repeat(64)

describe('admin user contracts', () => {
  beforeEach(() => {
    apiClient.clearCredentials()
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('serializes the documented cursor and filter query', () => {
    expect(
      buildAdminUserQuery({
        search: ' learner ',
        role: 'member',
        status: 'active',
        cursor: 'next-page-token',
        limit: 20,
      }),
    ).toBe('?search=learner&role=member&status=active&cursor=next-page-token&limit=20')
  })

  it('parses the real cursor list response without private content fields', () => {
    const page = parseAdminUserList({
      items: [memberPayload],
      next_cursor: null,
      has_more: false,
      private_answer_text: 'must never be rendered',
    })

    expect(page.items[0]).toMatchObject({
      username: 'learner_one',
      role: 'member',
      status: 'active',
      department: '产品组',
      learning_group: '一组',
    })
    expect(page.items[0]).not.toHaveProperty('private_answer_text')
  })

  it('rejects malformed lists instead of fabricating data', () => {
    expect(() => parseAdminUserList({ items: 'not-an-array', has_more: false })).toThrow(ContractError)
  })

  it('loads a privacy-safe user detail with only allow-listed aggregates', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          account: memberPayload,
          aggregates: {
            active_sessions: 2,
            audit_events_30d: 8,
            learning_metrics_available: false,
            study_minutes: null,
            completed_tasks: null,
            practice_submissions: null,
            ai_usage_count: null,
            error_rate: null,
            private_answers: ['must not surface'],
          },
          private_drafts: ['must not surface'],
        }),
        { status: 200, headers: { 'Content-Type': 'application/json' } },
      ),
    )
    vi.stubGlobal('fetch', fetchMock)

    const result = await getAdminUserDetail(memberPayload.id)

    expect(result.account.username).toBe('learner_one')
    expect(result.aggregates.active_sessions).toBe(2)
    expect(result.aggregates.learning_metrics_available).toBe(false)
    expect(result.aggregates).not.toHaveProperty('private_answers')
    expect(result).not.toHaveProperty('private_drafts')

    const call = fetchMock.mock.calls[0] as [string, RequestInit]
    expect(call[0]).toBe(`/api/v1/admin/users/${memberPayload.id}`)
    expect(call[1].method).toBe('GET')
  })

  it('redacts one-time import passwords before retaining the durable batch result', () => {
    const safe = redactImportSecrets({
      import_id: 'import-1',
      status: 'imported',
      created_count: 1,
      created_users: [
        {
          id: memberPayload.id,
          username: memberPayload.username,
          display_name: memberPayload.display_name,
          temporary_password: 'One-Time-Pass-123!',
        },
      ],
    })

    expect(safe.created_users[0]).not.toHaveProperty('temporary_password')
  })

  it('creates a member through the real endpoint and keeps only the returned temporary password', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          user: memberPayload,
          temporary_password: 'One-Time-Pass-123!',
        }),
        {
          status: 201,
          headers: { 'Content-Type': 'application/json', 'X-Request-ID': 'create-user' },
        },
      ),
    )
    vi.stubGlobal('fetch', fetchMock)
    apiClient.setAccessToken('memory-token')
    apiClient.setCsrfToken('csrf-token')

    const result = await createAdminUser({
      username: 'learner_one',
      display_name: '学习者一号',
      role: 'member',
      department: '产品组',
      learning_group: '一组',
    })

    expect(result.temporary_password).toBe('One-Time-Pass-123!')
    expect(localStorage.length).toBe(0)
    expect(sessionStorage.length).toBe(0)

    const call = fetchMock.mock.calls[0] as [string, RequestInit]
    const headers = new Headers(call[1].headers)
    expect(call[0]).toBe('/api/v1/admin/users')
    expect(call[1].method).toBe('POST')
    expect(call[1].credentials).toBe('include')
    expect(headers.get('Authorization')).toBe('Bearer memory-token')
    expect(headers.get('X-CSRF-Token')).toBe('csrf-token')
  })

  it('uploads CSV as multipart form data for a server-owned preview', async () => {
    const previewPayload = {
      preview_id: 'b59e2aa0-0fec-48f2-ae86-5fc5761dbf1e',
      preview_hash: previewHash,
      expires_at: '2026-10-22T15:00:00Z',
      total_rows: 1,
      valid_rows: 1,
      invalid_rows: 0,
      rows: [
        {
          line_number: 2,
          username: 'learner_two',
          display_name: '学习者二号',
          department: '运营组',
          learning_group: '二组',
          status: 'valid',
          errors: [],
        },
      ],
    }
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify(previewPayload), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      }),
    )
    vi.stubGlobal('fetch', fetchMock)

    const file = new File(['username,display_name,initial_password,department,learning_group'], 'members.csv', {
      type: 'text/csv',
    })
    const result = await previewAdminUserImport(file)

    expect(parseImportPreview(previewPayload).valid_rows).toBe(1)
    expect(result.preview_hash).toBe(previewHash)
    const call = fetchMock.mock.calls[0] as [string, RequestInit]
    expect(call[0]).toBe('/api/v1/admin/users/import/preview')
    expect(call[1].method).toBe('POST')
    expect(call[1].body).toBeInstanceOf(FormData)
    expect((call[1].body as FormData).get('file')).toBeInstanceOf(File)
    expect(new Headers(call[1].headers).get('Content-Type')).toBeNull()
  })

  it('binds import confirmation to both preview id and tamper-evident hash', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          import_id: '40a74caf-7499-45c2-93ff-d8d88b4d60e3',
          status: 'imported',
          created_count: 1,
          created_users: [
            {
              id: '1aa8ad0b-f402-4dc8-91fe-4794d61c9a7c',
              username: 'learner_two',
              display_name: '学习者二号',
              temporary_password: 'Imported-Pass-123!',
            },
          ],
        }),
        {
          status: 202,
          headers: { 'Content-Type': 'application/json' },
        },
      ),
    )
    vi.stubGlobal('fetch', fetchMock)

    const result = await confirmAdminUserImport('preview-1', previewHash)

    expect(result.status).toBe('imported')
    expect(result.created_count).toBe(1)
    const call = fetchMock.mock.calls[0] as [string, RequestInit]
    expect(call[0]).toBe('/api/v1/admin/users/import')
    expect(JSON.parse(String(call[1].body))).toEqual({
      preview_id: 'preview-1',
      preview_hash: previewHash,
    })
  })

  it('polls the persisted import status endpoint', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        new Response(
          JSON.stringify({
            import_id: '40a74caf-7499-45c2-93ff-d8d88b4d60e3',
            status: 'imported',
            created_count: 1,
            created_users: [
              {
                id: '1aa8ad0b-f402-4dc8-91fe-4794d61c9a7c',
                username: 'learner_two',
                display_name: '学习者二号',
              },
            ],
            expires_at: '2026-10-22T15:00:00Z',
            used_at: '2026-10-22T14:31:00Z',
          }),
          { status: 200, headers: { 'Content-Type': 'application/json' } },
        ),
      ),
    )

    const status = await getAdminUserImportStatus('40a74caf-7499-45c2-93ff-d8d88b4d60e3')
    expect(status.status).toBe('imported')
    expect(status.created_count).toBe(1)
  })
})