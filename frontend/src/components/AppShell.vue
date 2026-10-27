<script setup lang="ts">
import { computed } from 'vue'
import { RouterView, useRoute, useRouter } from 'vue-router'
import { useAuthStore } from '../stores/auth'
import MemberShell from './MemberShell.vue'

const auth = useAuthStore()
const route = useRoute()
const router = useRouter()

const accessDenied = computed(() => route.query.access === 'denied')

async function signOut(): Promise<void> {
  try {
    await auth.logout()
  } catch {
    // The store keeps the server error for the login screen while clearing in-memory credentials.
  }
  await router.replace({ name: 'login' })
}
</script>

<template>
  <MemberShell
    :display-name="auth.displayName"
    :username="auth.user?.username ?? ''"
    :is-admin="auth.isAdmin"
    @signout="signOut"
  >
    <div v-if="accessDenied" class="alert alert-warning" role="alert">
      当前账号没有访问组织管理页面的权限。
    </div>
    <RouterView />
  </MemberShell>
</template>