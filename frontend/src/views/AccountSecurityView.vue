<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import ErrorNotice from '../components/ErrorNotice.vue'
import { ValidationError } from '../api/errors'
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
const usernamePassword = ref('')
const usernameSubmitting = ref(false)
const usernameError = ref<unknown>(null)
const usernameSaved = ref(false)

async function submitUsername(): Promise<void> {
  usernameError.value = null
  usernameSaved.value = false
  const name = username.value.trim()
  const nameError = validateUsername(name)
  if (nameError) {
    usernameError.value = new ValidationError(nameError)
    return
  }
  if (!usernamePassword.value) {
    usernameError.value = new ValidationError('请输入当前密码。')
    return
  }
  usernameSubmitting.value = true
  try {
    await auth.changeUsername({ username: name, current_password: usernamePassword.value })
    usernamePassword.value = ''
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
      <div class="field">
        <label for="settings-username-password">当前密码</label>
        <input
          id="settings-username-password"
          v-model="usernamePassword"
          type="password"
          autocomplete="current-password"
          required
          :disabled="usernameSubmitting"
        />
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
</template>