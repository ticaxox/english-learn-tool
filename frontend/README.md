# AI 英语学习工具｜前端

这是 v1.1 的 Vue 3 应用，覆盖真实认证、成员管理、词书工作区、T-FE-004 学习工作区、T-FE-005 AI 管理员页面，T-FE-006 的四类 AI 练习、草稿、结果、记录与错题，T-FE-007 的站内通知中心与通知偏好，以及 T-FE-008 的长期 AI 教练、真实 SSE 与动作撤销。所有业务状态、评分、队列、连接检查和用量均以服务端为唯一真相，不使用静态业务假数据。

## 环境

- Node.js 20.19+（当前开发环境使用 Node.js 24）
- npm 10+
- 真实运行的 FastAPI 后端（默认 `http://127.0.0.1:8000`）

## 安装与启动

```bash
npm ci
npm run dev
```

默认浏览器请求 `/api/v1`，开发服务器和预览服务器都会把 `/api` 代理到 `http://127.0.0.1:8000`，无需先创建 `.env`。需要切换后端地址时，再复制 `.env.example` 为 `.env` 并设置：

```dotenv
VITE_API_BASE_URL=http://127.0.0.1:8000/api/v1
VITE_API_PROXY_TARGET=http://127.0.0.1:8000
```

如果后端未启动，登录页和业务骨架页会显示真实网络错误、Request ID（后端提供时）和重试入口，不会切换为 mock 登录或静态演示数据。

## 后端契约

认证流程按 v1.1 文档实现：

- `POST /api/v1/auth/login`：用户名、密码；响应包含 `access_token` 与 `csrf_token`。
- `POST /api/v1/auth/refresh`：使用 HttpOnly Refresh Cookie 轮换令牌；刷新请求需要可读 CSRF Cookie 与 `X-CSRF-Token`，响应返回新令牌。
- `GET /api/v1/auth/me`：返回当前用户对象。
- `POST /api/v1/auth/change-password`：提交 `old_password` 和
ew_password`。
- `POST /api/v1/auth/logout`：撤销当前刷新令牌。

当前用户对象至少包含：

```json
{
  "id": "uuid",
  "username": "member_name",
  "display_name": "显示名称",
  "role": "member",
  "must_change_password": false
}
```

Access Token 仅保存在 API client 的内存中。页面刷新后通过 HttpOnly Cookie 调用刷新接口恢复会话，不使用 localStorage 或 sessionStorage 保存业务真相。

统一错误结构应遵循：

```json
{
  "code": "ERROR_CODE",
  "message": "错误说明",
  "details": {},
  "request_id": "uuid"
}
```

API client 优先读取响应头 `X-Request-ID`，并在错误界面展示。对于 Cookie 写请求，API client 会优先使用内存中的 CSRF Token，页面刷新后从覆盖 SPA 根路径的可读 Cookie 恢复，并回传 `X-CSRF-Token`；HttpOnly Refresh Cookie 仍保持最小路径。最终细节以 A10 的 OpenAPI 与真实联调结果为准。

## 已实现范围

- Vue 3 + Vite + TypeScript + Pinia + Vue Router。
- 登录、首次改密、会话恢复、退出、Access Token 内存保存。
- 角色守卫、管理员路由保护、改密拦截。
- 真实成员列表、搜索、角色/状态筛选和游标分页。
- 单个创建、CSV 预览与确认、启停、角色修改、重置密码和删除确认。
- 一次性临时密码仅在当前页面状态显示，关闭后清除；不使用 localStorage/sessionStorage 业务真相。
- 隐私安全的成员详情与允许的聚合指标，不展示答案、草稿、教练或私有词书正文。
- 统一 API client、`/api/v1` 前缀、结构化错误、网络重试和 Request ID 展示。
- 403/管理员越权、429、404、后端不可用、登录失败和最后管理员保护错误等可见状态。
- 学习档案 `GET/PATCH /users/me/profile` 与记忆配置 `GET/PUT /memory/config`。
- 今日计划 `GET /learning/today`、幂等创建 `/learning/daily-plan/ensure` 与服务端统计 `/learning/stats`。
- 翻卡、选择、拼写三种训练；服务端判分、事件幂等键、会话刷新恢复与 30 秒心跳/后台暂停。
- 错词列表、重点复习、已记住/恢复，以及真实空态和失败态。
- T-BE-004 契约坐标固定为 `contract_sha 25ad69f` / OpenAPI raw `248ff876…f57e7`；字段映射集中在 `src/api/contract-adapter.ts`。
- AI 管理员页面：Provider 列表/创建/编辑/启停/默认与备用顺序、真实连接检查、模型列表与手填回退、提示词读取/覆盖保存、隐私安全聚合用量。
- T-BE-005 管理员契约固定为 `6c72f19` / OpenAPI raw `7a0463b5…` / semantic `8497bc98…`；API Key 只存在于当前表单内存，列表仅显示服务端掩码。
- AI 练习：填空、阅读、翻译、作文四类创建与 202 生成轮询；服务端草稿/版本冲突、未作答重生成、提交幂等、提交后结果、记录筛选、错题与本人批量删除。
- T-BE-006 最终契约为 `d6dcdbf`；提交前页面与 API 解析均拒绝答案、解析、参考内容或评分字段。
- 站内通知：游标分页、未读筛选、单条/全部已读、未读数、类别偏好、免打扰时间、每日非 AI 上限与 AI 例外说明；正文只按纯文本渲染。
- T-BE-007 通知契约坐标固定为 `fe52cf2` / raw `8309ee03…` / semantic `82a08895…`，实时 OpenAPI semantic 与冻结值一致。
- AI 教练：长期会话 CRUD、游标消息分页、202 消息任务、真实 SSE 增量、usage、刷新/断线恢复、action receipt 与 24 小时撤销。
- T-BE-008 教练契约固定为 `44f49ca` / raw `99026f88…` / semantic `dfe1ca30…`；不保存对话正文或回执到浏览器存储。
- Vitest 测试基线。

## 路由

`/login`、`/change-password`、`/overview`、`/wordbooks`、`/memory`、`/practice`、`/practice/:sessionId`、`/practice/records`、`/practice/mistakes`、`/challenges`、`/challenges/:challengeId`、`/coach`、`/notifications`、`/notifications/preferences`、`/settings`、`/admin/dashboard`、`/admin/users`、`/admin/ai/providers`、`/admin/ai/prompts`、`/admin/ai/usage`。

成员管理、词书、学习、AI 练习、通知与 AI 教练均使用真实接口；每日闯关和看板等未实现页面只显示真实接口响应摘要或真实错误。

## 验证

```bash
npm ci
npm test
npm run build
git diff --check
```

## 暂不包含

- 每日闯关和控制台图表。
- 前端自行推进 FSRS、静态评分、离线计时或浏览器存储学习状态。
- 复杂动画、游戏化皮肤、图片或图标素材。
- 后端、CI、Docker、部署与服务器操作。
