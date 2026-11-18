# API 文档

- 代码基线：`main` @ `1cea3ff` / `v0.1.7`
- 前缀：`/api/v1`
- OpenAPI JSON：`/api/v1/openapi.json`；Swagger UI：`/api/v1/docs`
- 当前产物：**117 条路径 / 148 个操作 / 203 个 schema**
- `/api/v1/mcp` 按设计 `include_in_schema=False`，不出现在 OpenAPI 中

## 1. 通用约定

### Request ID

客户端可发送 `X-Request-ID`；缺失或非法时由后端生成，所有响应回写该头，错误体中的 `request_id` 与之一致。

### 错误结构

```json
{
  "code": "ERROR_CODE",
  "message": "Human-readable message",
  "details": null,
  "request_id": "request-id"
}
```

常见状态：`400`、`401`、`403`、`404`、`409`、`413`、`415`、`422`、`429`、`500`、`503`。错误响应不返回堆栈、密钥、连接串或完整答案。

### 认证

- 登录返回短时 Access Token（前端只放内存）与 HttpOnly Refresh Cookie。
- 写请求携带 `X-CSRF-Token`（双提交 Cookie）。
- `Authorization: Bearer <token>` 访问受保护端点。
- 2026-11-18 起服务端不再校验 Origin 白名单，CSRF 校验仍在。

### 幂等与 202

- 写操作普遍接受 `Idempotency-Key`；AI 任务、词书导入/导出、练习生成返回 `202` + 任务标识。
- `202` 只表示任务已接收，必须轮询或订阅终态；任务状态值见各域。

### 分页

- 列表类接口用页码或游标；教练消息与通知使用游标（`cursor` + `limit`），返回 `next_cursor`。

### SSE

- 教练回复通过 `GET /coach/streams/{message_id}` 输出 `text/event-stream`，事件带序号；断线可用 `Last-Event-ID` 续传。

## 2. 路由清单

### 系统与健康

```text
GET    /api/v1                  服务元数据（name/version/environment）
GET    /health/live             进程存活，不访问依赖
GET    /health/ready            依赖就绪
```

### 认证（6）

```text
POST   /api/v1/auth/register
POST   /api/v1/auth/login
POST   /api/v1/auth/refresh
POST   /api/v1/auth/logout
GET    /api/v1/auth/me
PATCH  /api/v1/auth/me
POST   /api/v1/auth/change-password
```

（`/auth/me` 的 GET/PATCH 合计 2 个操作，域内共 6 条路径。）

### 个人资料与设置

```text
GET, PATCH  /api/v1/users/me/profile
```

### 学习计划与记忆（10）

```text
GET    /api/v1/learning/today
POST   /api/v1/learning/daily-plan/ensure
GET    /api/v1/learning/stats
GET    /api/v1/learning/events
POST   /api/v1/learning/heartbeat
GET, PUT /api/v1/memory/config
POST   /api/v1/memory/sessions
GET    /api/v1/memory/sessions/{session_id}
POST   /api/v1/memory/sessions/{session_id}/complete
POST   /api/v1/memory/sessions/{session_id}/events
GET    /api/v1/memory/mistakes
PATCH  /api/v1/memory/mistakes/{entry_id}/priority
PATCH  /api/v1/memory/words/{state_id}/master
PATCH  /api/v1/memory/words/{state_id}/restore
POST   /api/v1/memory/progress/reset
```

### 练习（13）

```text
POST, GET      /api/v1/practice/sessions
GET, DELETE    /api/v1/practice/sessions/{session_id}
PUT            /api/v1/practice/sessions/{session_id}/draft
POST           /api/v1/practice/sessions/{session_id}/start
POST           /api/v1/practice/sessions/{session_id}/submit
POST           /api/v1/practice/sessions/{session_id}/regenerate
GET            /api/v1/practice/sessions/{session_id}/result
GET, POST      /api/v1/practice/sessions/{session_id}/conversation/turns
GET            /api/v1/practice/records
GET            /api/v1/practice/records/{session_id}
DELETE         /api/v1/practice/records/bulk
GET            /api/v1/practice/mistakes
GET            /api/v1/practice/events
```

### 教练（10）

```text
GET, POST      /api/v1/coach/conversations
PATCH, DELETE  /api/v1/coach/conversations/{conversation_id}
GET, POST      /api/v1/coach/conversations/{conversation_id}/messages
POST           /api/v1/coach/conversations/{conversation_id}/attachments
GET            /api/v1/coach/attachments/{attachment_id}
GET            /api/v1/coach/messages/{message_id}
GET            /api/v1/coach/messages/{message_id}/events
GET            /api/v1/coach/streams/{message_id}
GET            /api/v1/coach/action-receipts/{receipt_id}
POST           /api/v1/coach/action-receipts/{receipt_id}/undo
```

### 每日闯关（9）

```text
GET    /api/v1/challenges/today
POST   /api/v1/challenges/today/generate
POST   /api/v1/challenges/today/regenerate
GET    /api/v1/challenges/jobs/{job_id}
GET    /api/v1/challenges/history
GET    /api/v1/challenges/{challenge_id}
GET    /api/v1/challenges/{challenge_id}/nodes/{node_id}
POST   /api/v1/challenges/{challenge_id}/nodes/{node_id}/start
POST   /api/v1/challenges/{challenge_id}/nodes/{node_id}/boss-submit
```

### 词书（8）

```text
GET            /api/v1/wordbooks
POST           /api/v1/wordbooks/import
POST           /api/v1/wordbooks/import/preview
PATCH          /api/v1/wordbooks/import/previews/{preview_id}
GET            /api/v1/wordbooks/jobs/{job_id}
GET, PATCH, DELETE  /api/v1/wordbooks/{wordbook_id}
POST           /api/v1/wordbooks/{wordbook_id}/activate
POST           /api/v1/wordbooks/{wordbook_id}/export
```

### 导出

```text
GET  /api/v1/exports/{job_id}
GET  /api/v1/exports/{job_id}/download
```

### 知识库（6）

```text
GET            /api/v1/knowledge
POST           /api/v1/knowledge/folders
PATCH, DELETE  /api/v1/knowledge/folders/{folder_id}
GET, POST      /api/v1/knowledge/folders/{folder_id}/documents
GET, PATCH, DELETE  /api/v1/knowledge/documents/{document_id}
GET            /api/v1/knowledge/search
```

### 个人 AI 与进度（`/me`，19）

```text
GET, POST      /api/v1/me/ai/providers
POST           /api/v1/me/ai/providers/probe
POST           /api/v1/me/ai/providers/probe/models
GET, PATCH, DELETE  /api/v1/me/ai/providers/{provider_id}
POST           /api/v1/me/ai/providers/{provider_id}/test
POST           /api/v1/me/ai/providers/{provider_id}/models
GET, PUT       /api/v1/me/ai/memory
GET            /api/v1/me/ai/background-tasks
POST           /api/v1/me/ai/background-tasks/{task_id}/retry
DELETE         /api/v1/me/ai/background-tasks/{task_id}
GET, POST      /api/v1/me/memories
PATCH, DELETE  /api/v1/me/memories/{memory_id}
GET, POST      /api/v1/me/tokens
DELETE         /api/v1/me/tokens/{token_id}
POST           /api/v1/me/tokens/{token_id}/refresh
GET            /api/v1/me/progress
GET            /api/v1/me/progress/badges
GET            /api/v1/me/progress/weekly
GET            /api/v1/me/progress/footprint
```

### AI 通用任务

```text
POST   /api/v1/ai/jobs
GET    /api/v1/ai/jobs/{job_id}
POST   /api/v1/ai/jobs/{job_id}/cancel
GET    /api/v1/ai/usage/me
```

### 通知（5）

```text
GET    /api/v1/notifications
GET, PUT  /api/v1/notifications/preferences
GET    /api/v1/notifications/unread-count
PATCH  /api/v1/notifications/{notification_id}/read
POST   /api/v1/notifications/read-all
```

### 管理端（16）

```text
GET, POST      /api/v1/admin/users
POST           /api/v1/admin/users/import
POST           /api/v1/admin/users/import/preview
GET            /api/v1/admin/users/import/{import_id}
GET, PATCH, DELETE  /api/v1/admin/users/{user_id}
POST           /api/v1/admin/users/{user_id}/reset-password
GET            /api/v1/admin/dashboard
GET, POST      /api/v1/admin/ai/providers
PATCH, DELETE  /api/v1/admin/ai/providers/{provider_id}
POST           /api/v1/admin/ai/providers/{provider_id}/test
POST           /api/v1/admin/ai/providers/{provider_id}/models
GET            /api/v1/admin/ai/prompts
GET, PUT       /api/v1/admin/ai/prompts/{prompt_key}
GET            /api/v1/admin/ai/usage
GET, POST      /api/v1/admin/knowledge
PATCH, DELETE  /api/v1/admin/knowledge/{document_id}
```

### MCP

```text
POST   /api/v1/mcp      Streamable HTTP（JSON-RPC），Bearer 个人访问令牌
```

## 3. 练习与任务状态

| 实体 | 状态 |
|---|---|
| 练习会话 | `generating` → `ready` → `submitted`；异常为 `failed` / `cancelled` |
| 提交评分 | `scoring` → `completed` / `failed` |
| AI 任务 | `queued` → `running` → `succeeded` / `failed` / `stale` / `cancelled` |
| 闯关计划 | `generating` → `ready` / `failed` |

## 4. 契约产物

`backend/openapi.json` 由 `app.openapi()` 生成，是仓库内唯一的 API 契约快照。修改路由后必须重新生成：

```powershell
cd backend
uv run python -c "import json; from app.main import app; print(json.dumps(app.openapi(), ensure_ascii=False, indent=2))" > openapi.json
```

后端测试 `test_learning_contract.py` 会比较产物与 `app.openapi()` 的规范化哈希与路径数；产物过期即失败。
