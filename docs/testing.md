# 测试与验证记录

- 应用层基线：`caa731c`
- 容器/CI 基线：`a5bf49b`；GitHub Actions run `39801657963` 第 2 次尝试
- 验证日期：2026-10-22
- 环境：Windows；`uv` 0.11.28；Python 3.12（`uv` 解析为 3.12.13）；Node.js 24.18.0；npm 11.16.0；本地 PostgreSQL 16.10 与 Redis 7.0.15 可访问
- 测试资源：一次性独立 PostgreSQL 数据库与 Redis DB `15`，不使用生产资源。若共享测试库含有其他分支的 revision，不得直接复跑；应创建独立空库。

## 1. 后端验证

### 依赖安装

```powershell
cd backend
uv sync --locked --all-groups
```

结果：成功；创建隔离 `.venv` 并安装 42 个包。日志提示目标盘与缓存盘不支持 hardlink，自动 fallback 为复制，不影响通过结果。

### Ruff

```powershell
uv run ruff check .
uv run ruff format --check .
```

结果：

- `All checks passed!`
- `38 files already formatted`

### 真实数据库/Redis 测试

```powershell
$env:TEST_DATABASE_URL = '<dedicated PostgreSQL test URL>'
$env:TEST_REDIS_URL = 'redis://127.0.0.1:6379/15'
uv run pytest
```

结果：`18 passed in 4.43s`。

当前 18 项覆盖：

- API 契约、Request ID 和统一错误结构。
- 配置拒绝短密钥、错误数据库驱动和非法 CORS。
- 数据库迁移版本与 `system_metadata` 存在性。
- `/health/live`、`/health/ready` 及依赖失败状态。
- 结构化日志基础。
- 测试 PostgreSQL 事务回滚与 Redis 专用 DB 清理。
- ARQ worker/scheduler 心跳入口。

测试使用真实 PostgreSQL/Redis；依赖不可用时失败，不会自动跳过或改用内存数据库。

### 本地迁移

使用一次性独立 PostgreSQL 空库执行：

```powershell
uv run alembic upgrade head
uv run alembic check
```

结果：

- `upgrade head` 从空库成功迁移到 `20261022_0001`。
- `check` 返回 `No new upgrade operations detected.`

容器空库迁移由下面第 4 节的 CI Compose 作业独立覆盖。

### ARQ 心跳入口

在本地 `.env` 已准备且测试 Redis 可访问时：

```powershell
uv run arq app.workers.worker.WorkerSettings
uv run arq app.workers.scheduler.SchedulerSettings
```

结果：

- worker 启动 1 个函数 `worker_heartbeat`，Redis 7.0.15 连接成功。
- scheduler 启动 `scheduler_tick` 与对应 cron，Redis 连接成功。
- 两个进程均在确认启动后通过 Ctrl+C 停止；人工中断不作为业务测试失败。

该冒烟只证明入口可导入、配置可加载、Redis 可连接，不证明存在业务异步任务。

## 2. 前端验证

### 安装

```powershell
cd frontend
npm ci
```

结果：成功，新增 161 个包，`found 0 vulnerabilities`。

### 测试

```powershell
npm test
```

结果：4 个测试文件、11 项测试通过，耗时约 3.03 秒。测试环境输出 `Window scrollTo()` 未实现警告，不影响测试通过。

覆盖方向：

- API client 的请求、错误和 Request ID 处理。
- 认证 store 的内存令牌与状态流转。
- 错误展示。
- 路由守卫。

这只是前端组件/逻辑测试；真实 `/auth/*` 联调仍未完成。

### 生产构建

```powershell
npm run build
```

结果：`vue-tsc -b && vite build` 成功，43 个模块转换完成。

生成文件示例：

- `dist/index.html`
- `dist/assets/index-*.css`
- `dist/assets/index-*.js`

## 3. 前后端代理冒烟

验证步骤：

1. 使用非生产测试数据库/Redis 启动 FastAPI：`127.0.0.1:8000`。
2. 启动 Vite 开发服务器：`127.0.0.1:5173`。
3. 请求前端代理路径 `/api/v1`。

```powershell
Invoke-WebRequest -UseBasicParsing -Uri 'http://127.0.0.1:5173/api/v1' -Headers @{'X-Request-ID'='docs-proxy-smoke'}
Invoke-WebRequest -UseBasicParsing -Uri 'http://127.0.0.1:8000/health/live'
```

结果：

- `/api/v1` 经 Vite 代理返回 `200`。
- 响应头保留 `X-Request-ID: docs-proxy-smoke`。
- `/health/live` 直接返回 `200`。
- 测试完成后两个开发进程均已关闭。

该冒烟只证明前端代理与基础 API 可达，不证明登录、业务 CRUD、SSE、AI 或公网部署可用。

## 4. CI 与容器运行验证

证据固定在：

- 代码提交：`a5bf49b038800003549b218278c146777dc2b096`
- 合并主线：`caa731cb2481a4aef50f3ff16f0d2fb811bcf9dc`
- GitHub Actions run：`39801657963`
- 结果：第 2 次尝试 5/5 作业通过；第 1 次失败是 Docker Hub 临时 `500`，不是配置回归。

| 作业 | 验证内容 | 结果 |
|---|---|---|
| Backend | 锁定依赖、Ruff lint/format、真实 PostgreSQL/Redis pytest | PASS |
| Frontend | `npm ci`、生产构建、Vitest | PASS |
| Quality | 校验器单测与质量清单结构校验 | PASS |
| Security | Gitleaks 全历史敏感信息扫描 | PASS |
| Compose | 干净构建、空库迁移、启动、健康、权限和 HTTP 验证 | PASS |

Compose 作业在 GitHub 托管的干净 Ubuntu runner 上验证：

- PostgreSQL、Redis、API、worker、scheduler、frontend 和 reverse proxy 七个常驻服务健康。
- 一次性 `migrate` 服务先于应用启动并完成 `alembic upgrade head`。
- 数据库 revision 为 `20261022_0001`，`system_metadata` 表存在。
- API、worker、scheduler、frontend 和 reverse proxy 的 UID 非 `0`，实测为 `10001`。
- 只有反向代理默认绑定 `127.0.0.1:8080`；PostgreSQL 与 Redis 不发布宿主端口。
- 反向代理 `/health/live`、`/health/ready`、`/api/v1` 通过，`/healthz` 与 `/` 返回成功。

本机 `docker` 实际指向 `wslc`，没有可用的 `docker compose`。因此以上是 CI 运行时证据，不是本机 Compose 实测；本地配置解析也不能替代运行验证。

## 5. 质量门禁现状

`tests/quality-baseline/acceptance-gates.json` 在本次文档基线前记录：

- 共 47 条门禁：13 PASS、3 CONDITIONAL、30 FAIL、1 NOT_RUN。
- Stage A 工程基线为 PASS。
- `S-FE-04` 仍为 CONDITIONAL，等待真实认证联调。
- 最终 MVP 为 `FAIL / NOT_READY`。

因此：

- 阶段基线测试通过不等于完整产品完成。
- 根 README/文档结构完成后，`F-DOC-01` 仍需 A30/A40 按最终验收标准更新。
- 不能把本地命令结果解释为 GHCR 发布、云部署、AI 或生产环境通过；容器/CI 只按第 4 节的固定 run 记录。

## 6. 尚未验证

| 项目 | 状态 | 后续条件 |
|---|---|---|
| GHCR release workflow 与三个发布镜像 | 未实际触发/未推送 | 创建版本 tag 或手动触发后回读镜像与权限 |
| 云服务器部署 | 未执行 | 独立 A40 部署任务 |
| 域名、TLS、公网入口 | 未配置 | 主机、DNS、证书和代理联合验证 |
| 生产备份恢复/回滚演练 | 未执行 | 获批的恢复任务与脱敏证据 |
| 真实认证与管理员隐私边界 | 未实现/待联调 | AUTH-INT-001 |
| 词书导入导出、FSRS、AI、教练、挑战 | 未实现 | 后续业务任务 |
| 评审账号与完整比赛演示 | 未交付 | 业务闭环和合成数据完成后再准备 |

## 7. 复测规则

1. 每次代码变化后重新运行受影响命令，不复制旧结果冒充当前通过。
2. 容器/CI 结论必须固定提交、Actions run 和结果；发布与云部署必须引用各自证据。
3. 提交文档前至少检查 `git diff --cached --check`、敏感信息和相对链接。
4. 记录测试环境，但不记录密码、API Key、生产连接串或真实成员数据。
