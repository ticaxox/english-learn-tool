# 文档与代码事实核对

- 代码基线：`main` @ `1cea3ff` / `v0.1.7`（2026-11-18）
- 用途：把文档里的关键陈述映射到可复核的代码或证据；数字以本页为准。

## 1. 当前事实

| 陈述 | 证据 | 状态 |
|---|---|---|
| 迁移 head 为 `20261114_0032`，单头 | `backend/alembic/versions/`（40 个 revision） | 已验证 |
| 59 张应用表 | `grep __tablename__ backend/app/models/*.py` | 已验证 |
| OpenAPI 117 路径 / 148 操作 / 203 schema | `app.openapi()` 实际生成 | 已验证 |
| 凭证 `/api/v1/mcp` 不进 OpenAPI | `api/v1/mcp.py` 的 `include_in_schema=False` | 已验证 |
| 后端 40 个测试文件 / 209 个测试函数 | `backend/tests/` | 已验证（静态计数） |
| 前端 58 个 spec / 446 个 `it` | `frontend/src/tests/` | 已验证（静态计数） |
| 前端最近一次实跑 442/442 通过 | 2026-11-17 `d90778d` 的 vitest 输出 | 已验证（旧于当前 tip） |
| 后端 209 个测试当前未执行 | 本机无 PostgreSQL/Redis；conftest 连接失败 | 未验证 |
| `ruff check` 仍有 5 处告警、`format` 1 个文件待格式化 | 2026-11-18 在 `1cea3ff` 上实跑 | 已验证 |
| AI 为 BYOK | `ai_providers.owner_id`、`_providers_for_job(owner_id=...)` | 已验证 |
| 额度为任务计数（100/20/50 每日） | `app/core/config.py` | 已验证 |
| RAG 分块 900/120、≤400 块、阈值 0.12、最多 6 条 | `app/services/knowledge.py` | 已验证 |
| 23 枚徽章、等级曲线 120·L^1.35 | `app/services/gamification.py` | 已验证 |
| 昼夜由 cookie + `data-theme` 驱动，520ms 淡出 | `useTheme.ts`、`ArtImage.vue`、`game-ui.css` | 已验证（代码） |
| 线上预览上次核实为 `v0.1.5` | 2026-11-17 `/health/live` | 已验证（旧于当前日期） |
| 最新标签为 `v0.1.7` | `git tag` | 已验证 |
| 仓库公开但无 LICENSE | GitHub API（2026-11-17）+ `git ls-tree` | 已验证 |

## 2. 已废弃的旧口径

以下数字与说法来自 2026-10-24 的组织版基线，**不得再引用**：

| 旧说法 | 现状 |
|---|---|
| 迁移 head `844c0d89f737` | 现为 `20261114_0032` |
| 46 张表 | 现为 59 张 |
| OpenAPI 84 路径 / 153 schema | 现为 117 / 203 |
| 后端 156 passed | 现为 209 个测试函数；最近可复现执行是 10-22 的旧树 |
| 前端 310 passed | 现为 446 个 `it`；11-17 实跑 442 全绿 |
| 产品名 Whisker Crumb | 现为 Grimoire，角色 Hob |
| 主题只有 Whisker Crumb | 现为万圣节昼夜双态 |
| 组织版成员/看板/通知是主路径 | 个人版主导航只有 今日 / 练习 / Hob / 设置 |
| 预览 `v0.1.2` / `8d5cb83` | 标签已到 v0.1.7；预览上次核实 v0.1.5 |
| 仓库 Private | 实为公开 |
| CSP 未完成、F-SEC-01 未关闭 | 两份 nginx 与后端中间件均已输出 CSP |
| 「Origin + CSRF 双校验」 | 11-18 起 Origin 校验为空实现，只剩 CSRF |

## 3. 需要重跑才能确认

| 项 | 原因 |
|---|---|
| 后端 pytest 209 个 | 需要真实 PostgreSQL 16 与 Redis 7 |
| `alembic upgrade head` 在真实库 | 只做过离线 SQL 渲染 |
| `npm run build` / `npm test` 在当前 tip | 上次执行在 `d90778d` |
| 演示 seed 脚本 | head 已更新，未在当前 schema 上执行 |
| 线上预览的版本 | 11-17 之后未核实 |

## 4. 维护规则

1. 改文档中的数字前，先在当前 `main` 上跑出对应证据。
2. 新功能必须同时更新本页与对应专题文档。
3. 未执行的事项写「未验证」，不写「已通过」。
4. 本页与代码冲突时，以代码为准，并立即修文档。
