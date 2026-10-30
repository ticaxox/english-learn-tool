<script setup lang="ts">
import { RouterView, useRouter } from 'vue-router'
import { useAuthStore } from '../stores/auth'
import MemberShell from './MemberShell.vue'

const auth = useAuthStore()
const router = useRouter()

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
    @signout="signOut"
  >
    <RouterView v-slot="{ Component, route }">
      <Transition name="crumb-page" mode="out-in">
        <component :is="Component" :key="route.path" />
      </Transition>
    </RouterView>
  </MemberShell>
</template>
