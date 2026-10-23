# 贡献指南

## 开始前

1. 阅读项目根 `AGENTS.md`、`ai-workspace/AGENTS.md` 与代码仓库 `AGENTS.md`。
2. 确认正式任务卡、完整任务文档、角色、稳定 `thread_id`、分支所有者、工作树和允许写入路径。
3. 只在已登记工作树中工作；`main` 由 A01 SYNC 协调合并，执行 Agent 不得直接提交。
4. 任务、注册表或代码事实冲突时先返回 `BLOCKED`，不要自行扩大范围。

## 路径责任

| 路径 | 主要责任 |
|---|---|
| `backend/**` | A10 CORE｜后端 |
| `frontend/**` | A20 VIEW｜前端 |
| `.github/**`、`deploy/**`、容器文件 | A40 SHIP｜部署 |
| `tests/**`、质量证据 | A30 TEST｜质量 |
| `docs/**`、根文档与比赛材料 | A50 DOCS｜文档 |

## 分支与提交

- 使用已登记分支和 Conventional Commits，例如 `docs: update competition delivery`、`fix(api): preserve idempotency key`。
- 保持原子提交，保留可追溯 Git 历史。
- PR 说明目的、影响范围、验证命令、结果、迁移/回滚影响和未验证项。
- PR 不自行合并；合并由 A01 协调。

## 本地验证

### 后端

```powershell
cd backend
uv sync --locked --all-groups
uv run ruff check .
uv run ruff format --check .
uv run pytest
```

测试需要真实 PostgreSQL 16 与 Redis 7，不使用内存数据库或假认证。使用 `TEST_DATABASE_URL`、`TEST_REDIS_URL` 指向一次性隔离资源。

### 前端

```powershell
cd frontend
npm ci
npm test
npm run build
```

### Compose

```bash
cp .env.example .env
chmod 600 .env
ALLOW_INSECURE_EXAMPLE_ENV=1 ./deploy/scripts/start-stack.sh
```

`ALLOW_INSECURE_EXAMPLE_ENV=1` 只允许一次性本地/CI 环境。生产环境必须使用独立密钥、真实域名/TLS 和受控备份策略。

### 文档

提交前至少检查：

- `git diff --check`
- Markdown 相对链接和图片路径
- UTF-8、无 BOM、最终换行、无尾随空白
- 敏感信息扫描
- 文档中的 SHA、Actions run、测试数字与证据一致

## 数据库变更

- 每个模型变更必须有 Alembic migration 和可执行 downgrade。
- 本地至少执行 `uv run alembic upgrade head` 与 `uv run alembic check`。
- 迁移影响、回滚方式和兼容性风险写入 PR。
- 不提交数据库备份、生产连接串或真实数据导出。

## 安全边界

- 不提交 `.env`、API Key、密码、私钥、令牌、生产数据库地址或真实成员数据。
- 日志、截图、fixture、测试输出和视频脚本同样不能包含敏感信息。
- 前端路由守卫只负责体验；授权必须在后端服务层再次校验。
- AI 输入、上传词书和模型输出均视为不可信数据。
- 公开截图和视频必须使用合成数据，并由任务负责人检查。

## 完成检查

- 改动只位于任务允许路径。
- 相关测试、静态检查、构建或文档验证已执行，或明确记录未执行原因。
- 文档中的状态与代码、OpenAPI、迁移和 QA 证据一致。
- 工作树干净，PR 不自行合并。
- 详细汇报先落正式报告，再向任务卡指定汇报方发送精简汇报卡。
