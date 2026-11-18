# 贡献指南

## 开始前

1. 读项目根 `AGENTS.md`。它是唯一的协作规则来源。
2. 确认你只在自己的分支和工作树里工作；不要切换到别人的分支，不要修改别人的工作树或克隆。
3. 分支从最新 `origin/main` 切出，命名 `agent/<agent-id>/<slug>`，例如 `agent/a20/coach-levelup`。
4. 永远不提交 `main`，永远不合并 `main`。用户负责对比、挑选和合并各分支。

本仓库不要求任务卡、任务编号、`thread_id`、`BLOCKED` 回报或汇报卡。一次做完一件事，再回头看。

## 分支与提交

- 使用 Conventional Commits，例如 `docs: refresh the API reference`、`fix(auth): keep CSRF on writes`。
- 保持原子提交，保留可追溯 Git 历史。
- **默认不 push。** 只有用户明确要求时才推远端。

## 目录责任

| 路径 | 默认负责 |
|---|---|
| `backend/**` | A10 |
| `frontend/**` | A20；`frontend/src/assets/**` 由 A21 交付 |
| `.github/**`、`deploy/**`、容器文件 | A40 |
| `tests/**`、质量证据 | A30 |
| `docs/**`、根 README | A50 |

关注点只是默认倾向，不代表独占；任何人在自己的分支里都可以做全栈改动。

## 本地验证

### 后端

```powershell
cd backend
uv sync --locked --all-groups
uv run ruff check .
uv run ruff format --check .
uv run pytest
```

测试需要真实 PostgreSQL 16 与 Redis 7，不使用内存数据库或假认证。用 `TEST_DATABASE_URL`、`TEST_REDIS_URL` 指向一次性资源。

### 前端

```powershell
cd frontend
npm ci
npm run build
npm test
```

### 数据库

- 新增迁移必须从当前 head（`20261114_0032`）续接，保持单头。
- 迁移要有 downgrade 路径与兼容性说明。
- 改路由后重新生成 `backend/openapi.json`（命令见 `docs/api.md`）。

## 提交内容边界

- 不提交 `.env`、密钥、真实用户数据、生产连接串或来源不明的素材。
- 不把探索性页面、临时脚本或截图当作生产代码提交；调试脚本放在仓库外或明确标注。
- 文档中的数字必须能在当前 `main` 上复现；未执行的验证写「未验证」。
