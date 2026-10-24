# 文档与代码事实核对

- 代码基线：`efc6bcbd2679eca02613a7143c68d04dddc36a59`
- 临时公网预览：`http://23.94.141.170:18080`（`v0.1.0`，commit `4ee1a71`）
- 迁移 head：`844c0d89f737`
- OpenAPI：84 路径 / 153 schema
- 核对日期：2026-10-24
- 用途：防止把 QA 截图、临时 HTTP 预览或计划项误写成稳定生产/最终 MVP 完成

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
| 临时 HTTP 公网预览 | URL / `v0.1.0` / commit `4ee1a71` / T-SHIP-002 | PASS（仅临时 HTTP） |
| 发布镜像与 digest | release `v0.1.0`；workflow `40023555751`；三镜像 digest | 已验证 |
| 预览备份/恢复/机械回滚 | RPO 24h / RTO 2h / 保留 7 天；数据库与词书恢复 | PASS_WITH_LIMITS |
| 稳定 HTTPS/TLS/长期 SLA | 本次授权范围外 | 未验证 |
| 演示数据脚本 | `docs/competition/seed_demo_data.py` | 首次/重复初始化 PASS |
| 演示截图 | `docs/competition/screenshots/` | QA 合成数据；公网截图 TODO |
| 最终视频 | 比赛交付 | TODO |
| 完整 MVP | 47 门禁 40/3/4/0 | FAIL / NOT_READY |

## 2. 不可升级的事项

- 稳定 HTTPS、TLS、域名或长期生产 SLA 已完成。
- 历史兼容业务版本回滚已通过。
- 真实生产 provider 的模型效果、配额和网络策略。
- 最终比赛视频已录制、公网截图已取得。
- 完整 MVP 已 PASS。
- Today 页面 `ai_practice=not_available` 已修复。

## 3. 已知差异

| 项目 | 当前差异 | 处理 |
|---|---|---|
| 预览传输 | 只有临时 HTTP IP；HSTS 头不能替代 HTTPS | 保留“临时 HTTP 预览”边界 |
| 生产备份 | 演示环境恢复通过；历史兼容业务回滚未验证 | 保留 CONDITIONAL |
| 版本发布 | `v0.1.0`、release workflow 和三镜像 digest 已通过；GHCR 在线拉取未单独验证 | 记录为已验证范围，不升级最终 MVP |
| Today AI 摘要 | `GET /learning/today` 仍返回旧 `not_available` | 文档指向 `/practice`；修复需另立代码任务 |
| 真实 provider | QA 使用受控 OpenAI 兼容 provider | 不写成真实生产模型效果 |
| 本机 Compose | `docker` 实为 `wslc`，无 Compose | 容器运行证据引用 Actions/A40 |
| 许可证 | 仓库未选择开源许可证 | 公开提交前由 A00 决策 |

## 4. 证据索引

- T-QA-004 报告：`ai-workspace/10-collaboration/reports/T-QA-004-TEST.md`
- T-QA-004 证据：`ai-workspace/04-qa/evidence/T-QA-004/README.md`
- T-SHIP-002 报告：`ai-workspace/10-collaboration/reports/T-SHIP-002-SHIP.md`
- T-SHIP-002 公网证据：`ai-workspace/10-collaboration/sessions/A40-SHIP/test-artifacts/T-SHIP-002-20261024/racknerd/`
- 本任务公网轻量核验：`ai-workspace/10-collaboration/sessions/A50-DOCS/test-artifacts/T-DOC-002/public-preview-check.json`
- 演示数据验证：`ai-workspace/10-collaboration/sessions/A50-DOCS/test-artifacts/T-DOC-002/seed-verification.json`
- 质量门禁：`tests/quality-baseline/acceptance-gates.json`

## 5. 更新触发条件

- 新 API、表、worker 任务、前端路由或真实业务联调。
- 稳定 HTTPS、DNS 或长期生产 SLA 完成。
- A30 更新质量门禁状态。
- A00 决定许可证或最终比赛范围。
- 最终视频、评审账号或公网截图完成。

更新时必须记录提交 SHA、Actions run、日期、命令、结果和未覆盖范围。
