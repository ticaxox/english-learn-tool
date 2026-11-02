<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import ErrorNotice from '../components/ErrorNotice.vue'
import { ValidationError } from '../api/errors'
import { validateStrongPassword } from '../lib/validation'
import { PasswordChangedLoginRequiredError, useAuthStore } from '../stores/auth'

const auth = useAuthStore()
const router = useRouter()
const oldPassword = ref('')
const newPassword = ref('')
const confirmPassword = ref('')
const submitting = ref(false)
const error = ref<unknown>(null)
const saved = ref(false)

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