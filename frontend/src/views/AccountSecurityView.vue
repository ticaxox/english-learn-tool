<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import ErrorNotice from '../components/ErrorNotice.vue'
import LoadingState from '../components/LoadingState.vue'
import { ValidationError } from '../api/errors'
import {
  createPersonalToken,
  listPersonalTokens,
  revokePersonalToken,
  type PersonalToken,
  type PersonalTokenCreated,
} from '../api/tokens'
import { validateStrongPassword, validateUsername } from '../lib/validation'
import { PasswordChangedLoginRequiredError, useAuthStore } from '../stores/auth'

const auth = useAuthStore()
const router = useRouter()
const oldPassword = ref('')
const newPassword = ref('')
const confirmPassword = ref('')
const submitting = ref(false)
const error = ref<unknown>(null)
const saved = ref(false)

const username = ref(auth.user?.username ?? '')
const usernameSubmitting = ref(false)
const usernameError = ref<unknown>(null)
const usernameSaved = ref(false)

const tokens = ref<PersonalToken[]>([])
const tokensLoading = ref(false)
const tokenError = ref<unknown>(null)
const tokenName = ref('')
const tokenCreating = ref(false)
const newToken = ref<PersonalTokenCreated | null>(null)
const copyNotice = ref('')
const revokingId = ref('')

function formatTokenDate(value: string | null): string {
  if (!value) return '—'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return new Intl.DateTimeFormat('zh-CN', { dateStyle: 'medium' }).format(date)
}

async function loadTokens(): Promise<void> {
  tokensLoading.value = true
  tokenError.value = null
  try {
    tokens.value = await listPersonalTokens()
  } catch (loadError) {
    tokenError.value = loadError
  } finally {
    tokensLoading.value = false
  }
}

async function submitToken(): Promise<void> {
  const name = tokenName.value.trim()
  if (!name || tokenCreating.value) return
  tokenCreating.value = true
  tokenError.value = null
  copyNotice.value = ''
  try {
    newToken.value = await createPersonalToken(name)
    tokenName.value = ''
    await loadTokens()
  } catch (createError) {
    tokenError.value = createError
  } finally {
    tokenCreating.value = false
  }
}

async function revokeToken(token: PersonalToken): Promise<void> {
  if (revokingId.value) return
  revokingId.value = token.id
  tokenError.value = null
  try {
    await revokePersonalToken(token.id)
    if (newToken.value?.id === token.id) newToken.value = null
    await loadTokens()
  } catch (revokeError) {
    tokenError.value = revokeError
  } finally {
    revokingId.value = ''
  }
}

async function copyToken(): Promise<void> {
  if (!newToken.value) return
  try {
    await navigator.clipboard.writeText(newToken.value.token)
    copyNotice.value = '已复制'
  } catch {
    copyNotice.value = '请手动选中复制'
  }
}

onMounted(() => {
  void loadTokens()
})

async function submitUsername(): Promise<void> {
  usernameError.value = null
  usernameSaved.value = false
  const name = username.value.trim()
  const nameError = validateUsername(name)
  if (nameError) {
    usernameError.value = new ValidationError(nameError)
    return
  }
  usernameSubmitting.value = true
  try {
    await auth.changeUsername({ username: name })
    usernameSaved.value = true
  } catch (changeError) {
    usernameError.value = changeError
  } finally {
    usernameSubmitting.value = false
  }
}

async function submit(): Promise<void> {
  error.value = null
  saved.value = false

  if (!oldPassword.value) {
    error.value = new ValidationError('请输入当前密码。')
    return
  }

  const passwordError = validateStrongPassword(newPassword.value)
  if (passwordError) {
    error.value = new ValidationError(passwordError)
    return
  }

  if (newPassword.value !== confirmPassword.value) {
    error.value = new ValidationError('两次输入的新密码不一致。')
    return
  }

  if (oldPassword.value === newPassword.value) {
    error.value = new ValidationError('新密码不能与当前密码相同。')
    return
  }

  submitting.value = true
  try {
    await auth.changePassword({
      old_password: oldPassword.value,
      new_password: newPassword.value,
    })
    oldPassword.value = ''
    newPassword.value = ''
    confirmPassword.value = ''
    saved.value = true
  } catch (changeError) {
    if (changeError instanceof PasswordChangedLoginRequiredError) {
      await router.replace({ name: 'login', query: { reason: 'password-changed' } })
      return
    }
    error.value = changeError
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <section class="panel ia-account-security" aria-labelledby="account-username-title">
    <div class="ia-subsection-header">
      <div>
        <p class="eyebrow">我的账户</p>
        <h2 id="account-username-title">登录用户名</h2>
        <p>修改后请用新用户名登录；学习记录和显示名称不变。</p>
      </div>
    </div>

    <p v-if="usernameSaved" class="alert alert-success" role="status">用户名已更新。</p>
    <ErrorNotice v-if="usernameError" :error="usernameError" :show-retry="false" />

    <form class="form-stack ia-security-form" @submit.prevent="submitUsername">
      <div class="field">
        <label for="settings-username">新用户名</label>
        <input
          id="settings-username"
          v-model="username"
          type="text"
          autocomplete="username"
          minlength="3"
          maxlength="32"
          required
          :disabled="usernameSubmitting"
        />
        <p class="field-hint">3–32 位英文字母、数字或下划线。</p>
      </div>
      <div class="button-row">
        <DivButton type="submit" :disabled="usernameSubmitting">{{ usernameSubmitting ? '正在更新…' : '保存用户名' }}</DivButton>
      </div>
    </form>
  </section>

  <section class="panel ia-account-security" aria-labelledby="account-security-title">
    <div class="ia-subsection-header">
      <div>
        <p class="eyebrow">账户安全</p>
        <h2 id="account-security-title">修改登录密码</h2>
        <p>保存后旧会话会失效，系统会使用新密码重新建立本人会话。</p>
      </div>
    </div>

    <p v-if="saved" class="alert alert-success" role="status">密码已更新，当前会话已重新登录。</p>
    <ErrorNotice v-if="error" :error="error" :show-retry="false" />

    <form class="form-stack ia-security-form" @submit.prevent="submit">
      <div class="field">
        <label for="settings-old-password">当前密码</label>
        <input
          id="settings-old-password"
          v-model="oldPassword"
          type="password"
          autocomplete="current-password"
          required
          :disabled="submitting"
        />
      </div>
      <div class="field">
        <label for="settings-new-password">新密码</label>
        <input
          id="settings-new-password"
          v-model="newPassword"
          type="password"
          autocomplete="new-password"
          minlength="12"
          maxlength="128"
          required
          :disabled="submitting"
        />
        <p class="field-hint">12–128 位，需包含大写字母、小写字母、数字和特殊字符中的至少三类。</p>
      </div>
      <div class="field">
        <label for="settings-confirm-password">再次输入新密码</label>
        <input
          id="settings-confirm-password"
          v-model="confirmPassword"
          type="password"
          autocomplete="new-password"
          minlength="12"
          maxlength="128"
          required
          :disabled="submitting"
        />
      </div>
      <div class="button-row">
        <DivButton type="submit" :disabled="submitting">{{ submitting ? '正在更新…' : '保存新密码' }}</DivButton>
      </div>
    </form>
  </section>

  <section class="panel ia-account-security" aria-labelledby="account-tokens-title">
    <header>
      <p class="eyebrow">MCP</p>
      <h2 id="account-tokens-title">访问令牌</h2>
      <p class="field-hint">外部 MCP 客户端用这里的令牌调用教练动作；令牌只在创建时显示一次。</p>
    </header>

    <form class="form-stack ia-security-form" @submit.prevent="submitToken">
      <div class="field">
        <label for="mcp-token-name">令牌名称</label>
        <input
          id="mcp-token-name"
          v-model="tokenName"
          maxlength="80"
          placeholder="例如 Claude Desktop"
          :disabled="tokenCreating"
        />
      </div>
      <div class="button-row">
        <DivButton type="submit" :disabled="tokenCreating || !tokenName.trim()">
          {{ tokenCreating ? '正在生成…' : '生成令牌' }}
        </DivButton>
      </div>
    </form>

    <ErrorNotice v-if="tokenError" :error="tokenError" :show-retry="false" />

    <div v-if="newToken" class="mcp-token-reveal">
      <p class="field-hint">只显示这一次，请立即复制。</p>
      <code>{{ newToken.token }}</code>
      <DivButton class="button-secondary button-small" type="button" @click="copyToken">复制</DivButton>
      <span v-if="copyNotice" class="field-hint">{{ copyNotice }}</span>
    </div>

    <LoadingState v-if="tokensLoading && tokens.length === 0" label="正在读取令牌…" />
    <ul v-else-if="tokens.length" class="mcp-token-list">
      <li v-for="token in tokens" :key="token.id">
        <div>
          <strong>{{ token.name }}</strong>
          <small>
            {{ token.prefix }}…
            · 创建于 {{ formatTokenDate(token.createdAt) }}
            <template v-if="token.lastUsedAt"> · 最近使用 {{ formatTokenDate(token.lastUsedAt) }}</template>
          </small>
        </div>
        <DivButton
          v-if="!token.revokedAt"
          class="button-secondary button-small"
          type="button"
          :disabled="revokingId === token.id"
          @click="revokeToken(token)"
        >{{ revokingId === token.id ? '正在撤销…' : '撤销' }}</DivButton>
        <span v-else class="field-hint">已撤销</span>
      </li>
    </ul>
    <p v-else-if="!tokensLoading" class="field-hint">还没有访问令牌。</p>
  </section>
</template>