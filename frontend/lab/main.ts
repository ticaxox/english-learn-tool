/**
 * Motion lab entry. Serves sample gamification payloads to the real components
 * and mounts them on their own page; the app bundle never imports this file.
 */
import { createApp } from 'vue'
import '../src/composables/useTheme'
import DivButton from '../src/components/DivButton.vue'
import Lab from './Lab.vue'
import { BADGES, PROGRESS, WEEKLY, bookDetail } from './data'
import { gsap } from '../src/composables/useMotion'
import '../src/style.css'
import '../src/cookie-theme.css'
import '../src/member-redesign.css'
import '../src/workspace-reset.css'
import '../src/information-architecture.css'
import '../src/personal-ui.css'
import '../src/game-ui.css'
import '../src/controls.css'
import '../src/game-shell.css'
import '../src/learning.css'
import '../src/challenge.css'

function reply(payload: unknown): Promise<Response> {
  return Promise.resolve(new Response(JSON.stringify(payload), {
    status: 200,
    headers: { 'Content-Type': 'application/json' },
  }))
}

const passthrough = window.fetch.bind(window)

window.fetch = (input: RequestInfo | URL, init?: RequestInit): Promise<Response> => {
  const url = typeof input === 'string' ? input : input instanceof URL ? input.href : input.url
  if (url.includes('/me/progress/weekly')) return reply(WEEKLY)
  if (url.includes('/me/progress/badges')) return reply(BADGES)
  if (url.includes('/me/progress')) return reply(PROGRESS)
  const book = url.match(/\/wordbooks\/([^?]+)/)
  if (book) return reply(bookDetail(decodeURIComponent(book[1])))
  return passthrough(input, init)
}

// Labs only: lets a headless check advance the timeline when the browser cuts
// requestAnimationFrame down to nothing.
;(window as unknown as { __motion: typeof gsap }).__motion = gsap

const app = createApp(Lab)
app.component('DivButton', DivButton)
app.mount('#lab')
