# 文档与代码事实核对清单

- 核对基线：`c3b2a50`
- 核对日期：2026-10-22
- 用途：防止把产品蓝图、前端预留契约或阶段结果误写成已交付能力

## 1. 当前事实映射

| 文档陈述 | 代码/命令证据 | 状态 |
|---|---|---|
| FastAPI 应用存在 | `backend/app/main.py` | 已验证 |
| `/health/live`、`/health/ready` | `backend/app/api/health.py`、`backend/app/services/health.py` | 已验证 |
| `/api/v1` 服务元数据 | `backend/app/api/v1/router.py`；本机请求返回 200 | 已验证 |
| Request ID 与统一错误结构 | `backend/app/core/middleware.py`、`errors.py`、相关测试 | 已验证 |
| PostgreSQL/Alembic 基线 | `backend/alembic/versions/20261022_0001_initial.py`；本地 upgrade/check | 已验证 |
| `system_metadata` 是当前唯一的非业务基线表 | migration 与 `backend/app/models/system.py` | 已验证 |
| Redis readiness | `backend/app/services/health.py`、后端测试 | 已验证 |
| ARQ worker/scheduler 心跳入口 | `backend/app/workers/worker.py`、`scheduler.py`、测试与启动冒烟 | 已验证 |
| Vue/Vite 壳层 | `frontend/src/`、`frontend/package.json` | 已验证 |
| Vite `/api` 代理 | `frontend/vite.config.ts`；本机代理冒烟返回 200 | 已验证 |
| 前端认证状态/路由守卫逻辑 | `frontend/src/stores/auth.ts`、`router/index.ts`、前端测试 | 已实现，真实后端未联调 |
| 后端认证接口 | 当前 `backend/app/api/v1/router.py` 无 auth 子路由 | 未实现 |
| Dockerfile/Compose/CI | 当前文件列表不存在对应文件 | 待 T-SHIP 验证 |
| 词书/FSRS/AI/教练/挑战 | 当前后端只有基础 service 与 worker 心跳，无领域模型/API | 未实现 |

## 2. 命令证据

### 后端

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
- Alembic：upgrade 成功，drift check 无新迁移。

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

## 3. 不可升级的事项

以下内容目前不得从“规划中”改为“已实现”：

- 用户登录、Refresh Token、改密、CSRF、限流。
- 管理员创建成员、组织聚合看板。
- 词书导入导出、FSRS 复习、今日计划。
- AI provider、提示词、题目生成、评分、额度。
- AI 教练 SSE、受控 action、撤销回执。
- 每日闯关、节点同步、终点挑战。
- 真实数据库业务表、容器迁移、CI、公网演示。

## 4. 仍需确认的冲突

| 项目 | 当前差异 | 处理 |
|---|---|---|
| 前端登录契约与后端实现 | 前端预留 `/auth/*`；后端没有对应路由 | 继续标记“待联调”，由 AUTH-INT-001 解决 |
| 产品质量门禁与当前阶段 | 质量清单最终 MVP 为 FAIL/NOT_READY | 保留 FAIL，不按阶段结果改成最终通过 |
| 部署文件 | 产品规划要求 Docker/CI；仓库当前无文件 | 统一标记“待 T-SHIP 验证” |
| 根级 `.env.example` | 产品要求；当前只有 backend/frontend 局部示例 | 由后续部署/文档任务确认，不在本任务越权创建 |
| 数据表说明 | 产品蓝图列出大量目标表；当前 migration 仅有 `system_metadata` | 文内均加“规划中”标签 |

## 5. 后续更新触发条件

出现以下任一变化时更新本清单：

- 新 API、表、worker 任务或前端路由落地。
- CI/Compose/部署文件出现并产生可验证证据。
- 真实认证或 AI 联调完成。
- A30 更新质量门禁状态。
- A00/A01 改变产品范围或交付优先级。

更新时必须记录提交 SHA、日期、执行命令、结果和未覆盖范围。
