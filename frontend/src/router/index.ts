import type { Pinia } from 'pinia'
import {
  createMemoryHistory,
  createRouter,
  createWebHistory,
  type RouterHistory,
  type RouteRecordRaw,
} from 'vue-router'
import AppShell from '../components/AppShell.vue'
import AdminUsersView from '../views/AdminUsersView.vue'
import AdminAiProvidersView from '../views/AdminAiProvidersView.vue'
import AdminAiPromptsView from '../views/AdminAiPromptsView.vue'
import AdminAiUsageView from '../views/AdminAiUsageView.vue'
import ChangePasswordView from '../views/ChangePasswordView.vue'
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
import RemoteDataPage from '../views/RemoteDataPage.vue'
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
        component: RemoteDataPage,
        props: {
          title: '每日闯关',
          description: '真实读取今日闯关地图。若后端尚未生成地图，页面会显示真实 404 响应。',
          endpoint: '/challenges/today',
        },
      },
      {
        path: 'challenges/:challengeId',
        name: 'challenge-detail',
        component: RemoteDataPage,
        props: (route) => ({
          title: '闯关详情',
          description: '按挑战 ID 读取真实地图数据；关卡交互将在后续任务实现。',
          endpoint: `/challenges/${encodeURIComponent(String(route.params.challengeId))}`,
        }),
      },
      {
        path: 'coach',
        name: 'coach',
        component: RemoteDataPage,
        props: {
          title: 'AI 教练',
          description: '真实读取教练会话列表；流式对话界面将在后续任务实现。',
          endpoint: '/coach/conversations',
        },
      },
      {
        path: 'notifications',
        name: 'notifications',
        component: NotificationsView,
      },
      {
        path: 'notifications/preferences',
        name: 'notification-preferences',
        component: NotificationPreferencesView,
      },
      {
        path: 'settings',
        name: 'settings',
        component: LearningSettingsView,
      },
      {
        path: 'admin/dashboard',
        name: 'admin-dashboard',
        component: RemoteDataPage,
        meta: { requiresRole: 'admin' },
        props: {
          title: '组织看板',
          description: '真实读取组织聚合数据；图表和指标界面将在后续任务实现。',
          endpoint: '/admin/dashboard',
        },
      },
      {
        path: 'admin/users',
        name: 'admin-users',
        component: AdminUsersView,
        meta: { requiresRole: 'admin' },
      },
      {
        path: 'admin/ai/providers',
        name: 'admin-providers',
        component: AdminAiProvidersView,
        meta: { requiresRole: 'admin' },
      },
      {
        path: 'admin/ai/prompts',
        name: 'admin-prompts',
        component: AdminAiPromptsView,
        meta: { requiresRole: 'admin' },
      },
      {
        path: 'admin/ai/usage',
        name: 'admin-ai-usage',
        component: AdminAiUsageView,
        meta: { requiresRole: 'admin' },
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
