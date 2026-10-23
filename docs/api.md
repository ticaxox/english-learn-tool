# API 文档

- 交付基线：`efc6bcbd2679eca02613a7143c68d04dddc36a59`
- API 前缀：`/api/v1`
- OpenAPI JSON：`/api/v1/openapi.json`
- Swagger UI：`/api/v1/docs`
- 当前 OpenAPI：84 个路径、153 个 schema
- 认证：Access Token + HttpOnly Refresh Cookie + CSRF 双提交

## 1. 通用约定

### Request ID

- 客户端可发送 `X-Request-ID`；缺失或非法时由后端生成。
- 所有响应回写 `X-Request-ID`。
- 错误体中的 `request_id` 与响应头一致。

### 错误结构

```json
{
  "code": "ERROR_CODE",
  "message": "Human-readable message",
  "details": null,
  "request_id": "request-id"
}
```

常见状态：`400`、`401`、`403`、`404`、`409`、`413`、`415`、`422`、`429`、`500`、`503`。错误响应不返回堆栈、密钥、数据库连接串或完整答案。

### 分页

- 成员、词书、练习记录、通知、教练会话等使用游标或 offset 分页。
- 响应通常包含 `items`、`next_cursor`/`has_more` 或 `total`/`offset`/`limit`。
- 客户端不得自行拼接不存在的光标。

### 幂等

- 写操作使用 `Idempotency-Key`（如词书导入、练习创建/提交、BOSS 提交、部分通知操作）。
- 重复请求必须返回同一结果或明确冲突，不能重复扣额度、重复判分或重复推进计划。
- 词书导入同时校验 `preview_id`、`preview_token` 和 `preview_hash`。

### 202 与异步任务

`202` 只表示任务已接受，不是业务完成：

- 词书导入/导出/删除：创建 `wordbook_jobs`，轮询 `/wordbooks/jobs/{job_id}` 或 `/exports/{job_id}`。
- AI 练习生成/评分、教练消息、挑战生成：持久化任务，轮询对应状态或 SSE。
- 任务失败保留真实 `error_code`、可重试标记和 Request ID。

### SSE

AI 教练消息使用 SSE：

- 流式事件包含序号和事件类型。
- 断线后通过 `Last-Event-ID` 或事件查询恢复。
- 事件示例：`message.delta`、`action.applied`、`usage`、`done`、`error`。
- 前端不得把 SSE 断开解释为成功，也不得用假流兜底。

## 2. 认证与身份

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/auth/login` | 登录，设置 Refresh/CSRF Cookie |
| POST | `/auth/refresh` | 轮换 Refresh Token，返回新 Access Token |
| POST | `/auth/logout` | 撤销当前 Refresh 会话 |
| POST | `/auth/change-password` | 改密并撤销 Refresh 会话 |
| GET | `/auth/me` | 当前账号、角色和改密状态 |

Access Token 通过 `Authorization: Bearer <token>` 发送。Refresh/Logout 需要 Refresh Cookie、CSRF Cookie 和 `X-CSRF-Token`；生产 Cookie 使用 `Secure`。

## 3. 管理员

| 分组 | 代表路径 |
|---|---|
| 成员 | `GET/POST /admin/users`、`GET/PATCH/DELETE /admin/users/{id}`、`POST /admin/users/{id}/reset-password` |
| 成员导入 | `POST /admin/users/import/preview`、`POST /admin/users/import`、`GET /admin/users/import/{id}` |
| AI provider | `GET/POST /admin/ai/providers`、`PATCH/DELETE /admin/ai/providers/{id}`、`POST .../test`、`POST .../models` |
| 提示词 | `GET /admin/ai/prompts`、`GET/PUT /admin/ai/prompts/{key}` |
| 用量 | `GET /admin/ai/usage` |
| 看板 | `GET /admin/dashboard` |

管理员接口只返回隐私安全的聚合或必要账号字段；成员答题正文、草稿、教练消息和私有词书正文不可读取。

## 4. 成员与学习

| 分组 | 代表路径 |
|---|---|
| 档案 | `GET/PATCH /users/me/profile` |
| 今日计划 | `GET /learning/today`、`POST /learning/daily-plan/ensure`、`POST /learning/heartbeat` |
| 统计/事件 | `GET /learning/stats`、`GET /learning/events` |
| 词书 | `GET/POST /wordbooks`、`POST /wordbooks/import/preview`、`POST /wordbooks/import`、`POST /wordbooks/{id}/activate` |
| 记忆 | `GET/PUT /memory/config`、`POST /memory/sessions`、`POST /memory/sessions/{id}/events`、`GET /memory/mistakes` |
| 练习 | `POST /practice/sessions`、`GET/PUT .../{id}`、`POST .../submit`、`GET /practice/records`、`GET /practice/mistakes` |
| 教练 | `GET/POST /coach/conversations`、`GET/POST .../{id}/messages`、`GET /coach/streams/{message_id}`、`POST /coach/action-receipts/{id}/undo` |
| 挑战 | `GET /challenges/today`、`POST /challenges/today/generate`、`POST .../nodes/{id}/start`、`POST .../boss-submit` |
| 通知 | `GET /notifications`、`GET/PUT /notifications/preferences`、`PATCH .../{id}/read` |

## 5. 当前 OpenAPI 路径分组

OpenAPI 共 84 个 path。按前缀统计：

| 分组 | 路径数 |
|---|---:|
| 系统/健康 | 3 |
| Auth | 5 |
| 管理员成员 | 6 |
| 管理员 AI | 7 |
| 管理员看板 | 1 |
| AI jobs/usage | 4 |
| 词书与导出 | 10 |
| 学习/档案 | 6 |
| 记忆 | 9 |
| 练习 | 12 |
| 教练 | 8 |
| 挑战 | 8 |
| 通知 | 5 |

实际 method、参数和 schema 以 `backend/openapi.json` 与运行中的 `/api/v1/openapi.json` 为准。

## 6. 答案与隐私

- 练习创建/读取阶段不返回 `correct_option_id`、解析、参考内容或评分。
- 提交后结果才包含答案、解析、维度分和建议。
- 管理员 API 不返回成员答题正文或教练正文。
- AI Key 只返回掩码；错误信息不包含 Key、完整 prompt 或内部堆栈。

## 7. 调用示例

```powershell
$login = Invoke-RestMethod -Method Post -Uri 'http://127.0.0.1:8000/api/v1/auth/login' `
  -ContentType 'application/json' `
  -Body '{"username":"<username>","password":"<password>"}'
$headers = @{ Authorization = "Bearer $($login.access_token)" }
Invoke-RestMethod -Uri 'http://127.0.0.1:8000/api/v1/learning/today' -Headers $headers
```

## 8. 已知限制

- `GET /learning/today` 的 `ai_practice` 摘要目前仍返回旧 `not_available` 字段；已实现的 AI 练习使用 `/practice`，不要据此认为 AI 练习整体未实现。
- 生产 provider、公网 SSE、TLS、限流和真实部署尚未由 T-SHIP-002 冻结。
- API 文档中的状态必须与 `docs/fact-check.md` 和 QA 证据同步更新。
