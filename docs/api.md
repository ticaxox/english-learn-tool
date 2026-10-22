# API 文档

- 事实基线：`caa731c`；容器/代理运行证据对应 `a5bf49b` / run `39801657963`
- API 前缀：`/api/v1`
- OpenAPI：`http://127.0.0.1:8000/api/v1/openapi.json`
- Swagger UI：`http://127.0.0.1:8000/api/v1/docs`
- 当前后端：仅基础服务元数据和健康检查，无认证与业务 API

## 1. 通用约定

### Request ID

- 客户端可以发送 `X-Request-ID`。
- 仅接受 1–128 位、以字母或数字开头、由字母、数字、`.`、`_`、`:`、`-` 组成的值。
- 非法或缺失时由后端生成。
- 所有响应都回写 `X-Request-ID`。
- 错误响应体中的 `request_id` 与响应头一致。

### 错误结构

```json
{
  "code": "ERROR_CODE",
  "message": "Human-readable message",
  "details": null,
  "request_id": "request-id"
}
```

当前已实现通用处理：

| HTTP 状态 | 默认错误码 |
|---:|---|
| 400 | `BAD_REQUEST` |
| 401 | `UNAUTHORIZED` |
| 403 | `FORBIDDEN` |
| 404 | `NOT_FOUND` |
| 405 | `METHOD_NOT_ALLOWED` |
| 409 | `CONFLICT` |
| 413 | `PAYLOAD_TOO_LARGE` |
| 415 | `UNSUPPORTED_MEDIA_TYPE` |
| 422 | `VALIDATION_ERROR` |
| 429 | `RATE_LIMITED` |
| 500 | `INTERNAL_SERVER_ERROR` |
| 503 | 由具体端点返回，例如 `SERVICE_NOT_READY` |

错误响应不得包含密钥、数据库连接串或内部堆栈。

## 2. 当前已实现端点

### `GET /health/live`

进程存活检查，不访问数据库或 Redis。

成功响应示例：

```json
{
  "status": "ok",
  "service": "AI English Learning Tool",
  "version": "0.1.0"
}
```

### `GET /health/ready`

检查配置、PostgreSQL 和 Redis。全部正常时返回 `200`；任一组件失败时返回 `503 SERVICE_NOT_READY`。

检测组件：

- `configuration`
- `database`
- `redis`

错误详情只包含组件状态、延迟和异常类型，不返回异常正文或连接信息。

### `GET /api/v1`

返回当前 API 服务元数据。

已验证响应：

```json
{
  "name": "AI English Learning Tool",
  "version": "0.1.0",
  "environment": "development",
  "api_version": "v1"
}
```

### OpenAPI

- `GET /api/v1/openapi.json`
- `GET /api/v1/docs`
- `GET /api/v1/redoc`

## 3. 调用示例

```powershell
Invoke-RestMethod -Uri 'http://127.0.0.1:8000/health/live'
Invoke-RestMethod -Uri 'http://127.0.0.1:8000/health/ready'
Invoke-RestMethod -Uri 'http://127.0.0.1:8000/api/v1' -Headers @{'X-Request-ID'='local-smoke-001'}
```

通过前端开发代理：

```powershell
Invoke-RestMethod -Uri 'http://127.0.0.1:5173/api/v1'
```

当前基线已验证：前端开发代理返回 `200`、Request ID 原样回传，`/health/live` 返回 `200`。`a5bf49b` 的 Compose CI 另经反向代理验证 `/health/live`、`/health/ready` 与 `/api/v1`；这只覆盖基础路由，不代表认证或业务 API 已实现。

## 4. 前端当前声明的认证契约

`frontend/src/api/contracts.ts` 和前端壳层预留以下路径：

- `POST /api/v1/auth/login`
- `POST /api/v1/auth/refresh`
- `POST /api/v1/auth/logout`
- `POST /api/v1/auth/change-password`
- `GET /api/v1/auth/me`

**重要：这些后端路由当前尚未实现。** 前端登录、改密和会话恢复测试只验证客户端逻辑与契约处理，不代表真实认证联调完成。`S-FE-04` 仍为 `CONDITIONAL`，依赖后续 `AUTH-INT-001`。

## 5. 规划中的业务 API 分组

产品基线规划的组别如下，当前均需后续任务实现后才能写入“可用 API”：

| 分组 | 目标能力 |
|---|---|
| `/admin/*` | 成员、聚合看板、AI provider、提示词与用量 |
| `/users/me/*` | 学习档案 |
| `/learning/*` | 今日计划、心跳、统计、学习事件 |
| `/wordbooks/*` | 词书、导入预览、导入、导出、激活、删除 |
| `/memory/*` | 配置、会话、事件、已记住/恢复、错词 |
| `/practice/*` | 会话、草稿、重生成、提交、结果、记录 |
| `/coach/*` | 对话、消息、SSE、action receipt 撤销 |
| `/challenges/*` | 今日地图、节点、BOSS 提交、历史 |
| `/notifications/*` | 通知与偏好 |

这些分组是接口边界，不是当前可调用的实现。

## 6. 后续 API 实现门槛

1. 所有用户资源在服务层校验所有权，不能只依赖前端隐藏。
2. 写操作按任务要求支持 `Idempotency-Key`。
3. 异步 AI 任务使用 `202`，并以数据库任务状态为权威。
4. 提交前禁止返回正确答案、解析或参考内容。
5. Cookie/CSRF、Refresh Token 轮换和角色权限必须有集成测试。
6. API 变更同步更新 OpenAPI、前端 client、测试和本文档。
