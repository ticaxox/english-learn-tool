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
import KnowledgeBaseView from '../views/KnowledgeBaseView.vue'
import AdminUsersView from '../views/AdminUsersView.vue'
import AdminDashboardView from '../views/AdminDashboardView.vue'
import AdminAiProvidersView from '../views/AdminAiProvidersView.vue'
import AdminAiPromptsView from '../views/AdminAiPromptsView.vue'
import AdminManagementView from '../views/AdminManagementView.vue'
import AdminAiPlatformView from '../views/AdminAiPlatformView.vue'
import ChangePasswordView from '../views/ChangePasswordView.vue'
import ChallengeView from '../views/ChallengeView.vue'
import LoginView from '../views/LoginView.vue'
import NotFoundView from '../views/NotFoundView.vue'
import LearningSettingsView from '../views/LearningSettingsView.vue'
import PersonalAiConfigView from '../views/PersonalAiConfigView.vue'
import PracticeHubView from '../views/PracticeHubView.vue'
import PracticeRecordsView from '../views/PracticeRecordsView.vue'
import PracticeTasksView from '../views/PracticeTasksView.vue'
import MistakesView from '../views/MistakesView.vue'
import SettingsHubView from '../views/SettingsHubView.vue'
import TodayView from '../views/TodayView.vue'
import CoachView from '../views/CoachView.vue'
import WordbooksView from '../views/WordbooksView.vue'
import { useAuthStore } from '../stores/auth'
import { surfaceBase } from '../lib/surface'

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
        redirect: '/settings/wordbooks',
      },
      {
        path: 'learning',
        redirect: { name: 'challenges' },
      },
      {
        // Memory training lives on the practice page; old links keep working.
        path: 'memory',
        name: 'memory',
        redirect: (to) => ({ name: 'practice', query: to.query }),
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
      },
      {
        path: 'practice/tasks',
        name: 'practice-tasks',
        component: PracticeTasksView,
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
        // Answering happens inside the practice page, never on a page of its own.
        redirect: (to) => ({
          name: 'practice',
          query: {
            session: String(to.params.sessionId),
            ...(typeof to.query.timer === 'string' ? { timer: to.query.timer } : {}),
          },
        }),
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
        component: CoachView,
        props: { surface: 'page' },
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
          {
            path: 'wordbooks',
            name: 'settings-wordbooks',
            component: WordbooksView,
          },
          {
            path: 'knowledge',
            name: 'settings-knowledge',
            component: KnowledgeBaseView,
          },
        ],
      },
      {
        path: 'admin',
        component: AdminManagementView,
        meta: { adminOnly: true },
        children: [
          { path: '', redirect: { name: 'admin-users' } },
          { path: 'users', name: 'admin-users', component: AdminUsersView },
          { path: 'dashboard', name: 'admin-dashboard', component: AdminDashboardView },
          {
            path: 'ai',
            component: AdminAiPlatformView,
            children: [
              { path: '', redirect: { name: 'admin-ai-providers' } },
              { path: 'providers', name: 'admin-ai-providers', component: AdminAiProvidersView },
              { path: 'prompts', name: 'admin-ai-prompts', component: AdminAiPromptsView },
            ],
          },
        ],
      },
      {
        path: 'admin/knowledge',
        name: 'admin-knowledge',
        component: KnowledgeBaseView,
        meta: { adminOnly: true },
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
    : createWebHistory(surfaceBase()),
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

    if (to.meta.adminOnly && !auth.isAdmin) {
      return { name: 'overview' }
    }

    return true
  })

  return router
}

export { routes }
