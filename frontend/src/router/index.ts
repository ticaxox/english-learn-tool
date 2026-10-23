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
import ChangePasswordView from '../views/ChangePasswordView.vue'
import LoginView from '../views/LoginView.vue'
import NotFoundView from '../views/NotFoundView.vue'
import LearningSettingsView from '../views/LearningSettingsView.vue'
import MemoryPracticeView from '../views/MemoryPracticeView.vue'
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
        component: RemoteDataPage,
        props: {
          title: 'AI 练习',
          description: '真实读取练习记录；生成、作答和评分界面将在后续任务实现。',
          endpoint: '/practice/records',
        },
      },
      {
        path: 'practice/:sessionId',
        name: 'practice-session',
        component: RemoteDataPage,
        props: (route) => ({
          title: '练习会话',
          description: '按会话 ID 读取真实练习数据；本任务不渲染业务题目。',
          endpoint: `/practice/sessions/${encodeURIComponent(String(route.params.sessionId))}`,
        }),
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
        component: RemoteDataPage,
        props: {
          title: '通知',
          description: '真实读取当前成员的通知；通知操作将在后续任务实现。',
          endpoint: '/notifications',
        },
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
        component: RemoteDataPage,
        meta: { requiresRole: 'admin' },
        props: {
          title: 'AI 提供商',
          description: '真实读取已配置的提供商；编辑和连接测试将在后续任务实现。',
          endpoint: '/admin/ai/providers',
        },
      },
      {
        path: 'admin/ai/prompts',
        name: 'admin-prompts',
        component: RemoteDataPage,
        meta: { requiresRole: 'admin' },
        props: {
          title: 'AI 提示词',
          description: '真实读取提示词列表；覆盖编辑将在后续任务实现。',
          endpoint: '/admin/ai/prompts',
        },
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
