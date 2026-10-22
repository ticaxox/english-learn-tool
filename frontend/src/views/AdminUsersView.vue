<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import {
  confirmAdminUserImport,
  createAdminUser,
  deleteAdminUser,
  getAdminUserDetail,
  getAdminUserImportStatus,
  listAdminUsers,
  previewAdminUserImport,
  redactImportSecrets,
  resetAdminUserPassword,
  updateAdminUser,
  type AdminUser,
  type AdminUserDetail,
  type AdminUserRole,
  type AdminUserStatus,
  type ImportConfirmResult,
  type ImportPreview,
  type ImportStatusResult,
} from '../api/admin-users'
import { isApiError } from '../api/errors'
import ErrorNotice from '../components/ErrorNotice.vue'
import LoadingState from '../components/LoadingState.vue'
import { validateStrongPassword, validateUsername } from '../lib/validation'

type ActionKind = 'toggle-status' | 'change-role' | 'reset-password' | 'delete'
type PasswordMode = 'generated' | 'manual'

interface TemporarySecret {
  username: string
  password: string
  context: string
}

const PAGE_SIZE = 20

const users = ref<AdminUser[]>([])
const nextCursor = ref<string | null>(null)
const hasMore = ref(false)
const currentCursor = ref<string | null>(null)
const cursorHistory = ref<Array<string | null>>([])
const loading = ref(false)
const listError = ref<unknown>(null)

const filters = reactive({
  search: '',
  role: '' as AdminUserRole | '',
  status: '' as AdminUserStatus | '',
})
const appliedFilters = reactive({
  search: '',
  role: '' as AdminUserRole | '',
  status: '' as AdminUserStatus | '',
})

const createOpen = ref(false)
const createSubmitting = ref(false)
const createError = ref<unknown>(null)
const operationSuccess = ref('')
const createForm = reactive({
  username: '',
  display_name: '',
  role: 'member' as AdminUserRole,
  department: '',
  learning_group: '',
  password_mode: 'generated' as PasswordMode,
  initial_password: '',
})

const actionUser = ref<AdminUser | null>(null)
const actionKind = ref<ActionKind | null>(null)
const actionSubmitting = ref(false)
const actionError = ref<unknown>(null)
const deleteConfirmation = ref('')
const selectedRole = ref<AdminUserRole>('member')

const fileInput = ref<HTMLInputElement | null>(null)
const selectedFile = ref<File | null>(null)
const fileError = ref<unknown>(null)
const previewLoading = ref(false)
const preview = ref<ImportPreview | null>(null)
const importConfirming = ref(false)
const importResult = ref<ImportConfirmResult | null>(null)
const importError = ref<unknown>(null)
const importStatus = ref<ImportStatusResult | null>(null)
const importStatusLoading = ref(false)

const temporarySecrets = ref<TemporarySecret[]>([])
const temporaryDialogOpen = ref(false)
const copiedUsername = ref('')

const detailUser = ref<AdminUser | null>(null)
const detail = ref<AdminUserDetail | null>(null)
const detailLoading = ref(false)
const detailError = ref<unknown>(null)

const filtered = computed(() => Boolean(appliedFilters.search || appliedFilters.role || appliedFilters.status))
const actionTitle = computed(() => {
  switch (actionKind.value) {
    case 'toggle-status':
      return actionUser.value && isActive(actionUser.value) ? '确认停用成员' : '确认启用成员'
    case 'change-role':
      return '确认修改角色'
    case 'reset-password':
      return '确认重置密码'
    case 'delete':
      return '删除成员'
    default:
      return '确认操作'
  }
})
const actionDescription = computed(() => {
  const user = actionUser.value
  if (!user) {
    return ''
  }

  switch (actionKind.value) {
    case 'toggle-status':
      return isActive(user)
        ? `停用后，${user.display_name} 的所有刷新会话会被撤销，且不能继续登录。`
        : `启用后，${user.display_name} 将可以重新登录。`
    case 'change-role':
      return `将 ${user.display_name} 的角色改为${roleLabel(selectedRole.value)}。后端会再次校验最后管理员保护。`
    case 'reset-password':
      return `系统会撤销 ${user.display_name} 的全部会话，并生成一次性临时密码。`
    case 'delete':
      return `删除是不可恢复的硬删除，将清理 ${user.display_name} 的个人学习数据。`
    default:
      return ''
  }
})
const actionRisk = computed(() => {
  const user = actionUser.value
  if (!user || user.role !== 'admin' || !isActive(user)) {
    return ''
  }
  if (
    actionKind.value === 'delete' ||
    (actionKind.value === 'toggle-status' && isActive(user)) ||
    (actionKind.value === 'change-role' && selectedRole.value === 'member')
  ) {
    return '若这是系统中最后一名启用管理员，后端会拒绝本次操作。最终判定始终以服务端为准。'
  }
  return ''
})
const canConfirmAction = computed(() => {
  if (actionKind.value === 'delete') {
    return Boolean(actionUser.value && deleteConfirmation.value === actionUser.value.username)
  }
  return true
})
const previewInvalidRows = computed(() => preview.value?.invalid_rows ?? 0)

function isActive(user: AdminUser): boolean {
  return user.status === 'active'
}

function roleLabel(role: AdminUserRole): string {
  return role === 'admin' ? '管理员' : '成员'
}

function statusLabel(status: string): string {
  if (status === 'active') {
    return '启用'
  }
  if (status === 'disabled') {
    return '停用'
  }
  return status
}

function formatDate(value?: string | null): string {
  if (!value) {
    return '—'
  }
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? value : new Intl.DateTimeFormat('zh-CN').format(date)
}


async function loadUsers(targetCursor: string | null = currentCursor.value): Promise<void> {
  loading.value = true
  listError.value = null

  try {
    const page = await listAdminUsers({
      search: appliedFilters.search,
      role: appliedFilters.role,
      status: appliedFilters.status,
      cursor: targetCursor,
      limit: PAGE_SIZE,
    })
    users.value = page.items
    nextCursor.value = page.next_cursor
    hasMore.value = page.has_more
    currentCursor.value = targetCursor
  } catch (error) {
    users.value = []
    nextCursor.value = null
    hasMore.value = false
    listError.value = error
  } finally {
    loading.value = false
  }
}

async function applyFilters(): Promise<void> {
  appliedFilters.search = filters.search.trim()
  appliedFilters.role = filters.role
  appliedFilters.status = filters.status
  cursorHistory.value = []
  currentCursor.value = null
  await loadUsers(null)
}

async function clearFilters(): Promise<void> {
  filters.search = ''
  filters.role = ''
  filters.status = ''
  await applyFilters()
}

async function goNext(): Promise<void> {
  if (!hasMore.value || !nextCursor.value || loading.value) {
    return
  }
  cursorHistory.value.push(currentCursor.value)
  currentCursor.value = nextCursor.value
  await loadUsers(nextCursor.value)
}

async function goPrevious(): Promise<void> {
  if (cursorHistory.value.length === 0 || loading.value) {
    return
  }
  const target = cursorHistory.value.pop() ?? null
  currentCursor.value = target
  await loadUsers(target)
}

function resetCreateForm(): void {
  createForm.username = ''
  createForm.display_name = ''
  createForm.role = 'member'
  createForm.department = ''
  createForm.learning_group = ''
  createForm.password_mode = 'generated'
  createForm.initial_password = ''
}

function toggleCreatePanel(): void {
  createOpen.value = !createOpen.value
  createError.value = null
}

async function submitCreate(): Promise<void> {
  createError.value = null
  operationSuccess.value = ''

  const usernameError = validateUsername(createForm.username.trim())
  if (usernameError) {
    createError.value = new Error(usernameError)
    return
  }
  if (!createForm.display_name.trim()) {
    createError.value = new Error('请输入显示名称。')
    return
  }
  if (createForm.password_mode === 'manual') {
    const passwordError = validateStrongPassword(createForm.initial_password)
    if (passwordError) {
      createError.value = new Error(passwordError)
      return
    }
  }

  createSubmitting.value = true
  try {
    const result = await createAdminUser({
      username: createForm.username.trim(),
      display_name: createForm.display_name.trim(),
      role: createForm.role,
      department: createForm.department.trim() || null,
      learning_group: createForm.learning_group.trim() || null,
      password: createForm.password_mode === 'manual' ? createForm.initial_password : undefined,
    })

    operationSuccess.value = `账号 ${result.user.display_name}（@${result.user.username}）已创建。`
    if (result.temporary_password) {
      showSecrets([
        {
          username: result.user.username,
          password: result.temporary_password,
          context: '创建成员的一次性临时密码',
        },
      ])
    }
    resetCreateForm()
    await loadUsers()
  } catch (error) {
    createError.value = error
  } finally {
    createSubmitting.value = false
  }
}

function openAction(user: AdminUser, kind: ActionKind): void {
  actionUser.value = user
  actionKind.value = kind
  actionError.value = null
  deleteConfirmation.value = ''
  selectedRole.value = user.role === 'admin' ? 'member' : 'admin'
}

function closeAction(): void {
  if (actionSubmitting.value) {
    return
  }
  actionUser.value = null
  actionKind.value = null
  actionError.value = null
  deleteConfirmation.value = ''
}

let detailRequestId = 0

async function openDetail(user: AdminUser): Promise<void> {
  const requestId = ++detailRequestId
  detailUser.value = user
  detail.value = null
  detailError.value = null
  detailLoading.value = true
  try {
    const result = await getAdminUserDetail(user.id)
    if (requestId === detailRequestId) {
      detail.value = result
    }
  } catch (error) {
    if (requestId === detailRequestId) {
      detailError.value = error
    }
  } finally {
    if (requestId === detailRequestId) {
      detailLoading.value = false
    }
  }
}

function retryDetail(): void {
  if (detailUser.value) {
    void openDetail(detailUser.value)
  }
}

function closeDetail(): void {
  detailRequestId += 1
  detailUser.value = null
  detail.value = null
  detailError.value = null
  detailLoading.value = false
}

async function confirmAction(): Promise<void> {
  const user = actionUser.value
  const kind = actionKind.value
  if (!user || !kind || !canConfirmAction.value) {
    return
  }

  actionSubmitting.value = true
  actionError.value = null
  try {
    if (kind === 'toggle-status') {
      await updateAdminUser(user.id, { status: isActive(user) ? 'disabled' : 'active' })
    } else if (kind === 'change-role') {
      await updateAdminUser(user.id, { role: selectedRole.value })
    } else if (kind === 'reset-password') {
      const result = await resetAdminUserPassword(user.id)
      showSecrets([
        {
          username: user.username,
          password: result.temporary_password,
          context: '管理员重置的一次性临时密码',
        },
      ])
    } else {
      await deleteAdminUser(user.id)
    }

    const completedMessage =
      kind === 'toggle-status'
        ? `${user.display_name} 已${isActive(user) ? '停用' : '启用'}。`
        : kind === 'change-role'
          ? `${user.display_name} 的角色已更新。`
          : kind === 'reset-password'
            ? `${user.display_name} 的密码已重置。`
            : `${user.display_name} 已删除。`

    actionSubmitting.value = false
    closeAction()
    operationSuccess.value = completedMessage
    await loadUsers()
  } catch (error) {
    actionError.value = error
  } finally {
    actionSubmitting.value = false
  }
}

function onFileChange(event: Event): void {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0] ?? null
  selectedFile.value = file
  preview.value = null
  importResult.value = null
  importStatus.value = null
  fileError.value = null
  importError.value = null

  if (!file) {
    return
  }
  if (!file.name.toLowerCase().endsWith('.csv')) {
    fileError.value = new Error('请选择 CSV 文件。')
    selectedFile.value = null
    input.value = ''
    return
  }
  if (file.size > 1_000_000) {
    fileError.value = new Error('CSV 文件不能超过 1 MB。')
    selectedFile.value = null
    input.value = ''
  }
}

async function requestPreview(): Promise<void> {
  if (!selectedFile.value) {
    fileError.value = new Error('请先选择 CSV 文件。')
    return
  }

  previewLoading.value = true
  fileError.value = null
  importError.value = null
  importResult.value = null
  importStatus.value = null
  try {
    preview.value = await previewAdminUserImport(selectedFile.value)
  } catch (error) {
    preview.value = null
    fileError.value = error
  } finally {
    previewLoading.value = false
  }
}

async function confirmImport(): Promise<void> {
  if (!preview.value) {
    return
  }

  importConfirming.value = true
  importError.value = null
  try {
    const result = await confirmAdminUserImport(
      preview.value.preview_id,
      preview.value.preview_hash,
    )
    const oneTimeUsers = result.created_users.filter(
      (item): item is typeof item & { temporary_password: string } =>
        typeof item.temporary_password === 'string' && item.temporary_password.length > 0,
    )
    const safeResult = redactImportSecrets(result)
    importResult.value = safeResult
    importStatus.value = null
    if (oneTimeUsers.length > 0) {
      showSecrets(
        oneTimeUsers.map((item) => ({
          username: item.username,
          password: item.temporary_password,
          context: 'CSV 导入的一次性临时密码',
        })),
      )
    }
    preview.value = null
    selectedFile.value = null
    if (fileInput.value) {
      fileInput.value.value = ''
    }
    await loadUsers()

    try {
      importStatus.value = await getAdminUserImportStatus(safeResult.import_id)
    } catch (error) {
      // The import already succeeded; surface a persisted-status read error without reversing that result.
      importError.value = error
    }
  } catch (error) {
    importError.value = error
  } finally {
    importConfirming.value = false
  }
}

function importStatusLabel(status: ImportStatusResult['status']): string {
  switch (status) {
    case 'previewed':
      return '已预览，尚未确认'
    case 'imported':
      return '已导入'
    case 'failed':
      return '失败'
    case 'expired':
      return '已过期'
  }
}

async function refreshImportStatus(): Promise<void> {
  const importId = importStatus.value?.import_id ?? importResult.value?.import_id
  if (!importId) {
    return
  }

  importStatusLoading.value = true
  importError.value = null
  try {
    importStatus.value = await getAdminUserImportStatus(importId)
  } catch (error) {
    importError.value = error
  } finally {
    importStatusLoading.value = false
  }
}

function showSecrets(secrets: TemporarySecret[]): void {
  temporarySecrets.value = secrets
  copiedUsername.value = ''
  temporaryDialogOpen.value = true
}

function closeTemporaryDialog(): void {
  temporaryDialogOpen.value = false
  temporarySecrets.value = []
  copiedUsername.value = ''
}

async function copyPassword(secret: TemporarySecret): Promise<void> {
  try {
    await navigator.clipboard.writeText(secret.password)
    copiedUsername.value = secret.username
  } catch {
    copiedUsername.value = ''
    temporarySecrets.value = temporarySecrets.value.map((item) => ({ ...item }))
  }
}

function apiErrorCode(error: unknown): string {
  return isApiError(error) ? error.code : ''
}

function metricValue(value: number | null, suffix = ''): string {
  return value === null ? '—' : `${value}${suffix}`
}

function errorRateValue(value: number | null): string {
  return value === null ? '—' : `${(value * 100).toFixed(1)}%`
}

onMounted(() => loadUsers(null))
</script>

<template>
  <article class="admin-users">
    <header class="page-header admin-users__hero">
      <div>
        <p class="eyebrow">组织管理员</p>
        <h1>成员管理</h1>
        <p>只展示账号、角色、状态和允许的聚合指标；不提供答题正文、草稿、教练对话或私有词书正文入口。</p>
      </div>
      <button type="button" @click="toggleCreatePanel">
        {{ createOpen ? '收起创建表单' : '添加成员' }}
      </button>
    </header>

    <div class="alert alert-warning privacy-note" role="note">
      <strong>隐私边界</strong>
      <p>此处数据仅用于组织账号管理。权限和最后管理员保护必须由后端服务再次校验，前端提示不能替代服务端判断。</p>
    </div>

    <div v-if="operationSuccess" class="alert alert-success" role="status">
      {{ operationSuccess }}
    </div>

    <section v-if="createOpen" class="panel create-panel" aria-labelledby="create-title">
      <div class="section-heading">
        <div>
          <p class="eyebrow">单个创建</p>
          <h2 id="create-title">添加一名成员</h2>
        </div>
        <button class="button-secondary button-small" type="button" @click="toggleCreatePanel">关闭</button>
      </div>

      <ErrorNotice v-if="createError" :error="createError" />

      <form class="member-form" @submit.prevent="submitCreate">
        <div class="field">
          <label for="create-username">用户名</label>
          <input
            id="create-username"
            v-model="createForm.username"
            autocomplete="off"
            minlength="3"
            maxlength="32"
            required
            :disabled="createSubmitting"
          />
          <p class="field-hint">3–32 位英文字母、数字或下划线，大小写不敏感唯一。</p>
        </div>
        <div class="field">
          <label for="create-display-name">显示名称</label>
          <input
            id="create-display-name"
            v-model="createForm.display_name"
            autocomplete="off"
            maxlength="100"
            required
            :disabled="createSubmitting"
          />
        </div>
        <div class="field">
          <label for="create-role">角色</label>
          <select id="create-role" v-model="createForm.role" :disabled="createSubmitting">
            <option value="member">成员</option>
            <option value="admin">管理员</option>
          </select>
        </div>
        <div class="field">
          <label for="create-department">部门</label>
          <input
            id="create-department"
            v-model="createForm.department"
            autocomplete="organization"
            maxlength="100"
            placeholder="可选"
            :disabled="createSubmitting"
          />
        </div>
        <div class="field">
          <label for="create-learning-group">学习小组</label>
          <input
            id="create-learning-group"
            v-model="createForm.learning_group"
            maxlength="100"
            placeholder="可选"
            :disabled="createSubmitting"
          />
        </div>
        <fieldset class="field password-mode-field">
          <legend>初始密码</legend>
          <label class="radio-row">
            <input
              v-model="createForm.password_mode"
              type="radio"
              value="generated"
              :disabled="createSubmitting"
            />
            由系统生成一次性临时密码
          </label>
          <label class="radio-row">
            <input
              v-model="createForm.password_mode"
              type="radio"
              value="manual"
              :disabled="createSubmitting"
            />
            由管理员填写
          </label>
        </fieldset>
        <div v-if="createForm.password_mode === 'manual'" class="field member-form__full">
          <label for="create-password">初始密码</label>
          <input
            id="create-password"
            v-model="createForm.initial_password"
            type="password"
            autocomplete="new-password"
            minlength="12"
            maxlength="128"
            required
            :disabled="createSubmitting"
          />
          <p class="field-hint">12–128 位，至少包含大写字母、小写字母、数字和特殊字符中的三类。</p>
        </div>
        <div class="member-form__full button-row">
          <button type="submit" :disabled="createSubmitting">
            {{ createSubmitting ? '正在创建真实成员…' : '创建成员' }}
          </button>
          <button class="button-secondary" type="button" :disabled="createSubmitting" @click="resetCreateForm">
            清空
          </button>
        </div>
      </form>
    </section>

    <section class="panel" aria-labelledby="member-list-title">
      <div class="section-heading">
        <div>
          <p class="eyebrow">真实成员列表</p>
          <h2 id="member-list-title">组织账号</h2>
        </div>
        <span class="count-pill" role="status">
          {{ users.length }} 项已加载
        </span>
      </div>

      <form class="filter-bar" role="search" @submit.prevent="applyFilters">
        <div class="field filter-bar__search">
          <label for="member-search">搜索</label>
          <input
            id="member-search"
            v-model="filters.search"
            type="search"
            autocomplete="off"
            placeholder="用户名或显示名称"
          />
        </div>
        <div class="field">
          <label for="member-role">角色</label>
          <select id="member-role" v-model="filters.role">
            <option value="">全部角色</option>
            <option value="member">成员</option>
            <option value="admin">管理员</option>
          </select>
        </div>
        <div class="field">
          <label for="member-status">状态</label>
          <select id="member-status" v-model="filters.status">
            <option value="">全部状态</option>
            <option value="active">启用</option>
            <option value="disabled">停用</option>
          </select>
        </div>
        <div class="button-row filter-bar__actions">
          <button type="submit" :disabled="loading">筛选</button>
          <button
            class="button-secondary"
            type="button"
            :disabled="loading || !filtered"
            @click="clearFilters"
          >
            清除
          </button>
        </div>
      </form>

      <LoadingState v-if="loading" label="正在读取真实成员列表…" />
      <ErrorNotice
        v-else-if="listError"
        :error="listError"
        retry-label="重新读取成员"
        @retry="loadUsers()"
      />

      <div v-else-if="users.length === 0" class="empty-state">
        <strong>{{ filtered ? '没有符合条件的成员' : '尚未创建成员' }}</strong>
        <p>{{ filtered ? '调整搜索或筛选条件后重试。' : '可通过单个表单或 CSV 导入创建第一名成员。' }}</p>
      </div>

      <div v-else class="table-wrap">
        <table class="data-table member-table">
          <thead>
            <tr>
              <th scope="col">成员</th>
              <th scope="col">角色</th>
              <th scope="col">状态</th>
              <th scope="col">部门 / 小组</th>
              <th scope="col">最近登录</th>
              <th scope="col">创建时间</th>
              <th scope="col"><span class="sr-only">操作</span></th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="user in users" :key="user.id">
              <td>
                <strong class="member-name">{{ user.display_name }}</strong>
                <span class="member-handle">@{{ user.username }}</span>
                <span v-if="user.must_change_password" class="mini-badge">待改密</span>
              </td>
              <td><span class="role-badge" :class="`role-badge--${user.role}`">{{ roleLabel(user.role) }}</span></td>
              <td>
                <span class="status-badge" :class="{ 'status-badge--active': isActive(user) }">
                  {{ statusLabel(user.status) }}
                </span>
              </td>
              <td>
                <span class="cell-line">{{ user.department || '—' }}</span>
                <span v-if="user.learning_group" class="cell-line muted">小组：{{ user.learning_group }}</span>
              </td>
              <td>{{ formatDate(user.last_login_at) }}</td>
              <td>{{ formatDate(user.created_at) }}</td>
              <td>
                <div class="row-actions">
                  <button class="button-secondary button-small" type="button" @click="openDetail(user)">
                    详情
                  </button>
                  <button class="button-secondary button-small" type="button" @click="openAction(user, 'toggle-status')">
                    {{ isActive(user) ? '停用' : '启用' }}
                  </button>
                  <button class="button-secondary button-small" type="button" @click="openAction(user, 'change-role')">
                    角色
                  </button>
                  <button class="button-secondary button-small" type="button" @click="openAction(user, 'reset-password')">
                    重置密码
                  </button>
                  <button class="button-danger button-small" type="button" @click="openAction(user, 'delete')">
                    删除
                  </button>
                </div>
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <nav v-if="!loading && !listError && (cursorHistory.length > 0 || hasMore)" class="pagination" aria-label="成员列表分页">
        <button class="button-secondary" type="button" :disabled="cursorHistory.length === 0" @click="goPrevious">
          上一页
        </button>
        <span>每页最多 {{ PAGE_SIZE }} 项</span>
        <button class="button-secondary" type="button" :disabled="!hasMore" @click="goNext">下一页</button>
      </nav>
    </section>

    <section class="panel" aria-labelledby="import-title">
      <div class="section-heading">
        <div>
          <p class="eyebrow">CSV 批量导入</p>
          <h2 id="import-title">预览后确认</h2>
        </div>
        <span class="count-pill">仅创建普通成员</span>
      </div>
      <p class="muted">
        表头必须包含 username、display_name、initial_password、department、learning_group。
        初始密码留空时由后端生成一次性临时密码；预览结果、逐行错误和确认结果均来自真实后端，确认后整批成功或整批失败。
      </p>

      <div class="import-picker">
        <label class="field">
          <span>选择 CSV 文件</span>
          <input
            ref="fileInput"
            type="file"
            accept=".csv,text/csv"
            :disabled="previewLoading || importConfirming"
            @change="onFileChange"
          />
        </label>
        <span v-if="selectedFile" class="file-chip">{{ selectedFile.name }}</span>
        <button type="button" :disabled="!selectedFile || previewLoading" @click="requestPreview">
          {{ previewLoading ? '正在预览…' : '上传并预览' }}
        </button>
      </div>

      <ErrorNotice v-if="fileError" :error="fileError" />
      <LoadingState v-if="previewLoading" label="正在解析真实 CSV…" />

      <div v-if="preview" class="import-preview" aria-live="polite">
        <div class="summary-grid">
          <div><strong>{{ preview.total_rows }}</strong><span>总行数</span></div>
          <div><strong>{{ preview.valid_rows }}</strong><span>可导入</span></div>
          <div><strong>{{ preview.invalid_rows }}</strong><span>不可导入</span></div>
          <div><strong>{{ preview.rows.filter((row) => row.status === 'conflict').length }}</strong><span>用户名冲突</span></div>
        </div>
        <p class="muted">预览有效期至 {{ formatDate(preview.expires_at) }}；确认时会提交预览哈希，防止内容被篡改。</p>

        <div class="table-wrap">
          <table class="data-table import-table">
            <thead>
              <tr>
                <th scope="col">行</th>
                <th scope="col">用户名</th>
                <th scope="col">显示名称</th>
                <th scope="col">部门 / 小组</th>
                <th scope="col">结果</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="row in preview.rows" :key="row.line_number" :class="{ 'row-invalid': row.status !== 'valid' }">
                <td>{{ row.line_number }}</td>
                <td>{{ row.username || '—' }}</td>
                <td>{{ row.display_name || '—' }}</td>
                <td>
                  <span class="cell-line">{{ row.department || '—' }}</span>
                  <span v-if="row.learning_group" class="cell-line muted">小组：{{ row.learning_group }}</span>
                </td>
                <td>
                  <span v-if="row.status === 'valid'" class="status-badge status-badge--active">可导入</span>
                  <span v-else-if="row.status === 'conflict'" class="status-badge">用户名冲突</span>
                  <span v-else class="status-badge">格式错误</span>
                  <ul v-if="row.errors.length" class="row-errors">
                    <li v-for="error in row.errors" :key="error">{{ error }}</li>
                  </ul>
                </td>
              </tr>
            </tbody>
          </table>
        </div>

        <div class="button-row">
          <button
            type="button"
            :disabled="importConfirming || preview.total_rows === 0 || previewInvalidRows > 0"
            @click="confirmImport"
          >
            {{ importConfirming ? '正在确认导入…' : `确认导入 ${preview.total_rows} 行` }}
          </button>
          <span v-if="previewInvalidRows > 0" class="muted">存在错误或冲突时，后端会整批拒绝。</span>
        </div>
      </div>

      <ErrorNotice v-if="importError" :error="importError" />

      <div
        v-if="importResult"
        class="alert"
        :class="importResult.status === 'imported' ? 'alert-success' : 'alert-error'"
        role="status"
      >
        <strong>{{ importResult.status === 'imported' ? 'CSV 批次已导入' : 'CSV 批次导入失败' }}</strong>
        <p>创建成员：{{ importResult.created_count }} 名。</p>
        <p>批次编号：<code>{{ importResult.import_id }}</code></p>
        <button class="button-secondary button-small" type="button" :disabled="importStatusLoading" @click="refreshImportStatus">
          {{ importStatusLoading ? '正在读取真实状态…' : '重新读取批次状态' }}
        </button>
        <p v-if="importStatus">
          服务端状态：<strong>{{ importStatusLabel(importStatus.status) }}</strong>
        </p>
      </div>
    </section>

    <div v-if="detailUser" class="dialog-backdrop" role="presentation" @click.self="closeDetail">
      <section class="dialog-card dialog-card--detail" role="dialog" aria-modal="true" aria-labelledby="member-detail-title">
        <p class="eyebrow">隐私安全的账号详情</p>
        <h2 id="member-detail-title">{{ detailUser.display_name }}</h2>
        <p class="muted">
          仅展示账号、角色、状态与后端允许的聚合指标；不读取答案、草稿、教练对话或私有词书正文。
        </p>

        <LoadingState v-if="detailLoading" label="正在读取真实成员详情…" />
        <ErrorNotice v-else-if="detailError" :error="detailError" retry-label="重新读取详情" @retry="retryDetail" />

        <template v-else-if="detail">
          <div class="summary-grid detail-summary">
            <div>
              <strong>{{ detail.aggregates.active_sessions }}</strong>
              <span>活跃会话家族</span>
            </div>
            <div>
              <strong>{{ detail.aggregates.audit_events_30d }}</strong>
              <span>30 天审计事件</span>
            </div>
            <div>
              <strong>{{ detail.aggregates.learning_metrics_available ? '可用' : '暂不可用' }}</strong>
              <span>学习指标状态</span>
            </div>
          </div>

          <dl class="detail-list">
            <dt>账号</dt>
            <dd>@{{ detail.account.username }}</dd>
            <dt>角色 / 状态</dt>
            <dd>{{ roleLabel(detail.account.role) }} · {{ statusLabel(detail.account.status) }}</dd>
            <dt>部门 / 小组</dt>
            <dd>{{ detail.account.department || '—' }} · {{ detail.account.learning_group || '—' }}</dd>
            <dt>最近登录</dt>
            <dd>{{ formatDate(detail.account.last_login_at) }}</dd>
            <dt>账号更新</dt>
            <dd>{{ formatDate(detail.account.updated_at) }}</dd>
          </dl>

          <div v-if="detail.aggregates.learning_metrics_available" class="summary-grid detail-summary">
            <div><strong>{{ metricValue(detail.aggregates.study_minutes, ' 分钟') }}</strong><span>学习时长</span></div>
            <div><strong>{{ metricValue(detail.aggregates.completed_tasks) }}</strong><span>完成任务</span></div>
            <div><strong>{{ metricValue(detail.aggregates.practice_submissions) }}</strong><span>练习提交</span></div>
            <div><strong>{{ metricValue(detail.aggregates.ai_usage_count) }}</strong><span>AI 使用次数</span></div>
            <div><strong>{{ errorRateValue(detail.aggregates.error_rate) }}</strong><span>错误率</span></div>
          </div>
          <p v-else class="muted">学习聚合指标尚不可用，页面不会用静态数字补位。</p>
        </template>

        <div class="button-row dialog-actions">
          <button class="button-secondary" type="button" :disabled="detailLoading" @click="closeDetail">
            关闭详情
          </button>
        </div>
      </section>
    </div>

    <div v-if="actionUser" class="dialog-backdrop" role="presentation" @click.self="closeAction">
      <section class="dialog-card" role="dialog" aria-modal="true" :aria-labelledby="'action-dialog-title'">
        <p class="eyebrow">服务端校验</p>
        <h2 id="action-dialog-title">{{ actionTitle }}</h2>
        <p>{{ actionDescription }}</p>

        <div v-if="actionRisk" class="alert alert-warning" role="alert">
          <strong>最后管理员保护</strong>
          <p>{{ actionRisk }}</p>
        </div>

        <div v-if="actionKind === 'change-role'" class="field">
          <label for="action-role">新角色</label>
          <select id="action-role" v-model="selectedRole" :disabled="actionSubmitting">
            <option value="member">成员</option>
            <option value="admin">管理员</option>
          </select>
        </div>

        <div v-if="actionKind === 'delete'" class="field">
          <label for="delete-confirmation">输入目标用户名 <code>{{ actionUser.username }}</code> 以确认删除</label>
          <input
            id="delete-confirmation"
            v-model="deleteConfirmation"
            autocomplete="off"
            :disabled="actionSubmitting"
          />
        </div>

        <ErrorNotice v-if="actionError" :error="actionError" />

        <div class="button-row dialog-actions">
          <button
            :class="{ 'button-danger': actionKind === 'delete' }"
            type="button"
            :disabled="actionSubmitting || !canConfirmAction"
            @click="confirmAction"
          >
            {{ actionSubmitting ? '正在请求服务端…' : '确认' }}
          </button>
          <button class="button-secondary" type="button" :disabled="actionSubmitting" @click="closeAction">
            取消
          </button>
        </div>
        <p v-if="apiErrorCode(actionError)" class="request-id">
          错误码：<code>{{ apiErrorCode(actionError) }}</code>
        </p>
      </section>
    </div>

    <div v-if="temporaryDialogOpen" class="dialog-backdrop" role="presentation">
      <section class="dialog-card dialog-card--password" role="dialog" aria-modal="true" aria-labelledby="password-dialog-title">
        <p class="eyebrow">仅显示一次</p>
        <h2 id="password-dialog-title">一次性临时密码</h2>
        <p>关闭后页面不会从 localStorage、sessionStorage 或本地业务缓存恢复这些密码。请通过安全渠道立即交付给对应成员。</p>

        <ul class="secret-list">
          <li v-for="secret in temporarySecrets" :key="`${secret.username}-${secret.password}`">
            <div>
              <strong>@{{ secret.username }}</strong>
              <span>{{ secret.context }}</span>
            </div>
            <div class="secret-value">
              <code>{{ secret.password }}</code>
              <button class="button-secondary button-small" type="button" @click="copyPassword(secret)">
                {{ copiedUsername === secret.username ? '已复制' : '复制' }}
              </button>
            </div>
          </li>
        </ul>

        <button type="button" @click="closeTemporaryDialog">我已安全保存，关闭</button>
      </section>
    </div>
  </article>
</template>