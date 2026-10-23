# AI 英语学习工具

面向学校、企业培训项目或学习组织内部成员的私有英语学习平台。产品把词书、FSRS 间隔复习、AI 练习、AI 教练、每日闯关和组织聚合看板整合为同一套真实学习闭环；首版不提供公开注册、陌生人社交或公开排行榜。

## 当前状态

本交付分支基于 T-QA-004 冻结提交 `efc6bcbd2679eca02613a7143c68d04dddc36a59`，当前是**可运行、可联调、可容器化的 M5 代码基线**。M5 代码内硬化结论为 `PASS_WITH_CONDITIONS`，完整 MVP 仍为 `FAIL / NOT_READY`，不得把本页面的能力清单解释为最终比赛验收通过。

| 范围 | 当前状态 | 证据 |
|---|---|---|
| 认证、成员管理、最后管理员保护 | 已实现并通过真实 PostgreSQL/Redis/API/浏览器验证 | `backend/tests/test_auth.py`、`test_admin_users.py`、T-QA-004 |
| 词书导入、导出、删除与持久任务 | 已实现；ARQ worker/scheduler 真实运行验证 | `backend/tests/test_wordbooks.py`、`test_wordbook_jobs.py` |
| 今日计划、FSRS 记忆训练、错词 | 已实现并通过真实浏览器闭环 | `backend/tests/test_learning_api.py`、`test_memory_api.py` |
| 四类 AI 练习、草稿、评分、记录、错题 | 已实现；受控 provider 与真实 worker 验证 | `backend/tests/test_practice_api.py`、T-QA-004 |
| AI provider、提示词、额度、失败重试 | 已实现；Key 加密、掩码、SSRF 拦截与额度账本验证 | `backend/tests/test_ai_admin.py`、`test_ai_jobs.py` |
| AI 教练 SSE、受控动作与 24h 撤销 | 已实现；真实 SSE 与 action receipt 验证 | `backend/tests/test_coach_api.py`、T-QA-004 |
| 每日闯关、共享进度、BOSS | 已实现；API 与浏览器条件链路验证 | `backend/tests/test_challenge_api.py`、T-QA-004 |
| 通知、DND、去重与 AI 例外 | 已实现；真实链路验证 | `backend/tests/test_notifications.py` |
| 管理员组织聚合看板与隐私边界 | 已实现；0/1/2/3 成员聚合与隐私测试通过 | `backend/tests/test_dashboard_api.py` |
| Docker Compose、CI、空库迁移、健康检查 | 已验证；Compose 七服务、非 root、回环端口与迁移通过 | T-SHIP-001、run `39801657963` |
| 生产部署、公网 URL、TLS、GHCR digest | **未验证**；T-SHIP-002 正在执行 | `docs/deployment.md`、`docs/fact-check.md` |
| 比赛视频、公网截图、最终提交清单 | 脚本、合成数据和 QA 截图已准备；最终录屏与公网入口待 T-SHIP-002 | `docs/competition/` |

> 事实规则：只有代码、测试、真实 API/浏览器、固定 CI run 或部署证据支持的能力才能标记为“已验证”。计划、占位值、QA 截图和容器构建不能冒充生产完成。

## 产品闭环

### 管理员

- 登录、首次改密、会话刷新与退出。
- 创建成员、CSV 批量导入、启停、重置密码、角色调整和最后管理员保护。
- 创建或导入组织词书，查看持久导入任务和结果。
- 配置 OpenAI 兼容 provider、提示词、连接检查、额度和备用顺序。
- 查看组织聚合学习指标，但不读取成员答题正文、草稿、私有词书正文或教练对话。

### 成员

- 登录、首次改密、学习档案与通知偏好。
- 选择主词书、导入个人词书。
- 获取今日新词和到期复习，完成翻卡、选择、拼写三类记忆训练。
- 完成填空、阅读、翻译、作文四类 AI 练习；支持草稿、提交、评分、记录、错题和删除。
- 使用 AI 教练读取合法上下文、接收 SSE 回复、执行受控动作并在 24 小时内撤销。
- 完成每日闯关、共享进度和终点 BOSS，接收站内通知并配置 DND。

## 技术架构

```text
Browser
  │
  ▼
Vue 3 / Vite / Pinia ── /api proxy ── FastAPI /api/v1
                                      │
                         ┌────────────┼────────────┐
                         ▼            ▼            ▼
                    PostgreSQL 16   Redis 7     ARQ worker
                    SQLAlchemy      queue /     scheduler
                    Alembic         cache       AI / import jobs
                         │
                         └── 私有词书卷（api/worker/scheduler 共享）
```

当前是模块化单体：身份、词书、学习、记忆、练习、AI、教练、挑战、通知和看板在同一后端应用中按领域拆分；Redis 负责队列与短期协调，PostgreSQL 是业务权威数据源。详细组件、请求链路和边界见 [架构文档](docs/architecture.md)。

## 快速启动

### Docker Compose（推荐验收路径）

需要 Docker Engine 与 Docker Compose v2。示例值只用于一次性本地/CI 环境；真实环境必须替换全部密钥。

```bash
cp .env.example .env
chmod 600 .env
# 编辑 .env，设置 POSTGRES_PASSWORD、JWT_SECRET、REFRESH_TOKEN_PEPPER、SECRET_ENCRYPTION_KEY 等
docker compose up --build -d
docker compose ps
```

Compose 会先运行一次性 `migrate` 服务执行 `alembic upgrade head`，再启动 API、worker、scheduler、frontend 和反向代理。默认只有反向代理绑定 `127.0.0.1:8080`，PostgreSQL、Redis 与内部服务不发布宿主端口。

创建首个管理员：

```bash
docker compose run --rm   -e BOOTSTRAP_ADMIN_USERNAME=admin   -e BOOTSTRAP_ADMIN_DISPLAY_NAME='Organization Administrator'   -e BOOTSTRAP_ADMIN_PASSWORD='<unique password from a secret channel>'   api python -m app.cli bootstrap-admin
```

然后按 [演示数据说明](docs/competition/demo-data.md) 初始化合成演示组织。演示密码不进入仓库，由运行者在环境变量中设置。

### 本地开发

后端需要 Python 3.12、`uv`、PostgreSQL 16 和 Redis 7：

```powershell
cd backend
uv sync --locked --all-groups
Copy-Item .env.example .env
# 编辑 .env；不要提交真实密钥
uv run alembic upgrade head
uv run uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

另开终端启动 worker 与 scheduler：

```powershell
cd backend
uv run arq app.workers.worker.WorkerSettings
uv run arq app.workers.scheduler.SchedulerSettings
```

前端需要 Node.js 24 与 npm 11：

```powershell
cd frontend
npm ci
npm run dev
```

开发地址：前端 `http://127.0.0.1:5173`，后端 `http://127.0.0.1:8000`。详细命令与未覆盖范围见 [测试文档](docs/testing.md)。

## 环境变量

根 `.env.example` 只包含占位值。关键变量：

| 变量 | 用途 |
|---|---|
| `POSTGRES_DB`、`POSTGRES_USER`、`POSTGRES_PASSWORD` | PostgreSQL 数据库与容器初始化 |
| `DATABASE_URL` | SQLAlchemy async PostgreSQL 连接串 |
| `REDIS_URL` | Redis 队列、会话与短期协调 |
| `JWT_SECRET` | Access Token 签名 |
| `REFRESH_TOKEN_PEPPER` | Refresh Token 哈希保护 |
| `SECRET_ENCRYPTION_KEY` | AI provider Key 服务端加密 |
| `CORS_ORIGINS` | 允许的前端 Origin |
| `WORDBOOK_STORAGE_DIR` | 私有词书文件卷路径 |
| `AI_ALLOW_PRIVATE_PROVIDER_URLS` | 是否允许受控测试环境的私有 provider 地址；生产默认关闭 |

真实密钥、生产连接串、成员数据和服务器接入资料不得提交到 Git。完整占位说明以根 `.env.example` 为准。

## 数据库与迁移

- 当前迁移 head：`844c0d89f737`。
- 当前有 46 张应用表（另含 Alembic `alembic_version`），覆盖身份、词书、学习、记忆、AI、练习、教练、通知、挑战、审计和系统元数据。
- 本地迁移：

```powershell
cd backend
uv run alembic upgrade head
uv run alembic check
```

- 容器空库迁移由 Compose 一次性 `migrate` 服务完成；T-QA-004 已完成空库 upgrade/downgrade/re-upgrade 验证。
- 迁移回滚与备份恢复的边界见 [部署文档](docs/deployment.md)。

## 测试与质量

```powershell
# 后端
cd backend
uv sync --locked --all-groups
uv run ruff check .
uv run ruff format --check .
uv run pytest

# 前端
cd frontend
npm ci
npm test
npm run build
```

T-QA-004 的冻结结果：后端 156 passed、前端 310 passed、M3 API 54/54、M3 浏览器 13/13、M4R API 21/21、M4R 浏览器 14/14；47 个门禁为 40 PASS / 3 CONDITIONAL / 4 FAIL / 0 NOT_RUN。当前交付新增的演示数据脚本在一次性独立数据库中首次初始化与重复初始化均通过，真实 API 读取 13 项全部返回 200。

完整证据、环境、性能原始值和未验证项见 [测试文档](docs/testing.md) 与 [事实核对](docs/fact-check.md)。

## API 与 OpenAPI

- API 前缀：`/api/v1`
- OpenAPI JSON：`http://127.0.0.1:8000/api/v1/openapi.json`
- Swagger UI：`http://127.0.0.1:8000/api/v1/docs`
- 当前 OpenAPI：84 个路径、153 个 schema
- 认证：短时 Access Token + HttpOnly Refresh Cookie + CSRF 双提交
- 异步：词书任务、AI 任务和部分练习评分使用 `202` + 持久任务状态查询
- 流式：AI 教练使用 SSE，断线后可按事件序号恢复

接口分组、错误结构、分页、SSE 和“202 不是成功”的边界见 [API 文档](docs/api.md)。

## 安全与隐私

- 密码使用 Argon2id；Refresh Token 数据库只存哈希并轮换。
- Access Token 仅保存在前端内存，不使用 localStorage/sessionStorage 保存业务真相。
- Cookie 写请求校验 Origin 与 CSRF；最后管理员不可删除、停用或降级。
- AI provider Key 服务端加密保存，接口只返回掩码；Base URL 阻止云元数据地址和非法内网访问。
- 管理员看板只展示聚合指标，不返回成员答题正文、草稿、教练对话或私有词书正文。
- 容器应用以 UID/GID `10001` 非 root 运行，启用只读根文件系统、`cap_drop: ALL` 与 `no-new-privileges`。
- 当前仍未完成 CSP、生产备份审批/RPO/RTO、生产恢复演练和公网 TLS 验证。

详见 [安全与隐私](docs/security-privacy.md)。

## 演示与比赛材料

- [演示数据与账号说明](docs/competition/demo-data.md)
- [可执行合成数据脚本](docs/competition/seed_demo_data.py)
- [演示截图与事实清单](docs/competition/screenshots/README.md)
- [技术文档正文](docs/competition/technical-document.md)
- [5–8 分钟视频脚本](docs/competition/demo-video-script.md)
- [最终提交清单](docs/competition/submission-checklist.md)
- [来源、许可证与素材边界](docs/competition/licensing.md)

比赛最终视频、公网 URL、镜像 digest 和评审账号必须等待 T-SHIP-002 的固定证据；未完成项在材料中保留 `TODO`，不写成已完成。

## GitHub、CI 与发布

- 仓库：`ticaxox/english-learn-tool`（Private）。
- `main` 只由 A01 SYNC 协调合并；执行 Agent 使用独立分支和 PR。
- CI 覆盖后端、前端、质量清单、敏感信息扫描和 Compose 集成五类作业。
- 发布工作流会构建 API、frontend 与 reverse-proxy 三个 GHCR 镜像，并要求完整 Git SHA/不可变 tag。
- 当前版本标签、GHCR 实际推送、digest 与生产拉取仍未验证。

## 已知限制

1. **部署未完成**：T-SHIP-002 正在执行，公网 URL、TLS、镜像 digest、备份恢复和回滚尚未冻结。
2. **CSP 未配置**：安全头部分通过，但 `F-SEC-01` 仍为 CONDITIONAL。
3. **生产备份未验收**：合成库恢复通过，但生产 RPO/RTO 与 A40 演练未完成。
4. **Today 页面 AI 摘要仍是旧字段**：后端 `GET /learning/today` 的 `ai_practice` 目前仍返回 `not_available`；已实现的四类 AI 练习从 `/practice` 使用，不能把 Today 摘要当作 AI 练习未实现。
5. **最终 MVP 未验收**：47 门禁仍有 3 CONDITIONAL、4 FAIL；完整 MVP 为 `FAIL / NOT_READY`。
6. **许可证未决定**：仓库未添加开源许可证，公开提交前需 A00 决策；见 [licensing](docs/competition/licensing.md)。

## 文档导航

- [文档索引](docs/README.md)
- [架构](docs/architecture.md)
- [数据模型](docs/data-model.md)
- [API](docs/api.md)
- [AI 链路](docs/ai-pipeline.md)
- [安全与隐私](docs/security-privacy.md)
- [测试](docs/testing.md)
- [部署](docs/deployment.md)
- [演示](docs/demo.md)
- [事实核对](docs/fact-check.md)

## 贡献

开发、测试、分支、PR 和敏感信息边界见 [CONTRIBUTING.md](CONTRIBUTING.md)。正式任务由 A01 SYNC 派发；执行 Agent 必须核对角色、`thread_id`、分支和工作树登记。
