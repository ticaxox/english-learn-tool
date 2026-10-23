# 测试与验证记录

- 交付基线：`efc6bcbd2679eca02613a7143c68d04dddc36a59`
- M5 代码内结论：`PASS_WITH_CONDITIONS`
- 最终 MVP：`FAIL / NOT_READY`
- QA 证据：`ai-workspace/04-qa/evidence/T-QA-004/`
- 本任务新增演示数据证据：`ai-workspace/10-collaboration/sessions/A50-DOCS/test-artifacts/T-DOC-002/seed-verification.json`

## 1. 已验证结果

| 范围 | 结果 | 证据 |
|---|---|---|
| 后端全量 | 156 passed；Ruff lint/format PASS | T-QA-004 |
| 前端全量 | 310 passed；`npm ci`/build PASS；0 已知漏洞 | T-QA-004 |
| M3 真实 API | 54/54 PASS | `results/m5-m3-20261024-0235/api-acceptance.json` |
| M3 真实浏览器 | 13/13 PASS | 同目录 `browser-acceptance.json` |
| M4R 条件链路 API | 21/21 PASS | `results/m5-m4r-20261024-0242/api-acceptance.json` |
| M4R 真实浏览器 | 14/14 PASS，0 缺口 | 同目录 `browser-acceptance.json` |
| 性能 | 读 P95 0.031 ms、提交 47 ms、5000 行导入 1.92 s、SSE 首事件 31 ms | `results/m5-probe-20261024-0312/api-acceptance.json` |
| 迁移 | 空库 upgrade/check/downgrade/re-upgrade PASS，drift 0 | T-QA-004 日志 |
| 备份恢复 | 合成库 dump/restore 关键表计数一致 | T-QA-004 |
| 依赖审计 | 后端 0、前端 0 已知漏洞 | T-QA-004 |
| 47 门禁 | 40 PASS / 3 CONDITIONAL / 4 FAIL / 0 NOT_RUN | `tests/quality-baseline/acceptance-gates.json` |

T-QA-004 的 PR CI run `40006774365` 为 5/5 PASS；基线 CI run `39999074319` 为 5/5 PASS。

## 2. 后端命令

```powershell
cd backend
uv sync --locked --all-groups
uv run ruff check .
uv run ruff format --check .
uv run pytest
uv run alembic upgrade head
uv run alembic check
```

测试必须使用真实 PostgreSQL/Redis；`TEST_DATABASE_URL` 和 `TEST_REDIS_URL` 指向隔离资源。不得使用内存数据库、生产连接串或真实成员数据。

## 3. 前端命令

```powershell
cd frontend
npm ci
npm test
npm run build
```

T-QA-004 已覆盖认证、成员管理、词书、记忆、练习、教练、挑战、通知、看板和错误态。视觉截图来自真实浏览器，不是 PPT 或静态 mock。

## 4. 演示数据初始化验证

在一次性 PostgreSQL 数据库中执行：

```powershell
$env:DEMO_SEED_CONFIRM = 'YES'
$env:DEMO_ADMIN_PASSWORD = '<unique demo admin password>'
$env:DEMO_MEMBER_PASSWORD = '<different unique demo member password>'
uv run --project backend python docs/competition/seed_demo_data.py --apply
```

验证结果：

- 首次初始化：PASS。
- 重复初始化：PASS。
- 数据库 revision：`844c0d89f737`。
- 4 个合成账号、20 个词条、60 个记忆状态、3 个每日计划、1 个练习记录、1 个教练会话、5 个挑战节点、3 个通知。
- 真实 API：管理员登录/看板/成员/词书，成员登录/今日计划/档案/挑战/练习记录/练习详情/教练会话/教练消息/未读数，共 13 项均返回 200。
- 管理员看板显示 3 个活跃成员和 1 个隐私安全分组，不返回成员正文。
- 练习详情包含 3 题、1 个错题；教练消息包含 `adjust_daily_plan` applied receipt；挑战地图包含 5 个节点。

说明：`GET /learning/today` 的 `ai_practice` 字段仍返回旧 `not_available`；已实现的 AI 练习从 `/practice` 使用。该差异不隐藏、不伪修，作为当前已知限制记录。

## 5. 47 门禁状态

已 PASS 的核心门禁包括认证、成员管理、词书、记忆、档案、四类 AI 练习、答案防泄露、记录、通知、E2E、AI 合同、安全头部分项、Docker、性能和迁移。

保留条件/失败：

- `F-SEC-01` CONDITIONAL：CSP 未配置。
- `F-AUDIT-01` CONDITIONAL：生产备份审批/RPO/RTO 与恢复演练未完成。
- `F-GIT-01` CONDITIONAL：版本标签/发布历史未完成。
- `F-DEMO-01` FAIL：本任务已增加可执行演示数据脚本和账号说明，但最终状态仍由 A30/A01 复验后更新。
- `F-DOC-01` FAIL：本任务更新 README、技术文档和专题文档，但最终状态仍由 A30/A01 复验后更新。
- `F-COMP-01` FAIL：截图和视频脚本已准备；最终公网入口、最终视频与提交清单仍待 T-SHIP-002。
- `F-FINAL-01` FAIL：最终 MVP 未验收。

## 6. 不重复执行的范围

A01 明确要求复用 T-QA-004 的 M3/M4R/性能/安全证据，不重复全量测试。本任务没有把旧的 156/310 数字冒充当前文档分支新跑结果；它们是固定 QA 基线证据，文档分支只新增 Markdown、截图和演示数据脚本。

## 7. 提交前检查

- `git diff --check`
- Markdown 链接、图片路径、UTF-8、无 BOM、最终换行、无尾随空白
- 敏感信息扫描
- 截图 SHA256 与 QA 来源一致
- 演示脚本语法、`--help`、首次/重复初始化
- PR CI 5/5

## 8. 相关文档

- [事实核对](fact-check.md)
- [部署](deployment.md)
- [演示数据](competition/demo-data.md)
- [截图清单](competition/screenshots/README.md)
