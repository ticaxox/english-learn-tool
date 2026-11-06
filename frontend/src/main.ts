import { createPinia } from 'pinia'
import { createApp } from 'vue'
import App from './App.vue'
import DivButton from './components/DivButton.vue'
import { apiClient } from './api/client'
import { createAppRouter } from './router'
import { markSurface, redirectForViewport, watchOrientation } from './lib/surface'
import { useAuthStore } from './stores/auth'
import './style.css'
import './cookie-theme.css'
import './member-redesign.css'
import './workspace-reset.css'
import './information-architecture.css'
import './personal-ui.css'
import './game-ui.css'
import './controls.css'

// Swap surfaces before the router is built, so its history base is right.
redirectForViewport()
markSurface()
watchOrientation()

const app = createApp(App)
const pinia = createPinia()

app.component('DivButton', DivButton)
app.use(pinia)

const auth = useAuthStore(pinia)
const router = createAppRouter(pinia)

apiClient.setRefreshHandler(async () => {
  await auth.refreshAccessToken()
})

apiClient.setSessionExpiredHandler(() => {
  auth.markSessionExpired()
  const current = router.currentRoute.value
  if (!current.meta.public && current.name !== 'login') {
    void router.replace({
      name: 'login',
      query: { redirect: current.fullPath, reason: 'session-expired' },
    })
  }
})

app.use(router)
void router.isReady().then(() => app.mount('#app'))
