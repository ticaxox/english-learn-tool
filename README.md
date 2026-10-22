# AI 英语学习工具

面向学校、企业培训项目或学习组织内部成员的私有英语学习平台。产品目标是以后端能力为核心，将词书、FSRS 间隔复习、AI 练习、AI 教练和每日学习编排整合为同一套真实学习闭环；首版不提供公开注册、陌生人社交或公开排行榜。

## 当前状态

本仓库当前主线技术基线为 `caa731c`（PR #4 合并提交），容器与 CI 实现对应提交为 `a5bf49b`。当前交付是**可运行的工程骨架与已通过的容器/CI 基础**，不是完整可用产品，也不代表比赛 MVP 已完成。

| 范围 | 当前状态 | 证据 |
|---|---|---|
| FastAPI 应用、统一错误与 Request ID | 已实现并通过测试 | `backend/tests/` |
| PostgreSQL/Alembic 基线 | 本地迁移、漂移检查与容器空库迁移均通过 | `docs/testing.md`、`docs/deployment.md` |
| Redis 就绪检查、ARQ 基础设施入口 | 已实现并通过测试 | `backend/app/workers/` |
| Vue 3/Vite/TypeScript 应用壳层 | 已实现；连接真实 API，不使用业务 mock | `frontend/` |
| 登录、改密、路由守卫骨架 | 前端逻辑已实现；真实认证接口尚未由后端提供 | `frontend/README.md` |
| 词书、FSRS、AI 练习、AI 教练、每日闯关 | **未实现**；仅有产品蓝图与文档结构 | `docs/architecture.md` |
| Docker、Compose、CI、容器迁移与健康检查 | GitHub Actions run `39801657963` 第 2 次尝试 5/5 作业通过；Compose 7 个常驻服务健康 | `docs/testing.md`、`docs/deployment.md` |
| GHCR 发布、公网部署、TLS、评审账号 | **未交付/未验证**；发布工作流尚未实际触发 | `docs/deployment.md` |
| 比赛技术文档正文、演示视频 | **未交付**；仅保留结构 | `docs/competition/` |

> 状态规则：代码与命令结果可以标记为“已验证”，但容器/CI 结论必须同时注明固定提交和 Actions run；GHCR 发布、云服务器部署、域名、TLS 与生产恢复必须各自取得证据，不能由容器构建通过推导。产品蓝图中的后续能力统一标记为“规划中”。

## 产品边界

- 一个部署实例服务一个组织；成员由组织管理员创建或批量导入，不开放自助注册。
- 角色为 `admin` 和 `member`。管理员可以查看聚合学习指标，但不得读取成员答题正文、未提交草稿或 AI 教练对话。
- FSRS 负责复习时间和卡片状态；AI 负责练习生成、评分、讲解和合法任务编排，不得修改 FSRS `due_at`。
- AI 失败时显示真实失败态与重试入口，不使用静态假题、假评分或伪造地图兜底。
- 代码、Git 历史、截图、视频和日志中不得出现真实密钥、真实成员数据或生产连接串。

## 基线架构

```text
Browser
   │
   ▼
Vue 3 / Vite ── /api proxy ── FastAPI /api/v1
                                   │
                                   ├── PostgreSQL 16（业务权威数据源；当前仅 system_metadata）
                                   ├── Redis 7（就绪检查与后续队列基础设施）
                                   └── ARQ worker / scheduler（当前仅心跳入口）
```

这是当前代码的工程骨架。规划中的认证、词书、FSRS、练习、教练和挑战模块尚未接入，不得把图中的未来模块当作已实现能力。

## 目录

```text
english-learn-tool/
├── AGENTS.md                 # 仓库协作与路径边界
├── .env.example              # Compose/CI 非敏感占位配置
├── docker-compose.yml        # PostgreSQL、Redis、迁移与五个应用服务
├── .github/workflows/        # CI 与 GHCR 发布工作流
├── deploy/                   # 镜像、生产覆盖、验证、备份和回滚脚本
├── backend/
│   ├── app/
│   │   ├── api/              # 健康检查与 /api/v1 入口
│   │   ├── core/             # 配置、错误、日志、请求上下文
│   │   ├── db/               # SQLAlchemy async 基础设施
│   │   ├── models/           # 当前为 system_metadata
│   │   ├── services/         # 健康检查服务
│   │   └── workers/          # ARQ worker/scheduler 入口
│   ├── alembic/              # 数据库迁移
│   ├── tests/                # 后端单元/集成测试
│   └── pyproject.toml
├── frontend/
│   ├── src/api/              # 真实 HTTP client 与契约
│   ├── src/router/           # 路由和角色守卫骨架
│   ├── src/stores/           # Pinia 认证状态骨架
│   ├── src/views/            # 登录、改密、远程数据空壳页
│   └── package.json
├── tests/quality-baseline/   # 阶段验收门禁清单
└── docs/                     # 架构、接口、测试、部署和比赛材料结构
```

## 前置环境

本地验证使用：

- Python 3.12（`uv` 解析并运行 Python 3.12）
- `uv`
- Node.js 20.19+；本次验证使用 Node.js 24.18.0
- npm 10+；本次验证使用 npm 11.16.0
- PostgreSQL 16
- Redis 7
- Docker Engine + Docker Compose v2（仅容器路径；本机当前没有可用 Compose）

后端测试使用真实 PostgreSQL 和专用 Redis 数据库，不提供内存数据库降级。若 PostgreSQL 或 Redis 不可用，集成测试会失败而不是静默跳过。容器运行证据来自 GitHub Actions，不能以本机配置解析代替。

## 本地启动

### 1. 后端

在 `backend` 目录执行：

```powershell
uv sync --locked --all-groups
uv run alembic upgrade head
uv run uvicorn app.main:app --host 127.0.0.1 --port 8000
```

启动前需要：

1. 在 PostgreSQL 中准备开发数据库，在 Redis 中准备可访问实例。
2. 以 `backend/.env.example` 为模板创建本地 `.env`；该文件不提交到 Git。
3. 替换所有示例连接串和密钥。`JWT_SECRET`、`REFRESH_TOKEN_PEPPER`、`SECRET_ENCRYPTION_KEY` 均至少 32 个字符。
4. 确认 `DATABASE_URL` 使用 `postgresql+asyncpg://`，`REDIS_URL` 使用 `redis://` 或 `rediss://`。

当前后端可访问入口：

- `GET http://127.0.0.1:8000/health/live`
- `GET http://127.0.0.1:8000/health/ready`
- `GET http://127.0.0.1:8000/api/v1`
- Swagger UI：`http://127.0.0.1:8000/api/v1/docs`
- OpenAPI：`http://127.0.0.1:8000/api/v1/openapi.json`

### 2. 前端

在 `frontend` 目录执行：

```powershell
npm ci
npm run dev
```

默认入口为 `http://127.0.0.1:5173`。开发服务器会把 `/api` 代理到 `http://127.0.0.1:8000`；如需切换后端地址，以 `frontend/.env.example` 为模板配置 `VITE_API_BASE_URL` 和 `VITE_API_PROXY_TARGET`。

当前基线没有可用的评审账号、合成业务数据或真实登录后端。登录页与业务空壳页可以启动，但完整业务演示要等待后续认证和数据任务。

## 已验证命令

以下应用层命令已在 `caa731c` 的文档工作树复跑；后端测试使用一次性独立 PostgreSQL 数据库，避免共享测试库中的其他分支迁移干扰。容器/CI 运行证据固定引用 `a5bf49b` 与 Actions run `39801657963`。

| 范围 | 命令 | 结果 |
|---|---|---|
| 后端安装 | `uv sync --locked --all-groups` | 成功 |
| 后端静态检查 | `uv run ruff check .` | `All checks passed!` |
| 后端格式检查 | `uv run ruff format --check .` | `38 files already formatted` |
| 后端测试 | `uv run pytest` | `18 passed`（独立 PostgreSQL） |
| 本地迁移 | `uv run alembic upgrade head` | 成功（独立空库） |
| 迁移漂移检查 | `uv run alembic check` | `No new upgrade operations detected.` |
| 前端安装 | `npm ci` | 成功，0 vulnerabilities |
| 前端测试 | `npm test` | 4 个测试文件、11 项测试通过 |
| 前端生产构建 | `npm run build` | 成功，43 个模块 |
| 前端代理冒烟 | 请求 `http://127.0.0.1:5173/api/v1` | `200`，返回真实后端服务元数据 |
| 后端存活检查 | 请求 `http://127.0.0.1:8000/health/live` | `200` |
| ARQ worker 入口 | `uv run arq app.workers.worker.WorkerSettings` | 启动 `worker_heartbeat` 成功，随后停止 |
| ARQ scheduler 入口 | `uv run arq app.workers.scheduler.SchedulerSettings` | 启动 `scheduler_tick`/cron 成功，随后停止 |

容器与 CI 证据：在 `a5bf49b` 上，GitHub Actions run `39801657963` 第 2 次尝试 5/5 作业通过，Compose 完成空库迁移、七个常驻服务健康检查、非 root 检查、仅反向代理绑定回环端口，以及 `/health/live`、`/health/ready`、`/api/v1` 路由验证。详细环境、测试数据和未验证项见 `docs/testing.md`、`docs/deployment.md` 与 `docs/fact-check.md`。

## 数据库迁移

当前迁移 revision 为 `20261022_0001`，仅建立 `system_metadata` 基线表。新增模型必须同时提供 Alembic migration、降级路径和变更说明。

```powershell
cd backend
uv run alembic upgrade head
uv run alembic check
```

规划中的业务表、约束和 API 以产品基线文档为准，不代表当前数据库已经包含这些表。

## 测试与质量

```powershell
# backend
cd backend
uv run ruff check .
uv run ruff format --check .
uv run pytest

# frontend
cd ../frontend
npm test
npm run build
```

后端测试默认指向 `english_learn_test` 和 Redis DB `15`，可通过 `TEST_DATABASE_URL`、`TEST_REDIS_URL` 覆盖；必须使用非生产资源。当前 `tests/quality-baseline` 中的最终门禁仍为 `FAIL / NOT_READY`，阶段门禁通过不能替代最终 MVP 验收。

## 文档入口

- [文档索引](docs/README.md)
- [架构与当前边界](docs/architecture.md)
- [数据模型](docs/data-model.md)
- [API](docs/api.md)
- [AI 链路（规划）](docs/ai-pipeline.md)
- [安全与隐私](docs/security-privacy.md)
- [测试与验证记录](docs/testing.md)
- [部署与运行](docs/deployment.md)
- [演示结构](docs/demo.md)
- [事实核对清单](docs/fact-check.md)

## 部署、CI 与比赛状态

当前仓库已包含根级 `.env.example`、`docker-compose.yml`、Dockerfile、CI、GHCR 发布工作流及部署/备份/回滚脚本。可确认的事实是：

- `a5bf49b` 对应的 GitHub Actions run `39801657963` 第 2 次尝试 5/5 作业通过；Compose 在干净 runner 上从空库完成迁移并验证七个常驻服务健康。
- 应用容器以 UID/GID `10001` 非 root 运行；默认只有反向代理绑定 `127.0.0.1:8080`，PostgreSQL、Redis 与应用内部端口不发布到宿主。
- 本机没有可用 Docker Compose，因此未把本地配置解析写成容器运行证据。
- GHCR 发布工作流尚未实际触发，三个发布镜像尚未推送；未部署云服务器，未配置域名、TLS 或公网入口。
- 现有服务器约 1 vCPU / 1 GiB，不适合直接部署完整栈；备份和回滚脚本已存在但未执行生产恢复演练。
- `tests/quality-baseline` 的最终 MVP 状态仍为 `FAIL / NOT_READY`；阶段 CI 通过不能替代完整产品验收。

## 协作与安全

- 开发前阅读 `AGENTS.md` 和对应任务文档；未经 SYNC 登记不得创建交付分支或写入仓库。
- 功能分支、PR、分段提交和版本标签是正式交付要求；`main` 由 SYNC 协调合入。
- 不提交 `.env`、API Key、密码、私钥、数据库备份、日志或真实成员数据。
- 文档必须先在代码或可复现命令中找到证据；无法验证的内容标注“规划中”或“待验证”。

详细协作规则见 [CONTRIBUTING.md](CONTRIBUTING.md)，版本记录见 [CHANGELOG.md](CHANGELOG.md)。
