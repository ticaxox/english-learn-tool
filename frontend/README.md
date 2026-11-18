# 前端

Grimoire 的个人学习版前端：Vue 3 + TypeScript + Vite，万圣节昼夜双态，所有业务状态以服务端为唯一真相。

## 技术栈

- Vue 3.5 / TypeScript 6 / Vite 8 / Pinia 4 / vue-router 5
- vitest 5 + jsdom + @vue/test-utils
- 少量依赖：`reka-ui`（Toaster）、`motion-v`（SvgPlateButton）、`gsap`（useMotion）、`@lucide/vue`（Toaster）
- 无 Tailwind、无 UI 组件库；样式是手写 CSS

## 页面与路由

| 路径 | 页面 |
|---|---|
| `/login`、`/change-password` | 登录、强制改密 |
| `/overview` | 今日学习：任务环、今日任务、推荐词书、内嵌闯关、周报、徽章墙 |
| `/practice` | 练习入口：记忆三模块 + 六种 AI 练习，`?session=` 同页作答 |
| `/practice/records`、`/practice/records/:recordId`、`/practice/mistakes`、`/practice/tasks` | 记录、详情、错题、任务集 |
| `/challenges`、`/challenges/:challengeId` | 每日闯关地图与详情 |
| `/coach` | Hob：对话、SSE、附件、动作回执 |
| `/settings` → `learning` / `ai` / `security` / `wordbooks` / `knowledge` | 设置 |
| `/admin/**` | 管理端（个人版导航不暴露） |
| `/_mascot` | 素材/角色预览 |

主导航只有四项：今日学习、练习、Hob、设置。二级页签在顶栏。

## 分层

| 层 | 位置 |
|---|---|
| 入口 | `src/main.ts`：先定 surface（`/m` 手机树），预涂主题，再加载全局样式 |
| 外壳 | `src/components/MemberShell.vue`：侧栏 rail、顶栏页签、手机底部导航、教练抽屉 |
| API | `src/api/client.ts`：Bearer + CSRF、401 单次刷新、错误规整 |
| 契约 | `src/api/contract-adapter.ts`：后端 snake_case 与前端类型的唯一映射层 |
| 状态 | `src/stores/auth.ts`（唯一 Pinia store）+ composables |
| 样式 | 18 张 CSS：`game-ui.css`、`controls.css`、`game-shell.css` 等 |

## 主题与素材

- `useTheme.ts`：cookie `crumb_theme` + `prefers-color-scheme`，写 `<html data-theme>`。
- `ThemeSwitch.vue`：侧栏底部与个人资料菜单。
- `ArtImage.vue`：同一格叠 day/night 两张图，切换 520ms 交叉淡出。
- 素材在 `src/assets/halloween/`，规则见该目录的 README。
- 手机端走 `/m` URL 树与媒体查询，没有第二套组件。

## 测试

```bash
npm ci
npm run build     # vue-tsc -b && vite build
npm test          # vitest run
```

- 58 个 spec、446 个 `it`。
- 最近一次实跑（2026-11-17，`d90778d`）：build 通过，442/442 通过。
- 没有浏览器 E2E 或视觉回归；昼夜与断点靠人眼与 `screenshots/` 下的手工探针。

## 约定

- 业务状态不在浏览器持久化；不使用 localStorage/sessionStorage 保存学习真相。
- 写操作带 `Idempotency-Key`；提交类操作在 composable 里持锁防双击。
- 不新增覆盖层样式表；改原样式表。
