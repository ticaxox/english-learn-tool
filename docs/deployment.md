# 部署与运行

- 事实基线：`c3b2a50`
- 本地开发：基础服务可启动，相关命令已验证
- 容器、Compose、CI 与公网部署：**待 T-SHIP 验证**
- 当前仓库中不存在 Dockerfile、`docker-compose.yml`、`.github/workflows/` 或根级 `.env.example`

## 1. 当前本地运行方式

### 依赖

- PostgreSQL 16
- Redis 7
- Python 3.12 + `uv`
- Node.js 20.19+ 与 npm 10+

### 后端

```powershell
cd backend
uv sync --locked --all-groups
uv run alembic upgrade head
uv run uvicorn app.main:app --host 127.0.0.1 --port 8000
```

运行前以 `backend/.env.example` 为模板准备本地 `.env`，替换全部占位连接串和密钥。不要把 `.env` 提交到 Git。

验证：

```powershell
Invoke-RestMethod -Uri 'http://127.0.0.1:8000/health/live'
Invoke-RestMethod -Uri 'http://127.0.0.1:8000/health/ready'
Invoke-RestMethod -Uri 'http://127.0.0.1:8000/api/v1'
```

### 前端

```powershell
cd frontend
npm ci
npm run dev
```

- 前端入口：`http://127.0.0.1:5173`
- `/api` 默认代理到 `http://127.0.0.1:8000`
- 可用 `VITE_API_PROXY_TARGET` 切换代理目标
- `VITE_API_BASE_URL` 默认 `/api/v1`

### 后台入口

在已准备本地 `.env` 且 Redis 可访问时，以下入口可启动；当前只执行心跳和调度 tick：

```powershell
cd backend
uv run arq app.workers.worker.WorkerSettings
uv run arq app.workers.scheduler.SchedulerSettings
```

本次基线验证：worker 启动 `worker_heartbeat`；scheduler 启动 `scheduler_tick` 和 cron；Redis 7.0.15 可连接。核验后均通过 Ctrl+C 停止。它们不是业务异步任务、不是定时学习计划，也不代表 AI 链路已实现。

## 2. 环境变量

### 后端

来源：`backend/.env.example`。

| 类别 | 变量 |
|---|---|
| 应用 | `APP_ENV`、`APP_NAME`、`APP_VERSION`、`APP_BASE_URL`、`FRONTEND_BASE_URL`、`APP_TIMEZONE` |
| 数据依赖 | `DATABASE_URL`、`REDIS_URL` |
| 安全 Secret | `JWT_SECRET`、`REFRESH_TOKEN_PEPPER`、`SECRET_ENCRYPTION_KEY` |
| 令牌有效期 | `ACCESS_TOKEN_MINUTES`、`REFRESH_TOKEN_DAYS` |
| CORS/日志 | `CORS_ORIGINS`、`LOG_LEVEL` |
| 健康检查/连接池 | `HEALTH_CHECK_TIMEOUT_SECONDS`、`DB_POOL_SIZE`、`DB_MAX_OVERFLOW` |

安全 Secret 至少 32 个字符；示例值不可用于任何真实环境。

### 前端

来源：`frontend/.env.example`。

| 变量 | 默认值/用途 |
|---|---|
| `VITE_API_BASE_URL` | `/api/v1`，浏览器请求前缀 |
| `VITE_API_PROXY_TARGET` | `http://127.0.0.1:8000`，Vite `/api` 代理目标 |

### 根级配置

根级 `.env.example` 尚未创建。若要形成统一 Compose 配置，必须由 T-SHIP 在允许路径内建立，并确保所有值均为非敏感占位值。

## 3. 当前已验证结果

| 检查 | 结果 |
|---|---|
| 后端锁文件安装 | 成功 |
| 本地 Alembic 迁移 | 成功 |
| Alembic drift check | 无新迁移 |
| 后端测试 | 18 passed |
| 前端构建 | 成功 |
| Vite `/api` 代理 | `/api/v1` 返回 200 |
| FastAPI liveness | 200 |

这些结果只覆盖本地进程，不覆盖容器。

## 4. 容器与 CI 门禁（待 T-SHIP 验证）

T-SHIP 需要提供以下可回读证据后，才能修改本文状态：

| 门禁 | 必须证明 |
|---|---|
| Docker 镜像 | API、worker、scheduler、frontend 镜像可构建 |
| Docker Compose | 从空环境启动 API、frontend、PostgreSQL、Redis 等必要服务 |
| 空库迁移 | 容器内对空 PostgreSQL 执行 Alembic 升级成功 |
| 容器健康 | API `/health/live` 与 `/health/ready` 在 Compose 内通过 |
| CI | PR 上执行后端检查、前端构建、镜像构建、迁移与敏感信息扫描 |
| 镜像发布 | 版本化 tag/digest 与提交 SHA 可追溯 |
| 反向代理/HTTPS | SSE 不缓冲，管理端口不暴露，TLS 配置有效 |
| 备份/回滚 | 数据库备份、迁移失败和镜像回滚路径可复现 |

在以上证据缺失时：

- 不得写“Docker Compose 已通过”。
- 不得写“CI 绿”。
- 不得写“容器迁移成功”。
- 不得宣称公网部署可用。

## 5. 目标部署拓扑

产品基线计划使用 Linux + Docker Engine + Docker Compose v2，至少包含：

- FastAPI API
- ARQ worker
- ARQ scheduler
- PostgreSQL 16
- Redis 7
- Vue 构建静态文件服务
- HTTPS 反向代理

安全要求：

- 只开放公网所需的 HTTP/HTTPS 和受控运维端口。
- PostgreSQL、Redis、队列管理端口不对公网暴露。
- 密钥只放部署环境或 Secret 管理，不进入镜像和仓库。
- AI provider 额度、速率和并发在生产环境进一步收紧。
- 部署前备份，失败时保留上一镜像和数据库备份。

现有共享测试服务器的资源规格低于产品推荐规格，且已有其他服务运行；部署方案、资源评估、域名和 HTTPS 必须由 A40 在独立任务中验证，本文不得复制任何服务器接入信息。

## 6. 更新部署文档的条件

只有同时满足以下条件才可把容器状态改为“已验证”：

1. 回读 A40 的详细报告和原始日志。
2. 确认运行提交与镜像 digest 对应。
3. 确认 Compose 健康检查、迁移和回滚路径真实执行。
4. 由 A30 或指定验收方完成复核。
5. 文档记录日期、提交、镜像和仍存在的限制。
