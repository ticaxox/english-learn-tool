<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { apiClient } from '../api/client'
import ErrorNotice from '../components/ErrorNotice.vue'
import { useAuthStore } from '../stores/auth'
import { safeInternalRedirect, validateUsername } from '../lib/validation'

const auth = useAuthStore()
const route = useRoute()
const router = useRouter()

const username = ref('')
const password = ref('')
const submitting = ref(false)
const error = ref<unknown>(null)
const statusNote = ref('')

onMounted(() => {
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
    <section class="auth-card" aria-labelledby="login-title">
      <p class="eyebrow">组织内部学习平台</p>
      <h1 id="login-title">登录学习空间</h1>
      <p class="lead">
        使用组织管理员分配的账号登录。首次登录或管理员重置密码后，需要先设置新密码。
      </p>

      <div v-if="route.query.reason === 'session-expired'" class="alert alert-warning" role="status">
        登录状态已失效，请重新登录。
      </div>

      <div v-if="statusNote" class="alert alert-success" role="status">
        {{ statusNote }}
      </div>

      <ErrorNotice
        v-if="error"
        :error="error"
        retry-label="重新检查连接"
        show-retry
        @retry="retryConnection"
      />

      <form class="form-stack" @submit.prevent="submit">
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
          <p class="field-hint">3–32 位英文字母、数字或下划线。</p>
        </div>

        <div class="field">
          <label for="password">密码</label>
          <input
            id="password"
            v-model="password"
            name="password"
            type="password"
            autocomplete="current-password"
            required
            :disabled="submitting"
          />
        </div>

        <button type="submit" :disabled="submitting">
          {{ submitting ? '正在验证真实账号…' : '登录' }}
        </button>
      </form>

      <p class="inline-note">
        当前 API 前缀：<code>{{ apiClient.getBaseUrl() }}</code>。页面直接请求真实后端；后端未就绪时会展示连接错误，不会切换为模拟登录。
      </p>
    </section>
  </main>
</template>