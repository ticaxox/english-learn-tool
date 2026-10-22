# 部署与运行

- 当前主线事实基线：`caa731cb2481a4aef50f3ff16f0d2fb811bcf9dc`
- 容器/CI 实现与运行证据：`a5bf49b038800003549b218278c146777dc2b096`，GitHub Actions run `39801657963`
- 容器基线：**GitHub Actions 已验证**
- GHCR 发布、云服务器、域名、TLS、公网入口与生产恢复：**未验证**

> 本机没有可用的 Docker Compose。本文件中的容器运行时事实来自 GitHub 托管 runner，不是本机 Compose 实测；配置解析或镜像构建不能替代运行时验证。

## 1. 已存在的交付资产

| 资产 | 位置 | 当前作用 |
|---|---|---|
| 根环境模板 | `.env.example` | Compose/CI 非敏感占位配置 |
| Compose | `docker-compose.yml` | PostgreSQL、Redis、迁移、API、worker、scheduler、frontend、反向代理 |
| 生产覆盖 | `deploy/compose.prod.yml` | 使用 GHCR 镜像并强制拉取 |
| 镜像定义 | `deploy/backend/Dockerfile`、`deploy/frontend/Dockerfile`、`deploy/reverse-proxy/Dockerfile` | 构建 API、前端和反向代理镜像 |
| 启动与验证 | `deploy/scripts/start-stack.sh`、`verify-stack.sh`、`verify-database.sh` | 干净启动、健康、权限、路由和迁移检查 |
| 发布与部署 | `.github/workflows/release.yml`、`deploy/scripts/deploy.sh` | GHCR 三镜像发布与不可变标签部署路径 |
| 备份与回滚 | `deploy/scripts/backup-db.sh`、`rollback.sh` | PostgreSQL custom-format 备份与应用镜像回滚 |
| CI | `.github/workflows/ci.yml` | 后端、前端、质量、安全扫描和 Compose 集成 |

## 2. 本地进程方式

### 依赖

- PostgreSQL 16
- Redis 7
- Python 3.12 + `uv`
- Node.js 20.19+ 与 npm 10+

如需走容器路径，还需要 Docker Engine 与 Docker Compose v2；当前 Windows 环境没有可用的 `docker compose`。

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

在本地 `.env` 已准备且 Redis 可访问时，以下入口可启动；当前只执行心跳和调度 tick：

```powershell
cd backend
uv run arq app.workers.worker.WorkerSettings
uv run arq app.workers.scheduler.SchedulerSettings
```

它们不是业务异步任务、不是定时学习计划，也不代表 AI 链路已实现。

## 3. 环境变量

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

### Compose 根级配置

根级 `.env.example` 已存在，包含：

- Compose 项目名、回环绑定地址和端口。
- API、frontend、reverse-proxy 镜像配置。
- PostgreSQL/Redis 占位连接。
- 应用、CORS、日志和数据库连接池设置。
- 三个安全 Secret 占位值。
- 备份目录参考值。

部署脚本会 source `.env`，包含空格的值必须加引号；密码中的 URL 保留字符在 `DATABASE_URL` 内必须百分号编码。所有 `replace_with_*` 值都必须在真实部署前替换。

## 4. Compose 干净启动路径

以下命令已写入项目并由 CI 使用；需要 Linux 或具备 Bash 与 Docker Compose v2 的环境：

```bash
cp .env.example .env
chmod 600 .env
ALLOW_INSECURE_EXAMPLE_ENV=1 ./deploy/scripts/start-stack.sh
```

`ALLOW_INSECURE_EXAMPLE_ENV=1` 只用于一次性本地/CI 检查，禁止用于真实部署。脚本会：

1. 校验 Compose 配置。
2. 构建项目镜像。
3. 启动 PostgreSQL 与 Redis 并等待健康。
4. 运行一次性 `migrate` 服务执行 `alembic upgrade head`。
5. 启动 API、worker、scheduler、frontend 和 reverse-proxy。
6. 验证七个常驻服务健康、应用容器非 root、代理路由和数据库 revision。

默认只有反向代理绑定 `127.0.0.1:8080`；PostgreSQL、Redis 和其他应用端口不发布到宿主。

## 5. 已通过的 GitHub Actions 证据

### Run 信息

| 项目 | 值 |
|---|---|
| 代码提交 | `a5bf49b038800003549b218278c146777dc2b096` |
| 合并主线 | `caa731cb2481a4aef50f3ff16f0d2fb811bcf9dc` |
| Actions run | `39801657963` |
| 结果 | 第 2 次尝试 5/5 作业通过 |

第 1 次尝试因 Docker Hub 临时 `500` 失败，不是配置回归；重跑后完整通过。

### 五类作业

| 作业 | 已证明范围 |
|---|---|
| Backend | 锁定依赖安装、Ruff lint/format、真实 PostgreSQL/Redis pytest |
| Frontend | `npm ci`、生产构建、Vitest |
| Quality | 质量清单校验器单测与结构校验；`RESULT=PASS` 不代表 30 个产品 FAIL 已修复 |
| Security | Gitleaks 完整 Git 历史扫描 |
| Compose | 镜像构建、空库迁移、七服务健康、非 root、端口和代理路由 |

### Compose 运行事实

- 七个常驻服务健康：PostgreSQL、Redis、API、worker、scheduler、frontend、reverse proxy。
- 一次性迁移容器先于应用启动，空库迁移成功。
- 数据库 revision 为 `20261022_0001`，`system_metadata` 表存在。
- API、worker、scheduler、frontend 和 reverse proxy 以 UID/GID `10001` 非 root 运行。
- 反向代理 `/health/live`、`/health/ready`、`/api/v1` 通过；`/healthz` 与 `/` 返回成功。
- PostgreSQL 与 Redis 不发布宿主端口；只有反向代理默认绑定 `127.0.0.1:8080`。

## 6. 本地应用基线验证

在 `caa731c` 文档工作树复跑：

| 检查 | 结果 |
|---|---|
| 后端锁文件安装 | 成功 |
| Ruff lint | 通过 |
| Ruff format check | 38 files already formatted |
| 后端测试 | 18 passed（一次性独立 PostgreSQL） |
| 空库 Alembic upgrade | 成功，revision `20261022_0001` |
| Alembic drift check | 无新迁移 |
| 前端安装 | 0 vulnerabilities |
| 前端测试 | 4 个文件、11 项通过 |
| 前端生产构建 | 43 个模块成功 |

若共享测试库残留其他分支的 revision，应改用一次性独立数据库，不得把脏库错误解释为当前主线回归。

## 7. GHCR 发布与生产部署边界

`release.yml` 会为 API、frontend 和 reverse proxy 构建 GHCR 镜像，并为每个镜像附加完整 Git SHA；版本 tag 同时产生语义版本和 `latest`。当前尚未：

- 创建版本 tag 或手动触发 release workflow。
- 向 GHCR 推送三个发布镜像。
- 验证镜像权限、拉取凭据、digest 或生产环境启动。
- 登录或修改云服务器。
- 配置域名、TLS、反向代理公网入口、监控或日志轮转。

`deploy.sh` 会拒绝 `local` 与 `latest`，只接受完整 40 位 SHA 或语义版本 tag；未执行该脚本不代表生产部署可用。

## 8. 目标部署拓扑

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
- 应用回滚不自动反向迁移数据库；结构不兼容时走单独批准的数据恢复流程。

当前共享服务器约 1 vCPU / 1 GiB，且已有其他服务运行，低于完整栈建议容量。不得直接部署完整 Compose 栈；文档和部署脚本均不包含服务器地址、账号或凭据。

## 9. 更新部署状态的触发条件

只有在对应证据可回读时才能升级状态：

1. **Compose/CI**：固定提交、run 编号、五作业结果和容器运行事实一致。
2. **GHCR**：三个镜像实际推送，记录 tag、digest、权限与拉取结果。
3. **云部署**：独立任务完成主机、端口、域名、TLS、监控和回滚验证。
4. **数据恢复**：在获批环境完成备份恢复演练，而不是只看脚本存在。
5. **产品演示**：认证、学习、AI 和隐私边界完成真实 E2E，质量门禁不再为 `FAIL / NOT_READY`。
