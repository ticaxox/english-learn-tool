# 文档与代码事实核对清单

- 当前主线核对基线：`caa731cb2481a4aef50f3ff16f0d2fb811bcf9dc`
- 容器/CI 核对基线：`a5bf49b038800003549b218278c146777dc2b096`
- GitHub Actions run：`39801657963`（第 2 次尝试，5/5 作业通过）
- 核对日期：2026-10-22
- 用途：防止把产品蓝图、前端预留契约、阶段结果或 CI 通过误写成完整交付

## 1. 当前事实映射

| 文档陈述 | 代码/命令证据 | 状态 |
|---|---|---|
| FastAPI 应用存在 | `backend/app/main.py` | 已验证 |
| `/health/live`、`/health/ready` | `backend/app/api/health.py`、`backend/app/services/health.py` | 已验证 |
| `/api/v1` 服务元数据 | `backend/app/api/v1/router.py`；本机与 Compose 代理请求返回 200 | 已验证 |
| Request ID 与统一错误结构 | `backend/app/core/middleware.py`、`errors.py`、相关测试 | 已验证 |
| PostgreSQL/Alembic 基线 | `backend/alembic/versions/20261022_0001_initial.py`；本地与 CI 空库迁移 | 已验证 |
| `system_metadata` 是当前唯一的非业务基线表 | migration、ORM 与 CI 数据库检查 | 已验证 |
| Redis readiness | `backend/app/services/health.py`、后端与 Compose 测试 | 已验证 |
| ARQ worker/scheduler 心跳入口 | `backend/app/workers/worker.py`、`scheduler.py`、测试与 Compose 健康 | 已验证 |
| Vue/Vite 壳层 | `frontend/src/`、`frontend/package.json` | 已验证 |
| Vite `/api` 代理 | `frontend/vite.config.ts`；本机代理冒烟返回 200 | 已验证 |
| 前端认证状态/路由守卫逻辑 | `frontend/src/stores/auth.ts`、`router/index.ts`、前端测试 | 已实现，真实后端未联调 |
| 后端认证接口 | 当前 `backend/app/api/v1/router.py` 无 auth 子路由 | 未实现 |
| Dockerfile、Compose 与 CI | 根配置、`.github/workflows/ci.yml`、run `39801657963` | 已验证（仅该 run） |
| 空库容器迁移 | Compose `migrate` 作业、`verify-database.sh` | 已验证 |
| 容器非 root、回环端口与代理健康 | `docker-compose.yml`、`verify-stack.sh`、Actions 日志 | 已验证 |
| GHCR 发布工作流 | `.github/workflows/release.yml` | 文件存在；**未运行** |
| 部署、备份与回滚脚本 | `deploy/scripts/**` | 文件存在并审查；**未生产演练** |
| 根级 `.env.example` | 根目录 | 已验证为占位配置 |
| 云服务器、域名、TLS、公网入口 | 无部署任务证据 | 未部署 |
| 词书/FSRS/AI/教练/挑战 | 当前后端无领域模型/API | 未实现 |

## 2. 本地命令证据

### 后端

在 `caa731c` 文档工作树执行，测试使用一次性独立 PostgreSQL 数据库：

```powershell
cd backend
uv sync --locked --all-groups
uv run ruff check .
uv run ruff format --check .
uv run pytest
uv run alembic upgrade head
uv run alembic check
```

结果：

- Ruff lint：通过。
- Ruff format：38 files already formatted。
- pytest：18 passed。
- Alembic：空库升级到 `20261022_0001` 成功，drift check 无新迁移。

### 前端

```powershell
cd frontend
npm ci
npm test
npm run build
```

结果：

- npm ci：0 vulnerabilities。
- Vitest：4 个测试文件、11 项通过。
- Build：成功，43 个模块。

### 代理

```powershell
Invoke-WebRequest -UseBasicParsing -Uri 'http://127.0.0.1:5173/api/v1' -Headers @{'X-Request-ID'='docs-proxy-smoke'}
```

结果：HTTP 200；响应头保留 Request ID。该证据只覆盖代理和基础元数据。

## 3. CI 与容器证据

在 `a5bf49b` 的 GitHub Actions run `39801657963` 第 2 次尝试中：

- Backend、Frontend、Quality、Security、Compose 五个作业全部 PASS。
- Compose 在干净 runner 上构建镜像并从空库迁移。
- 七个常驻服务健康；非 root UID 为 `10001`。
- 只有反向代理默认绑定 `127.0.0.1:8080`。
- `/health/live`、`/health/ready`、`/api/v1` 通过。
- revision 为 `20261022_0001`，`system_metadata` 存在。
- Gitleaks 完整历史扫描未发现已提交密钥。

本机没有可用 Compose，故不得写成“本机 Compose 已运行”。第 1 次 Actions 失败来自 Docker Hub 临时 `500`，不能据此声明配置回归。

## 4. 不可升级的事项

以下内容目前不得从“规划中/未验证”改为“已实现/已部署”：

- GHCR 三个发布镜像已推送、可拉取或已有 digest。
- 云服务器部署、域名、TLS、公网入口和评审账号。
- 生产备份恢复、灾备或回滚演练。
- 用户登录、Refresh Token、改密、CSRF、限流。
- 管理员创建成员、组织聚合看板。
- 词书导入导出、FSRS 复习、今日计划。
- AI provider、提示词、题目生成、评分、额度。
- AI 教练 SSE、受控 action、撤销回执。
- 每日闯关、节点同步、终点挑战。
- 完整 MVP 已验收；当前质量清单仍为 `FAIL / NOT_READY`。

## 5. 仍需确认的差异

| 项目 | 当前差异 | 处理 |
|---|---|---|
| 前端登录契约与后端实现 | 前端预留 `/auth/*`；后端没有对应路由 | 继续标记“待联调”，由 AUTH-INT-001 解决 |
| 本地与 CI 容器环境 | 本机无 Compose；CI 已运行通过 | 只引用 CI 运行事实，不写成本机实测 |
| GHCR 发布 | workflow 存在但未触发 | 保持“未运行”，不得根据静态 YAML 宣称镜像已发布 |
| 云部署 | 服务器容量与现有服务条件未解决 | 必须另立部署任务，不得复制接入信息进仓库 |
| 备份回滚 | 脚本存在但未执行生产恢复 | 记录为工程资产，不记为恢复能力已验证 |
| 产品质量门禁 | 最终 MVP 为 FAIL/NOT_READY | 保留 FAIL，不因 CI Compose 通过而改成完整产品通过 |
| 数据表说明 | 产品蓝图列出大量目标表；当前只有 `system_metadata` | 文内均加“规划中”标签 |

## 6. 后续更新触发条件

出现以下任一变化时更新本清单：

- 新 API、表、worker 任务、前端路由或真实业务联调落地。
- GHCR release workflow 实际运行并产生可回读镜像和 digest。
- 云服务器、域名、TLS、公网入口或生产恢复演练完成。
- A30 更新质量门禁状态。
- A00/A01 改变产品范围或交付优先级。

更新时必须记录提交 SHA、Actions run（如适用）、日期、执行命令、结果和未覆盖范围。
