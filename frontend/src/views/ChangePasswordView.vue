<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import ErrorNotice from '../components/ErrorNotice.vue'
import ArtImage from '../components/ArtImage.vue'
import { illustration } from '../assets/halloween'
import { validateStrongPassword } from '../lib/validation'
import { PasswordChangedLoginRequiredError, useAuthStore } from '../stores/auth'

const auth = useAuthStore()
const router = useRouter()

const oldPassword = ref('')
const newPassword = ref('')
const confirmPassword = ref('')
const submitting = ref(false)
const error = ref<unknown>(null)

async function submit(): Promise<void> {
  error.value = null

  if (!oldPassword.value) {
    error.value = new Error('请输入当前密码。')
    return
  }

  const passwordError = validateStrongPassword(newPassword.value)
  if (passwordError) {
    error.value = new Error(passwordError)
    return
  }

  if (newPassword.value !== confirmPassword.value) {
    error.value = new Error('两次输入的新密码不一致。')
    return
  }

  if (oldPassword.value === newPassword.value) {
    error.value = new Error('新密码不能与当前密码相同。')
    return
  }

  submitting.value = true
  try {
    await auth.changePassword({
      old_password: oldPassword.value,
      new_password: newPassword.value,
    })
    await router.replace({ name: 'overview' })
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

async function signOut(): Promise<void> {
  try {
    await auth.logout()
  } catch {
    // The store exposes the real logout error on the login screen.
  }
  await router.replace({ name: 'login' })
}
</script>

<template>
  <main class="auth-page">
    <section class="auth-card auth-card--wide" aria-labelledby="change-password-title">
      <div class="auth-card__masthead">
        <ArtImage class="auth-card__mark" :set="illustration.empty" />
        <span class="auth-card__seal">GRIMOIRE</span>
      </div>
      <p class="eyebrow">首次登录或密码已重置</p>
      <h1 id="change-password-title">设置新密码</h1>
      <p class="lead">
        当前账号为 <strong>{{ auth.displayName }}</strong>。完成改密前，只能访问本页、本人基本信息和退出登录。
      </p>

      <ErrorNotice v-if="error" :error="error" />

      <form class="form-stack" @submit.prevent="submit">
        <div class="field">
          <label for="old-password">当前密码</label>
          <input
            id="old-password"
            v-model="oldPassword"
            type="password"
            autocomplete="current-password"
            required
            :disabled="submitting"
          />
        </div>

        <div class="field">
          <label for="new-password">新密码</label>
          <input
            id="new-password"
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
          <label for="confirm-password">再次输入新密码</label>
          <input
            id="confirm-password"
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
          <DivButton type="submit" :disabled="submitting">
            {{ submitting ? '正在更新真实账号…' : '保存新密码' }}
          </DivButton>
          <DivButton class="button-secondary" type="button" :disabled="submitting" @click="signOut">
            退出登录
          </DivButton>
        </div>
      </form>
    </section>
  </main>
</template>