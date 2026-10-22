# 架构与当前边界

- 事实基线：`caa731c`；容器/CI 代码与运行证据对应 `a5bf49b` / run `39801657963`
- 当前形态：模块化单仓工程骨架
- 完整目标形态：以受控的 v1.1 产品基线为准，不属于当前已实现范围；本仓库不复制内部工作区资料

## 1. 当前可运行架构

```text
┌──────────────┐      /api proxy       ┌────────────────────────┐
│ Browser /    │ ────────────────────▶ │ FastAPI                │
│ Vue 3 + Vite │                       │ ├── /health/*          │
└──────────────┘                       │ └── /api/v1            │
                                       └───────┬───────┬────────┘
                                               │       │
                                     PostgreSQL 16   Redis 7
                                     SQLAlchemy      readiness only
                                               │
                                      ARQ worker / scheduler
                                      heartbeat entrypoints only
```

### 已实现组件

| 组件 | 位置 | 当前职责 |
|---|---|---|
| FastAPI 应用 | `backend/app/main.py` | 构建应用、注册中间件和路由、管理数据库/Redis 生命周期 |
| 配置 | `backend/app/core/config.py` | 环境变量校验、URL/时区/CORS/密钥长度检查 |
| 错误处理 | `backend/app/core/errors.py` | `code/message/details/request_id` 统一错误响应 |
| 请求上下文 | `backend/app/core/middleware.py` | 校验或生成 Request ID；输出结构化访问日志 |
| 健康检查 | `backend/app/api/health.py` | 存活检查、PostgreSQL/Redis/配置就绪检查 |
| 数据库基础 | `backend/app/db/` | SQLAlchemy 2.x async engine/session factory |
| 迁移 | `backend/alembic/` | 当前建立 `system_metadata` |
| ARQ 入口 | `backend/app/workers/` | worker/scheduler 心跳，不包含业务任务 |
| 前端壳层 | `frontend/src/` | Vue 路由、真实 API client、认证状态骨架、错误展示 |
| Vite 代理 | `frontend/vite.config.ts` | 开发/预览时把 `/api` 转发到后端 |
| Compose 运行拓扑 | `docker-compose.yml` | PostgreSQL、Redis、一次性迁移、API、worker、scheduler、frontend、反向代理 |
| CI | `.github/workflows/ci.yml` | 后端、前端、质量清单、敏感信息扫描和 Compose 集成五类作业 |
| 发布与部署资产 | `.github/workflows/release.yml`、`deploy/**` | GHCR 三镜像工作流、生产覆盖、验证、备份、部署和回滚脚本 |

### 尚未实现

- 后端 `/auth/*`、成员管理、词书、FSRS、练习、教练、通知和挑战 API。
- 数据库业务表、FSRS 服务、AI provider、额度账本和受控 action。
- SSE 流、AI 结构化生成/校验/评分链路。
- 完整业务页面、真实演示数据和评审账号。
- GHCR 发布实跑、云服务器部署、域名/TLS、公网入口和生产恢复演练。

## 2. 目标模块边界

目标产品采用模块化单体，而不是微服务：

| 模块 | 目标职责 | 当前状态 |
|---|---|---|
| `auth` | 登录、JWT、Refresh Token、改密、CSRF、限流 | 规划中；前端有契约骨架，后端未实现 |
| `users` | 成员、角色、状态、最后管理员保护、删除协调 | 规划中 |
| `profiles` | 学习档案、通知偏好、每日目标 | 规划中 |
| `wordbooks` / `imports` / `exports` | 词书、导入预览、事务导入、导出 | 规划中 |
| `memory` / `plans` | FSRS、会话、事件、每日计划快照 | 规划中 |
| `practice` | 四类 AI 练习、草稿、判分、记录、错题 | 规划中 |
| `ai` | provider、提示词、校验、额度、异步任务 | 规划中 |
| `coach` | 长对话、SSE、上下文、受控 action、撤销 | 规划中 |
| `challenges` | 每日地图编排、节点状态、终点挑战 | 规划中 |
| `notifications` | 站内通知、偏好、免打扰、去重 | 规划中 |
| `observability` | Request ID、日志、指标、审计 | 基线 Request ID/日志已实现；指标待后续 |

## 3. 关键决策边界

### FSRS 与 AI 分离

- FSRS 是复习时间的唯一决策者，保存 Card 状态、到期时间、算法版本。
- AI 只能读取已计算的合法任务上下文，负责组合、排序、文案和练习参数。
- AI 不得减少每日新词量、虚构词条、修改 `due_at` 或越过权限直接写数据库。

### 传统模式与每日闯关共享进度

- 今日任务快照由后端生成，传统模式和闯关地图读取同一份计划。
- 完成传统学习任务后，闯关节点通过领域事件、事务或可靠补偿同步。
- 闯关地图不是第二套学习量，失败时不得生成确定性替代地图。

### AI 失败不伪造成功

- 题目、评分、教练动作和挑战地图均要求结构化 JSON 与业务校验。
- 非法 JSON 最多修复 1 次；逻辑不合法时重新生成，总尝试最多 3 次。
- 最终失败返回明确错误态，不保存半成品、不扣逻辑额度。
- 生产路径不得使用静态题目或假 AI 兜底。

## 4. 前端边界

当前前端是真实 API 接入的骨架，不是完整产品：

- 已有路由、角色守卫、改密拦截、API client、错误状态和真实网络调用入口。
- 业务页面目前只读取真实 GET 端点或显示真实错误；完整表单、题目、SSE 对话和地图交互未实现。
- Access Token 只保存在内存，不使用 `localStorage`/`sessionStorage` 保存业务真相。
- 前端路由守卫只改善体验，授权必须在后端服务层执行。

## 5. 部署边界

仓库已包含 Dockerfile、`docker-compose.yml`、根级 `.env.example`、CI/GHCR 工作流和部署脚本。当前边界如下：

- `a5bf49b` 对应的 Actions run `39801657963` 第 2 次尝试 5/5 作业通过。
- Compose 在 GitHub 托管 runner 上从空库迁移到 `20261022_0001`，七个常驻服务健康；应用容器以 UID/GID `10001` 非 root 运行，默认只有反向代理绑定 `127.0.0.1:8080`。
- 本机没有可用 Docker Compose，因此本地只验证进程方式；容器运行时证据来自 CI，不冒充本机实测。
- GHCR release workflow 尚未实际触发，三个发布镜像尚未推送；没有云服务器部署、域名、TLS 或公网入口。
- 备份、部署和回滚脚本存在，但未执行生产恢复演练；应用回滚不自动反向迁移数据库。
- 当前服务器容量不足以直接部署完整栈，正式部署必须另立任务。

## 6. 架构变更规则

1. 新增跨模块依赖必须说明事务边界和失败补偿。
2. PostgreSQL 是业务权威数据源；Redis 不能保存唯一业务真相。
3. 任何 API 契约变更必须同步 OpenAPI、前端 client、测试和文档。
4. 任何数据库变化必须提供 Alembic migration 与 downgrade。
5. 不允许为了演示绕过 AI、FSRS、权限或幂等约束。
