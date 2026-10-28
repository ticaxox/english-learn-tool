import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { AdminUser } from '../api/admin-users'
import { ApiError } from '../api/errors'
import AdminUsersView from '../views/AdminUsersView.vue'

const apiMocks = vi.hoisted(() => ({
  listAdminUsers: vi.fn(),
  createAdminUser: vi.fn(),
  updateAdminUser: vi.fn(),
  deleteAdminUser: vi.fn(),
  getAdminUserDetail: vi.fn(),
  resetAdminUserPassword: vi.fn(),
  previewAdminUserImport: vi.fn(),
  confirmAdminUserImport: vi.fn(),
  getAdminUserImportStatus: vi.fn(),
}))

vi.mock('../api/admin-users', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../api/admin-users')>()
  return { ...actual, ...apiMocks }
})

const adminUser: AdminUser = {
  id: '0ffca5ad-a6a1-4dbc-87b6-2f4f82d2f819',
  username: 'owner_admin',
  display_name: '组织负责人',
  role: 'admin',
  status: 'active',
  must_change_password: false,
  department: '管理组',
  learning_group: null,
  last_login_at: '2026-10-22T12:00:00Z',
  created_at: '2026-10-01T12:00:00Z',
  updated_at: '2026-10-22T12:00:00Z',
}

const memberUser: AdminUser = {
  id: 'f99c12a8-65db-427f-9bfe-39c9dafdb73a',
  username: 'member_one',
  display_name: '成员一号',
  role: 'member',
  status: 'active',
  must_change_password: true,
  department: '产品组',
  learning_group: '学习一组',
  last_login_at: null,
  created_at: '2026-10-20T12:00:00Z',
  updated_at: '2026-10-22T12:00:00Z',
}

function page(items: AdminUser[]) {
  return { items, next_cursor: null, has_more: false }
}

describe('AdminUsersView', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    localStorage.clear()
    sessionStorage.clear()
    apiMocks.listAdminUsers.mockResolvedValue(page([adminUser, memberUser]))
    apiMocks.createAdminUser.mockResolvedValue({
      user: memberUser,
      temporary_password: 'Show-Once-Pass-123!',
    })
    apiMocks.updateAdminUser.mockResolvedValue(memberUser)
    apiMocks.deleteAdminUser.mockResolvedValue(undefined)
    apiMocks.getAdminUserDetail.mockResolvedValue({
      account: memberUser,
      aggregates: {
        active_sessions: 2,
        audit_events_30d: 7,
        learning_metrics_available: false,
        study_minutes: null,
        completed_tasks: null,
        practice_submissions: null,
        ai_usage_count: null,
        error_rate: null,
      },
    })
    apiMocks.resetAdminUserPassword.mockResolvedValue({
      user_id: memberUser.id,
      temporary_password: 'Reset-Pass-123!',
      must_change_password: true,
    })
    apiMocks.previewAdminUserImport.mockResolvedValue({
      preview_id: 'preview-1',
      preview_hash: 'a'.repeat(64),
      expires_at: '2026-10-22T15:00:00Z',
      total_rows: 0,
      valid_rows: 0,
      invalid_rows: 0,
      rows: [],
    })
    apiMocks.confirmAdminUserImport.mockResolvedValue({
      import_id: 'import-1',
      status: 'imported',
      created_count: 0,
      created_users: [],
    })
    apiMocks.getAdminUserImportStatus.mockResolvedValue({
      import_id: 'import-1',
      status: 'imported',
      created_count: 0,
      created_users: [],
      expires_at: '2026-10-22T15:00:00Z',
      used_at: null,
    })
  })

  it('renders real API members without writing browser business storage', async () => {
    const wrapper = mount(AdminUsersView)
    await flushPromises()

    expect(apiMocks.listAdminUsers).toHaveBeenCalledWith(
      expect.objectContaining({ limit: 20, cursor: null }),
    )
    expect(wrapper.text()).toContain('组织负责人')
    expect(wrapper.text()).toContain('成员一号')
    expect(wrapper.text()).toContain('小组：学习一组')
    expect(wrapper.text()).toContain('待改密')
    expect(localStorage.length).toBe(0)
    expect(sessionStorage.length).toBe(0)
  })

  it('creates a member and keeps the one-time password only in the active view', async () => {
    const wrapper = mount(AdminUsersView)
    await flushPromises()

    await wrapper.get('.admin-users__hero button').trigger('click')
    await wrapper.get('#create-username').setValue('member_two')
    await wrapper.get('#create-display-name').setValue('成员二号')
    await wrapper.get('#create-learning-group').setValue('学习二组')
    await wrapper.get('.member-form').trigger('submit')
    await flushPromises()

    expect(apiMocks.createAdminUser).toHaveBeenCalledWith(
      expect.objectContaining({
        username: 'member_two',
        display_name: '成员二号',
        role: 'member',
        learning_group: '学习二组',
      }),
    )
    expect(apiMocks.createAdminUser.mock.calls[0][0].password).toBeUndefined()
    expect(wrapper.text()).toContain('一次性临时密码')
    expect(wrapper.text()).toContain('Show-Once-Pass-123!')
    expect(localStorage.length).toBe(0)
    expect(sessionStorage.length).toBe(0)

    await wrapper.get('.dialog-card--password > button').trigger('click')
    expect(wrapper.text()).not.toContain('Show-Once-Pass-123!')

    await wrapper.get('.create-panel .section-heading button').trigger('click')
    expect(wrapper.find('.create-panel').exists()).toBe(false)
    expect(wrapper.text()).toContain('账号 成员一号（@member_one）已创建')
  })

  it('reads the persisted import status immediately after confirmation', async () => {
    apiMocks.previewAdminUserImport.mockResolvedValue({
      preview_id: 'preview-1',
      preview_hash: 'a'.repeat(64),
      expires_at: '2026-10-22T15:00:00Z',
      total_rows: 1,
      valid_rows: 1,
      invalid_rows: 0,
      rows: [
        {
          line_number: 2,
          username: memberUser.username,
          display_name: memberUser.display_name,
          department: memberUser.department,
          learning_group: memberUser.learning_group,
          status: 'valid',
          errors: [],
        },
      ],
    })
    apiMocks.confirmAdminUserImport.mockResolvedValue({
      import_id: 'import-1',
      status: 'imported',
      created_count: 1,
      created_users: [
        {
          id: memberUser.id,
          username: memberUser.username,
          display_name: memberUser.display_name,
          temporary_password: 'Imported-Pass-123!',
        },
      ],
    })
    apiMocks.getAdminUserImportStatus.mockResolvedValue({
      import_id: 'import-1',
      status: 'imported',
      created_count: 1,
      created_users: [
        {
          id: memberUser.id,
          username: memberUser.username,
          display_name: memberUser.display_name,
        },
      ],
      expires_at: '2026-10-22T15:00:00Z',
      used_at: '2026-10-22T14:31:00Z',
    })

    const wrapper = mount(AdminUsersView)
    await flushPromises()

    const fileInput = wrapper.get('input[type="file"]')
    const file = new File(
      [[
        'username,display_name,initial_password,department,learning_group',
        'member_one,成员一号,,产品组,学习一组',
      ].join('\n')],
      'members.csv',
      { type: 'text/csv' },
    )
    Object.defineProperty(fileInput.element, 'files', {
      configurable: true,
      value: [file],
    })

    await fileInput.trigger('change')
    await wrapper.get('.import-picker > button').trigger('click')
    await flushPromises()
    await wrapper.get('.import-preview .button-row > button').trigger('click')
    await flushPromises()

    expect(apiMocks.confirmAdminUserImport).toHaveBeenCalledWith('preview-1', 'a'.repeat(64))
    expect(apiMocks.getAdminUserImportStatus).toHaveBeenCalledWith('import-1')
    expect(wrapper.text()).toContain('服务端状态：已导入')
  })

  it('retries a failed import-status read with the confirmed import id', async () => {
    apiMocks.previewAdminUserImport.mockResolvedValue({
      preview_id: 'preview-1',
      preview_hash: 'a'.repeat(64),
      expires_at: '2026-10-22T15:00:00Z',
      total_rows: 1,
      valid_rows: 1,
      invalid_rows: 0,
      rows: [
        {
          line_number: 2,
          username: memberUser.username,
          display_name: memberUser.display_name,
          department: memberUser.department,
          learning_group: memberUser.learning_group,
          status: 'valid',
          errors: [],
        },
      ],
    })
    apiMocks.confirmAdminUserImport.mockResolvedValue({
      import_id: 'import-1',
      status: 'imported',
      created_count: 1,
      created_users: [
        {
          id: memberUser.id,
          username: memberUser.username,
          display_name: memberUser.display_name,
          temporary_password: 'Imported-Pass-123!',
        },
      ],
    })
    apiMocks.getAdminUserImportStatus
      .mockRejectedValueOnce(new Error('状态读取失败'))
      .mockResolvedValueOnce({
        import_id: 'import-1',
        status: 'imported',
        created_count: 1,
        created_users: [
          {
            id: memberUser.id,
            username: memberUser.username,
            display_name: memberUser.display_name,
          },
        ],
        expires_at: '2026-10-22T15:00:00Z',
        used_at: '2026-10-22T14:31:00Z',
      })

    const wrapper = mount(AdminUsersView)
    await flushPromises()

    const fileInput = wrapper.get('input[type="file"]')
    const file = new File(
      [[
        'username,display_name,initial_password,department,learning_group',
        'member_one,成员一号,,产品组,学习一组',
      ].join('\n')],
      'members.csv',
      { type: 'text/csv' },
    )
    Object.defineProperty(fileInput.element, 'files', {
      configurable: true,
      value: [file],
    })

    await fileInput.trigger('change')
    await wrapper.get('.import-picker > button').trigger('click')
    await flushPromises()
    await wrapper.get('.import-preview .button-row > button').trigger('click')
    await flushPromises()

    expect(wrapper.text()).toContain('CSV 批次已导入')
    expect(wrapper.text()).toContain('状态读取失败')
    expect(apiMocks.getAdminUserImportStatus).toHaveBeenCalledTimes(1)

    await wrapper.get('.alert-success .button-secondary').trigger('click')
    await flushPromises()

    expect(apiMocks.getAdminUserImportStatus).toHaveBeenCalledTimes(2)
    expect(apiMocks.getAdminUserImportStatus).toHaveBeenNthCalledWith(1, 'import-1')
    expect(apiMocks.getAdminUserImportStatus).toHaveBeenNthCalledWith(2, 'import-1')
    expect(wrapper.text()).toContain('服务端状态：已导入')
  })

  it('loads privacy-safe account aggregates through the real detail endpoint', async () => {
    const wrapper = mount(AdminUsersView)
    await flushPromises()

    const detailButtons = wrapper.findAll('.member-actions-menu__panel button').filter((button) => button.text() === '详情')
    await detailButtons[1].trigger('click')
    await flushPromises()

    expect(apiMocks.getAdminUserDetail).toHaveBeenCalledWith(memberUser.id)
    expect(wrapper.text()).toContain('隐私安全的账号详情')
    expect(wrapper.text()).toContain('活跃会话家族')
    expect(wrapper.text()).toContain('30 天审计事件')
    expect(wrapper.text()).toContain('学习聚合指标尚不可用')
    expect(wrapper.text()).not.toContain('answer_text')
  })

  it('requires the exact target username before deleting and shows a real 403 response', async () => {
    apiMocks.deleteAdminUser.mockRejectedValue(
      new ApiError(409, 'LAST_ADMIN_PROTECTED', 'The last active administrator cannot be deleted.', null, 'req-409'),
    )
    const wrapper = mount(AdminUsersView)
    await flushPromises()

    const deleteButtons = wrapper.findAll('.member-actions-menu__panel button').filter((button) => button.text() === '删除')
    await deleteButtons[0].trigger('click')

    const confirmButton = wrapper.get('.dialog-actions button')
    expect(confirmButton.attributes('disabled')).toBeDefined()

    await wrapper.get('#delete-confirmation').setValue(adminUser.username)
    expect(confirmButton.attributes('disabled')).toBeUndefined()

    await confirmButton.trigger('click')
    await flushPromises()

    expect(apiMocks.deleteAdminUser).toHaveBeenCalledWith(adminUser.id)
    expect(wrapper.text()).toContain('当前状态不允许此操作')
    expect(wrapper.text()).toContain('请刷新后再试')
    expect(wrapper.text()).toContain('req-409')
  })
})
