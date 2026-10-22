# 贡献指南

本项目采用单组织私有部署、后端优先和可追溯 Git 协作方式。本文只描述当前仓库可以执行的协作规则；产品能力以已确认任务文档为准。

## 1. 开始前

1. 阅读根目录 `AGENTS.md`、工作区规则和当前任务卡。
2. 确认任务执行方、稳定 `thread_id`、分支所有者、工作树和允许写入路径均已登记。
3. 在独立工作树中工作；不得直接写入 `main`，不得使用其他 Agent 的工作树。
4. 如果任务、注册表或代码事实冲突，先返回 `BLOCKED`，不要自行扩大范围。

## 2. 角色与路径

| 路径 | 主要责任方 |
|---|---|
| `backend/**` | A10 CORE｜后端 |
| `frontend/**` | A20 VIEW｜前端；素材另由 A21 ARTS｜素材交付 |
| `.github/**`、`deploy/**`、容器配置 | A40 SHIP｜部署 |
| `tests/**`、质量证据和审查记录 | A30 TEST｜质量 |
| `docs/**`、根 `README.md` | A50 DOCS｜文档 |

跨角色修改必须由 SYNC 在任务卡中明确授权。文档不得复制敏感接入信息，也不得把工作区内部资料未经任务复制进仓库。

## 3. 分支、提交与 PR

- 使用 `docs/*`、`feat/*`、`test/*`、`chore/*` 等已登记任务分支。
- 使用 Conventional Commits，例如：
  - `docs: add delivery documentation baseline`
  - `feat(auth): add refresh token rotation`
  - `fix(memory): preserve review queue ordering`
- 保持原子提交；不得把最终全部代码压缩为一个提交。
- PR 至少说明变更目的、影响范围、验证命令、结果、迁移和回滚影响。
- `main` 只由 A01 SYNC 协调合入。PR 会运行后端、前端、质量清单、敏感信息扫描和 Compose 集成五类 CI；`main` 推送同样运行，但仍不得由执行 Agent 直接写入。

## 4. 代码与文档事实

- 产品蓝图、实现代码和验证结果必须分开描述。
- 只有已定位的代码或已执行命令可以标记为“已实现”或“已验证”。
- 容器/CI 结论必须注明固定提交和 Actions run；当前已验证基线为 `a5bf49b` 的 run `39801657963`。GHCR 发布、云部署和 TLS 不能引用该 run 冒充已验证。
- 不得编造 API、表结构、AI 结果、测试通过状态、部署地址或评审账号。
- 更新代码事实时，同步更新 `docs/fact-check.md` 和相关文档。

## 5. 本地验证

### 后端

```powershell
cd backend
uv sync --locked --all-groups
uv run ruff check .
uv run ruff format --check .
uv run pytest
```

后端测试需要真实 PostgreSQL/Redis。默认测试目标为：

- PostgreSQL：`english_learn_test`
- Redis：`redis://127.0.0.1:6379/15`

使用 `TEST_DATABASE_URL`、`TEST_REDIS_URL` 指向专用测试资源。不得使用生产连接串、真实成员数据或共享 Redis 业务数据库。

### 前端

```powershell
cd frontend
npm ci
npm test
npm run build
```

### 组合代理冒烟

在 PostgreSQL/Redis 可用且后端已启动时，运行前端开发服务器并请求 `/api/v1`。当前基线中该请求通过 Vite 代理返回 `200`。这只能证明代理与基础 API 可达，不能证明认证、业务 CRUD 或 AI 完成。

### Container/Compose

容器路径需要 Docker Engine 与 Docker Compose v2。仅在一次性本地或 CI 环境使用示例占位配置：

```bash
cp .env.example .env
chmod 600 .env
ALLOW_INSECURE_EXAMPLE_ENV=1 ./deploy/scripts/start-stack.sh
```

`ALLOW_INSECURE_EXAMPLE_ENV=1` 只允许一次性环境接受示例占位密钥，禁止用于真实部署。生产参数、域名、TLS、备份和恢复必须走单独任务。本机没有可用 Compose，当前运行时证据来自 Actions run `39801657963`。

## 6. 数据库变更

- 每个模型变更必须有 Alembic migration 和可执行的 downgrade。
- 本地提交前至少执行 `uv run alembic upgrade head` 与 `uv run alembic check`。
- 迁移影响、回滚方式和兼容性风险写入 PR。
- 不在仓库提交数据库备份、生产连接串或真实数据导出。

## 7. 安全边界

- 不提交 `.env`、API Key、密码、私钥、令牌、生产数据库地址或真实成员数据。
- 日志、截图、fixture 和测试输出同样不能包含敏感信息。
- 前端路由守卫只负责体验，不能替代后端权限校验。
- AI 输入和模型输出均视为不可信数据；规划中的 AI 链路必须执行结构化校验和权限检查。
- 对外部署、服务器修改和密钥操作只能由已登记任务的责任角色执行。

## 8. 完成检查

提交前确认：

- 改动只位于任务允许路径。
- `git diff --check` 通过。
- 相关测试、静态检查和构建已执行，或明确记录未执行原因。
- 文档中的路径、命令、状态和代码一致；容器/CI 结论注明提交与 run。
- 没有密钥、真实成员数据或虚假完成声明。
- Markdown 相对链接、尾随空白和最终换行检查通过，且已扫描敏感信息。
- 详细汇报和精简汇报卡按任务卡要求提交。

当前基线文档事实见 `docs/fact-check.md`。
