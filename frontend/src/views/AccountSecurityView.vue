<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import ErrorNotice from '../components/ErrorNotice.vue'
import LoadingState from '../components/LoadingState.vue'
import UserAvatar from '../components/UserAvatar.vue'
import { AVATAR_KEYS, type AvatarKey } from '../api/contracts'
import { ValidationError } from '../api/errors'
import {
  createPersonalToken,
  listPersonalTokens,
  refreshPersonalToken,
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
const usernameError = ref<unknown>(null)
const usernameSaved = ref(false)
const avatar = ref<AvatarKey>(auth.user?.avatar ?? 'pumpkin')
const avatarError = ref<unknown>(null)
const avatarSaved = ref(false)
const avatarSaving = ref(false)
const avatarLocalOnly = ref(false)

async function chooseAvatar(next: AvatarKey): Promise<void> {
  if (avatarSaving.value || next === avatar.value) return
  avatarSaving.value = true
  avatarError.value = null
  avatarSaved.value = false
  avatarLocalOnly.value = false
  try {
    const persisted = await auth.changeAvatar(next)
    avatar.value = auth.user?.avatar ?? next
    avatarSaved.value = persisted
    avatarLocalOnly.value = !persisted
  } catch (error) {
    avatarError.value = error
  } finally {
    avatarSaving.value = false
  }
}

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

async function refreshToken(token: PersonalToken): Promise<void> {
  if (revokingId.value) return
  revokingId.value = token.id
  tokenError.value = null
  copyNotice.value = ''
  try {
    const refreshed = await refreshPersonalToken(token.id)
    await loadTokens()
    // The default token backs the web coach: it applies in place, nothing to copy.
    if (token.isDefault) {
      newToken.value = null
      copyNotice.value = '默认令牌已重置，网页会自动使用新令牌。'
    } else {
      newToken.value = refreshed
    }
  } catch (refreshError) {
    tokenError.value = refreshError
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

async function saveAll(): Promise<void> {
  error.value = null
  saved.value = false
  usernameError.value = null
  usernameSaved.value = false

  const name = username.value.trim()
  const nameChanged = name !== (auth.user?.username ?? '')
  const wantsPassword = Boolean(oldPassword.value || newPassword.value || confirmPassword.value)

  if (!nameChanged && !wantsPassword) {
    error.value = new ValidationError('没有需要保存的修改。')
    return
  }

  if (nameChanged) {
    const nameError = validateUsername(name)
    if (nameError) {
      usernameError.value = new ValidationError(nameError)
      return
    }
  }

  if (wantsPassword) {
    if (!oldPassword.value) {
      error.value = new ValidationError('修改密码需要先填写当前密码。')
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
  }

  submitting.value = true
  try {
    if (nameChanged) {
      await auth.changeUsername({ username: name })
      usernameSaved.value = true
    }
    if (wantsPassword) {
      await auth.changePassword({
        old_password: oldPassword.value,
        new_password: newPassword.value,
      })
      oldPassword.value = ''
      newPassword.value = ''
      confirmPassword.value = ''
      saved.value = true
    }
  } catch (saveError) {
    if (saveError instanceof PasswordChangedLoginRequiredError) {
      await router.replace({ name: 'login', query: { reason: 'password-changed' } })
      return
    }
    if (nameChanged && !usernameSaved.value) usernameError.value = saveError
    else error.value = saveError
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <section class="panel ia-account-security" aria-labelledby="account-security-title">
  <div class="ia-security-block ia-security-block--first" aria-labelledby="account-username-title">
    <header class="ia-subsection-header">
      <div>
        <p class="eyebrow">我的账户</p>
        <h2 id="account-username-title">用户信息</h2>
      </div>
    </header>

    <p v-if="usernameSaved" class="alert alert-success" role="status">用户名已更新。</p>
    <p v-if="avatarSaved" class="alert alert-success" role="status">头像已更新。</p>
    <p v-if="avatarLocalOnly" class="field-hint" role="status">当前本地后端还没有头像保存接口，选择只在本次预览生效。</p>
    <p v-if="saved" class="alert alert-success" role="status">密码已更新，当前会话已重新登录。</p>
    <ErrorNotice v-if="error" :error="error" :show-retry="false" />
    <ErrorNotice v-if="usernameError" :error="usernameError" :show-retry="false" />
    <ErrorNotice v-if="avatarError" :error="avatarError" :show-retry="false" />

    <div class="ia-security-block ia-avatar-block" aria-labelledby="account-avatar-title">
      <header>
        <p class="eyebrow">像素头像</p>
        <h2 id="account-avatar-title">选一个 Hob 世界里的自己</h2>
        <p class="field-hint">选中即保存到账号，主界面、练习页和个人资料菜单会一起换。</p>
      </header>
      <div class="ia-avatar-current">
        <UserAvatar :avatar="avatar" size="large" :label="`当前头像：${avatar}`" />
        <div>
          <strong>当前头像</strong>
          <span>16×16 像素，昼夜同图，随界面配色换底。</span>
        </div>
      </div>
      <div class="ia-avatar-grid" role="group" aria-label="头像选择">
        <button
          v-for="option in AVATAR_KEYS"
          :key="option"
          type="button"
          class="ia-avatar-choice"
          :class="{ 'is-selected': option === avatar }"
          :disabled="avatarSaving"
          :aria-pressed="option === avatar"
          :aria-label="`使用${option}头像`"
          @click="chooseAvatar(option)"
        >
          <UserAvatar :avatar="option" :label="option" />
        </button>
      </div>
    </div>

    <form class="ia-kv-form" @submit.prevent="saveAll">
      <div class="ia-kv-row">
        <label for="settings-username">用户名</label>
        <input
          id="settings-username"
          v-model="username"
          type="text"
          autocomplete="username"
          minlength="3"
          maxlength="32"
          :disabled="submitting"
        />
      </div>
      <div class="ia-kv-row">
        <label for="settings-old-password">当前密码</label>
        <input
          id="settings-old-password"
          v-model="oldPassword"
          type="password"
          autocomplete="current-password"
          :disabled="submitting"
        />
      </div>
      <div class="ia-kv-row">
        <label for="settings-new-password">新密码</label>
        <input
          id="settings-new-password"
          v-model="newPassword"
          type="password"
          autocomplete="new-password"
          minlength="12"
          maxlength="128"
          :disabled="submitting"
        />
      </div>
      <div class="ia-kv-row">
        <label for="settings-confirm-password">再次输入新密码</label>
        <input
          id="settings-confirm-password"
          v-model="confirmPassword"
          type="password"
          autocomplete="new-password"
          minlength="12"
          maxlength="128"
          :disabled="submitting"
        />
      </div>
      <div class="button-row">
        <DivButton type="submit" :disabled="submitting">{{ submitting ? '正在保存…' : '保存' }}</DivButton>
      </div>
    </form>
  </div>

    <div class="ia-security-block" aria-labelledby="account-tokens-title">
    <header>
      <p class="eyebrow">MCP</p>
      <h2 id="account-tokens-title">访问令牌</h2>
      <p class="field-hint">外部 MCP 客户端用这里的令牌调用教练动作；令牌只在创建时显示一次。</p>
    </header>

    <form class="ia-token-form" @submit.prevent="submitToken">
      <label class="visually-hidden" for="mcp-token-name">令牌名称</label>
      <input
        id="mcp-token-name"
        v-model="tokenName"
        maxlength="80"
        placeholder="例如 Claude Desktop"
        :disabled="tokenCreating"
      />
      <DivButton type="submit" :disabled="tokenCreating || !tokenName.trim()">
        {{ tokenCreating ? '正在生成…' : '生成令牌' }}
      </DivButton>
    </form>

    <ErrorNotice v-if="tokenError" :error="tokenError" :show-retry="false" />

    <div v-if="newToken" class="mcp-token-reveal">
      <p class="field-hint">只显示这一次，请立即复制。</p>
      <div class="mcp-token-reveal__row">
        <code>{{ newToken.token }}</code>
        <DivButton class="button-secondary button-small" type="button" @click="copyToken">复制</DivButton>
      </div>
    </div>
    <p v-if="copyNotice" class="field-hint">{{ copyNotice }}</p>

    <LoadingState v-if="tokensLoading && tokens.length === 0" label="正在读取令牌…" />
    <ul v-else-if="tokens.length" class="mcp-token-list">
      <li v-for="token in tokens" :key="token.id">
        <div class="mcp-token-main">
          <strong>
            {{ token.name }}
            <span v-if="token.isDefault" class="mcp-token-default">默认</span>
          </strong>
          <small>
            {{ token.prefix }}…
            · 创建于 {{ formatTokenDate(token.createdAt) }}
          </small>
        </div>
        <div class="mcp-token-actions">
          <DivButton
            class="button-secondary button-small"
            type="button"
            :disabled="revokingId === token.id"
            @click="refreshToken(token)"
          >{{ revokingId === token.id ? '正在重置…' : '重置' }}</DivButton>
          <DivButton
            v-if="!token.isDefault"
            class="button-danger button-small"
            type="button"
            :disabled="revokingId === token.id"
            @click="revokeToken(token)"
          >删除</DivButton>
        </div>
      </li>
    </ul>
    <p v-else-if="!tokensLoading" class="field-hint">还没有访问令牌。</p>
  </div>
  </section>

</template>


<style scoped>
.ia-avatar-block { margin-bottom: 24px; padding-bottom: 22px; border-bottom: 1px dashed var(--ui-line); }
.ia-avatar-current { display: flex; align-items: center; gap: 14px; margin: 12px 0 16px; }
.ia-avatar-current strong { display: block; font-size: 14px; }
.ia-avatar-current span { display: block; margin-top: 2px; color: var(--ui-muted); font-size: 12px; }
.ia-avatar-grid { display: flex; flex-wrap: wrap; gap: 10px; }
.ia-avatar-choice {
  display: grid;
  width: 56px;
  height: 56px;
  place-items: center;
  padding: 0;
  border: 2px solid var(--ui-line);
  border-radius: 50%;
  background: var(--ui-surface);
  cursor: pointer;
  transition: transform 120ms ease, border-color 120ms ease, box-shadow 120ms ease;
}
.ia-avatar-choice:hover:not(:disabled) { transform: translateY(-2px); border-color: var(--g-orange-edge); }
.ia-avatar-choice.is-selected { border-color: var(--ui-ink); box-shadow: 0 0 0 3px var(--g-gold); }
.ia-avatar-choice:focus-visible { outline: 3px solid var(--g-orange); outline-offset: 2px; }
.ia-avatar-choice:disabled { cursor: wait; opacity: 0.7; }
.ia-avatar-choice .user-avatar { width: 46px; height: 46px; }
</style>
