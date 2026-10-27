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
import AdminAiPlatformView from '../views/AdminAiPlatformView.vue'
import AdminManagementView from '../views/AdminManagementView.vue'
import AdminUsersView from '../views/AdminUsersView.vue'
import AdminAiProvidersView from '../views/AdminAiProvidersView.vue'
import AdminAiPromptsView from '../views/AdminAiPromptsView.vue'
import AdminAiUsageView from '../views/AdminAiUsageView.vue'
import AdminDashboardView from '../views/AdminDashboardView.vue'
import ChangePasswordView from '../views/ChangePasswordView.vue'
import ChallengeView from '../views/ChallengeView.vue'
import LoginView from '../views/LoginView.vue'
import NotFoundView from '../views/NotFoundView.vue'
import LearningSettingsView from '../views/LearningSettingsView.vue'
import MemoryPracticeView from '../views/MemoryPracticeView.vue'
import NotificationsView from '../views/NotificationsView.vue'
import NotificationPreferencesView from '../views/NotificationPreferencesView.vue'
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
      },
      {
        path: 'memory/mistakes',
        name: 'memory-mistakes',
        component: MistakesView,
      },
      {
        path: 'practice',
        name: 'practice',
        component: PracticeHubView,
      },
      {
        path: 'practice/records',
        name: 'practice-records',
        component: PracticeRecordsView,
      },
      {
        path: 'practice/mistakes',
        name: 'practice-mistakes',
        component: PracticeRecordsView,
        props: { onlyMistakes: true },
      },
      {
        path: 'practice/:sessionId',
        name: 'practice-session',
        component: PracticeSessionView,
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
        path: 'notifications',
        name: 'notifications',
        component: NotificationsView,
      },
      {
        path: 'notifications/preferences',
        name: 'notification-preferences',
        redirect: { name: 'settings-notifications' },
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
            path: 'notifications',
            name: 'settings-notifications',
            component: NotificationPreferencesView,
          },
          {
            path: 'security',
            name: 'settings-security',
            component: AccountSecurityView,
          },
        ],
      },
      {
        path: 'admin',
        component: AdminManagementView,
        meta: { requiresRole: 'admin' },
        children: [
          {
            path: '',
            redirect: { name: 'admin-users' },
          },
          {
            path: 'users',
            name: 'admin-users',
            component: AdminUsersView,
          },
          {
            path: 'dashboard',
            name: 'admin-dashboard',
            component: AdminDashboardView,
          },
          {
            path: 'ai',
            component: AdminAiPlatformView,
            children: [
              {
                path: '',
                redirect: { name: 'admin-providers' },
              },
              {
                path: 'providers',
                name: 'admin-providers',
                component: AdminAiProvidersView,
              },
              {
                path: 'prompts',
                name: 'admin-prompts',
                component: AdminAiPromptsView,
              },
              {
                path: 'usage',
                name: 'admin-ai-usage',
                component: AdminAiUsageView,
              },
            ],
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

    if (to.meta.requiresRole && auth.user?.role !== to.meta.requiresRole) {
      return {
        name: 'overview',
        query: { access: 'denied' },
      }
    }

    return true
  })

  return router
}

export { routes }