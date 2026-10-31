import type { Pinia } from 'pinia'
import {
  createMemoryHistory,
  createRouter,
  createWebHistory,
  type RouterHistory,
  type RouteRecordRaw,
} from 'vue-router'
import AppShell from '../components/AppShell.vue'
import AccountSecurityView from '../views/AccountSecurityView.vue'
import ChangePasswordView from '../views/ChangePasswordView.vue'
import ChallengeView from '../views/ChallengeView.vue'
import LoginView from '../views/LoginView.vue'
import NotFoundView from '../views/NotFoundView.vue'
import LearningSettingsView from '../views/LearningSettingsView.vue'
import MemoryPracticeView from '../views/MemoryPracticeView.vue'
import PersonalAiConfigView from '../views/PersonalAiConfigView.vue'
import PracticeHubView from '../views/PracticeHubView.vue'
import PracticeSessionView from '../views/PracticeSessionView.vue'
import PracticeRecordsView from '../views/PracticeRecordsView.vue'
import MistakesView from '../views/MistakesView.vue'
import SettingsHubView from '../views/SettingsHubView.vue'
import TodayView from '../views/TodayView.vue'
import WordbooksView from '../views/WordbooksView.vue'
import { useAuthStore } from '../stores/auth'

const routes: RouteRecordRaw[] = [
  {
    path: '/login',
    name: 'login',
    component: LoginView,
    meta: { public: true },
  },
  {
    path: '/change-password',
    name: 'change-password',
    component: ChangePasswordView,
  },
  {
    path: '/',
    component: AppShell,
    children: [
      {
        path: '',
        redirect: '/overview',
      },
      {
        path: 'overview',
        name: 'overview',
        component: TodayView,
      },
      {
        path: 'wordbooks',
        name: 'wordbooks',
        component: WordbooksView,
      },
      {
        path: 'learning',
        redirect: { name: 'challenges' },
      },
      {
        path: 'memory',
        name: 'memory',
        component: MemoryPracticeView,
        meta: { immersive: true },
      },
      {
        path: 'memory/mistakes',
        name: 'memory-mistakes',
        component: MistakesView,
        meta: { immersive: true },
      },
      {
        path: 'practice',
        name: 'practice',
        component: PracticeHubView,
        meta: { immersive: true },
      },
      {
        path: 'practice/records',
        name: 'practice-records',
        component: PracticeRecordsView,
        meta: { immersive: true },
      },
      {
        path: 'practice/mistakes',
        name: 'practice-mistakes',
        component: PracticeRecordsView,
        props: { onlyMistakes: true },
        meta: { immersive: true },
      },
      {
        path: 'practice/:sessionId',
        name: 'practice-session',
        component: PracticeSessionView,
        meta: { immersive: true },
      },
      {
        path: 'challenges',
        name: 'challenges',
        component: ChallengeView,
      },
      {
        path: 'challenges/:challengeId',
        name: 'challenge-detail',
        component: ChallengeView,
      },
      {
        path: 'coach',
        name: 'coach',
        component: TodayView,
        meta: { coachPanel: true },
      },
      {
        path: 'settings',
        component: SettingsHubView,
        children: [
          {
            path: '',
            redirect: { name: 'settings-learning' },
          },
          {
            path: 'learning',
            name: 'settings-learning',
            component: LearningSettingsView,
          },
          {
            path: 'ai',
            name: 'settings-ai',
            component: PersonalAiConfigView,
          },
          {
            path: 'security',
            name: 'settings-security',
            component: AccountSecurityView,
          },
        ],
      },
      {
        path: ':pathMatch(.*)*',
        name: 'not-found',
        component: NotFoundView,
      },
    ],
  },
]

export function createAppRouter(
  pinia: Pinia,
  history: RouterHistory = import.meta.env.MODE === 'test'
    ? createMemoryHistory()
    : createWebHistory(import.meta.env.BASE_URL),
) {
  const router = createRouter({
    history,
    routes,
    scrollBehavior: () => ({ top: 0 }),
  })

  router.beforeEach(async (to) => {
    const auth = useAuthStore(pinia)
    await auth.ensureInitialized()

    if (to.meta.public) {
      if (auth.isAuthenticated) {
        return auth.mustChangePassword
          ? { name: 'change-password' }
          : { name: 'overview' }
      }
      return true
    }

    if (!auth.isAuthenticated) {
      return {
        name: 'login',
        query: {
          redirect: to.fullPath,
          reason: auth.status === 'error' ? 'api-unreachable' : undefined,
        },
      }
    }

    if (auth.mustChangePassword) {
      return to.name === 'change-password' ? true : { name: 'change-password' }
    }

    if (to.name === 'change-password') {
      return { name: 'overview' }
    }

    return true
  })

  return router
}

export { routes }
