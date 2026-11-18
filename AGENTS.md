# AGENTS.md（代码仓库）

本文件只补充本仓库的特殊约定；协作规则以项目根 `AGENTS.md` 为准。

## 仓库

- 这是 Grimoire 的 monorepo：`backend/`（FastAPI + ARQ）、`frontend/`（Vue 3 + Vite）、`deploy/`、`docs/`、`tests/`。
- 当前迁移 head：`20261114_0032`；数据表 59 张；OpenAPI 117 路径 / 203 schema。

## Git

- 一个 Agent、一个分支、一个工作区。
- 分支从最新 `origin/main` 切出，命名 `agent/<agent-id>/<slug>`。
- 只在自己的工作树里 `add` / `commit` / `rebase`。
- 不切换别人的分支，不修改别人的工作树或克隆。
- 永远不提交 `main`、不合并 `main`。
- **默认不 push。** 只有用户亲口要求时才推远端。

## 目录

| 路径 | 默认负责 |
|---|---|
| `backend/**` | A10 |
| `frontend/**` | A20；素材由 A21 交付 |
| `.github/**`、`deploy/**`、容器文件 | A40 |
| `tests/**` | A30 |
| `docs/**`、根 README、比赛材料 | A50 |

默认关注不是独占；在自己的分支里可以做全栈改动。

## 开发

- 一次做完一件事；不要改一点就停下来验证、再改一点。
- 改完跑与改动直接相关的那条路径。数据库迁移、认证与权限、密钥处理、AI 额度计费要做扎实。
- 数据库变化必须提供迁移与回滚说明；迁移保持单头。
- 改后端路由后重新生成 `backend/openapi.json`。
- 不要新增覆盖层样式表；改原样式表。
- 不提交 `.env`、密钥、真实用户数据或来源不明的素材。

## 文档

- `README.md` 与 `docs/**` 由 A50 维护。
- 文档中的数字以当前 `main` 的事实为准；未验证的事项明确标注。
- `docs/fact-check.md` 是数字与陈述的对照表，改数字时同步更新。
