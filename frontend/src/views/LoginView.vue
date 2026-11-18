<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import ErrorNotice from '../components/ErrorNotice.vue'
import appicon from '../assets/logo/appicon.webp'
import { useAuthStore } from '../stores/auth'
import { safeInternalRedirect, validateUsername } from '../lib/validation'

const auth = useAuthStore()
const route = useRoute()
const router = useRouter()

const username = ref('')
const password = ref('')
const submitting = ref(false)
const mode = ref<'login' | 'register'>('login')
const passwordConfirm = ref('')
const error = ref<unknown>(null)
const statusNote = ref('')

onMounted(() => {
  if (route.query.reason === 'password-changed') {
    statusNote.value = '密码已更新，但自动重新登录未完成。请使用新密码手动登录。'
  }
  if (auth.lastError) {
    error.value = auth.lastError
  }
})

async function submit(): Promise<void> {
  error.value = null
  statusNote.value = ''

  const usernameError = validateUsername(username.value.trim())
  if (usernameError) {
    error.value = new Error(usernameError)
    return
  }
  if (!password.value) {
    error.value = new Error('请输入密码。')
    return
  }

  submitting.value = true
  try {
    const user = await auth.login({
      username: username.value.trim(),
      password: password.value,
    })

    if (user.must_change_password) {
      await router.replace({ name: 'change-password' })
      return
    }

    const redirect = safeInternalRedirect(route.query.redirect)
    await router.replace(redirect ?? { name: 'overview' })
  } catch (loginError) {
    error.value = loginError
  } finally {
    submitting.value = false
  }
}

async function register(): Promise<void> {
  error.value = null
  statusNote.value = ''
  const usernameError = validateUsername(username.value.trim())
  if (usernameError) {
    error.value = new Error(usernameError)
    return
  }
  if (password.value !== passwordConfirm.value) {
    error.value = new Error('两次输入的密码不一致。')
    return
  }
  submitting.value = true
  try {
    await auth.register({ username: username.value.trim(), password: password.value })
    await router.replace({ name: 'overview' })
  } catch (registerError) {
    error.value = registerError
  } finally {
    submitting.value = false
  }
}

async function retryConnection(): Promise<void> {
  error.value = null
  statusNote.value = ''
  await auth.retryInitialization()

  if (auth.lastError) {
    error.value = auth.lastError
  } else {
    statusNote.value = '学习服务已可连接，请继续登录。'
  }
}
</script>

<template>
  <main class="auth-page">
    <!-- Hob stands beside the door, not on top of the form. -->
    <aside class="auth-art" aria-hidden="true">
      <img class="auth-art__mark" :src="appicon" alt="" />
    </aside>

    <section class="auth-card" aria-labelledby="login-title">
      <div class="auth-card__masthead">
        <span class="auth-card__seal">GRIMOIRE</span>
        <h1 id="login-title" class="auth-card__title">
          {{ mode === 'login' ? '登录学习空间' : '创建学习账号' }}
        </h1>
      </div>

      <div v-if="route.query.reason === 'session-expired'" class="alert alert-warning" role="status">
        登录状态已失效，请重新登录。
      </div>

      <div v-if="route.query.reason === 'password-changed'" class="alert alert-warning" role="status">
        密码已修改。请使用新密码重新登录。
      </div>

      <div v-if="statusNote" class="alert alert-success" role="status">
        {{ statusNote }}
      </div>

      <ErrorNotice
        v-if="error"
        :error="error"
        retry-label="重新检查连接"
        @retry="retryConnection"
      />

      <form class="form-stack" @submit.prevent="mode === 'login' ? submit() : register()">
        <div class="field">
          <label for="username">用户名</label>
          <input
            id="username"
            v-model="username"
            name="username"
            type="text"
            autocomplete="username"
            minlength="3"
            maxlength="32"
            required
            :disabled="submitting"
          />
        </div>

        <div class="field">
          <label for="password">密码</label>
          <input
            id="password"
            v-model="password"
            name="password"
            type="password"
            :autocomplete="mode === 'login' ? 'current-password' : 'new-password'"
            required
            :disabled="submitting"
          />
        </div>

        <div v-if="mode === 'register'" class="field">
          <label for="password-confirm">再次输入密码</label>
          <input
            id="password-confirm"
            v-model="passwordConfirm"
            name="password-confirm"
            type="password"
            autocomplete="new-password"
            required
            :disabled="submitting"
          />
        </div>

        <DivButton type="submit" :disabled="submitting">
          {{ submitting ? '请稍候…' : mode === 'login' ? '登录' : '注册并进入' }}
        </DivButton>
      </form>

      <p class="auth-switch">
        {{ mode === 'login' ? '还没有账号？' : '已经有账号？' }}
        <DivButton
          type="button"
          class="auth-switch__link"
          @click="mode = mode === 'login' ? 'register' : 'login'; passwordConfirm = ''"
        >
          {{ mode === 'login' ? '注册一个' : '去登录' }}
        </DivButton>
      </p>

    </section>
  </main>
</template>
