# AI 英语学习工具｜前端

这是 v1.1 的 Vue 3 应用壳层，覆盖 T-FE-001 的认证、路由守卫、真实 API 接入和基础错误状态。当前不实现完整业务页面，也不使用任何静态业务假数据。

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

- `POST /api/v1/auth/login`：用户名、密码；响应包含 `access_token`。
- `POST /api/v1/auth/refresh`：使用 HttpOnly Refresh Cookie 轮换令牌，响应包含 `access_token`。
- `GET /api/v1/auth/me`：返回当前用户对象。
- `POST /api/v1/auth/change-password`：提交 `old_password` 和 `new_password`。
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

API client 优先读取响应头 `X-Request-ID`，并在错误界面展示。对于 Cookie 写请求，API client 会在收到 `X-CSRF-Token` 响应头后于内存保存并回传该值；最终 Cookie/CSRF 细节需以 A10 的 OpenAPI 与联调结果为准。

## 已实现范围

- Vue 3 + Vite + TypeScript + Pinia + Vue Router。
- 登录、首次改密、会话恢复、退出、Access Token 内存保存。
- 角色守卫、管理员路由保护、改密拦截。
- 统一 API client、`/api/v1` 前缀、结构化错误、网络重试和 Request ID 展示。
- v1.1 必需路由和连接真实 GET 接口的基础页面。
- 403/管理员越权、404、后端不可用、登录失败等可见状态。
- Vitest 测试基线。

## 路由

`/login`、`/change-password`、`/overview`、`/wordbooks`、`/memory`、`/practice`、`/practice/:sessionId`、`/challenges`、`/challenges/:challengeId`、`/coach`、`/notifications`、`/settings`、`/admin/dashboard`、`/admin/users`、`/admin/ai/providers`、`/admin/ai/prompts`。

业务页只显示真实接口响应摘要或真实错误；完整表单、表格、题目、进度和 AI 对话界面由后续任务实现。

## 验证

```bash
npm run build
npm test
```

## 暂不包含

- 完整业务 CRUD、词书导入、题目作答、SSE 对话和控制台图表。
- 复杂动画、游戏化皮肤、图片或图标素材。
- 后端、CI、Docker、部署与服务器操作。
