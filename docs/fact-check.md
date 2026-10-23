# 文档与代码事实核对

- 交付基线：`efc6bcbd2679eca02613a7143c68d04dddc36a59`
- 迁移 head：`844c0d89f737`
- OpenAPI：84 路径 / 153 schema
- 核对日期：2026-10-24
- 用途：防止把产品蓝图、QA 截图、计划项或容器构建误写成最终生产完成

## 1. 当前事实映射

| 陈述 | 代码/证据 | 状态 |
|---|---|---|
| FastAPI 应用与 `/api/v1` | `backend/app/main.py`、`router.py` | 已验证 |
| 认证、Refresh、CSRF、改密 | `api/v1/auth.py`、`services/auth.py`、后端测试 | 已验证 |
| 成员管理、最后管理员保护 | `api/v1/admin.py`、`services/users.py` | 已验证 |
| 词书、导入、导出、删除任务 | `models/wordbooks.py`、ARQ worker/scheduler | 已验证 |
| 今日计划、心跳、统计 | `api/v1/learning.py`、`services/learning.py` | 已验证 |
| FSRS 记忆训练 | `services/memory.py`、`fsrs_scheduler.py` | 已验证 |
| AI provider、提示词、额度、任务 | `models/ai.py`、`services/ai_*.py` | 已验证（受控 provider） |
| 四类 AI 练习 | `api/v1/practice.py`、`services/practice.py` | 已验证 |
| 教练 SSE、action receipt、撤销 | `api/v1/coach.py`、`services/coach.py` | 已验证 |
| 每日闯关/BOSS | `api/v1/challenges.py`、`services/challenge.py` | 已验证 |
| 通知/DND/去重 | `api/v1/notifications.py`、`services/notifications.py` | 已验证 |
| 管理员聚合看板/隐私 | `api/v1/admin_dashboard.py`、`services/dashboard.py` | 已验证 |
| 46 张应用表（另含 Alembic 版本表） | SQLAlchemy metadata / Alembic | 已验证 |
| Docker Compose/CI | T-SHIP-001 run `39801657963` | 已验证（该 run） |
| T-QA-004 M5 代码内硬化 | 后端 156、前端 310、M3/M4R API/浏览器 | PASS_WITH_CONDITIONS |
| 演示数据脚本 | `docs/competition/seed_demo_data.py` | 首次/重复初始化 PASS |
| 演示截图 | `docs/competition/screenshots/` | 来自 QA 合成数据 |
| 公网 URL、TLS、GHCR digest | T-SHIP-002 | 未完成 |
| 生产备份恢复/回滚 | T-SHIP-002 | 未完成 |
| 最终视频/公网截图 | 比赛交付 | TODO |
| 完整 MVP | 47 门禁 40/3/4/0 | FAIL / NOT_READY |

## 2. 不可升级的事项

- GHCR 三个镜像已推送、可拉取或已有 digest。
- 云服务器部署、域名、TLS、公网入口和评审账号。
- 生产备份恢复、灾备或回滚演练。
- 真实生产 provider 的模型效果、配额和网络策略。
- 最终比赛视频已录制、公网截图已取得。
- 完整 MVP 已 PASS。
- Today 页面 `ai_practice=not_available` 已修复。

## 3. 已知差异

| 项目 | 当前差异 | 处理 |
|---|---|---|
| Today AI 摘要 | `GET /learning/today` 仍返回旧 `not_available` | 文档明确指向 `/practice`；修复需另立代码任务 |
| 真实 provider | QA 使用受控 OpenAI 兼容 provider | 不写成真实生产模型效果 |
| 本机 Compose | `docker` 实为 `wslc`，无 Compose | 容器运行证据只引用 Actions |
| 生产备份 | 合成库恢复通过，生产 RPO/RTO 未完成 | 保留 CONDITIONAL |
| 许可证 | 仓库未选择开源许可证 | 公开提交前由 A00 决策 |
| 版本发布 | 无 tag/GHCR digest | 保留 CONDITIONAL/TODO |

## 4. 证据索引

- T-QA-004 报告：`ai-workspace/10-collaboration/reports/T-QA-004-TEST.md`
- T-QA-004 证据：`ai-workspace/04-qa/evidence/T-QA-004/README.md`
- 演示数据验证：`ai-workspace/10-collaboration/sessions/A50-DOCS/test-artifacts/T-DOC-002/seed-verification.json`
- QA 截图来源：`ai-workspace/04-qa/evidence/T-QA-004/results/`
- 质量门禁：`tests/quality-baseline/acceptance-gates.json`

## 5. 更新触发条件

出现以下变化时更新本清单：

- 新 API、表、worker 任务、前端路由或真实业务联调。
- T-SHIP-002 冻结公网、TLS、镜像 digest、备份恢复或回滚。
- A30 更新质量门禁状态。
- A00 决定许可证或最终比赛范围。
- 最终视频、评审账号或公网截图完成。

更新时必须记录提交 SHA、Actions run、日期、命令、结果和未覆盖范围。
