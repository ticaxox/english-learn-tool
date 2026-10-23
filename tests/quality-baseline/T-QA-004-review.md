# T-QA-004｜M5 全量硬化复审记录

- 日期：2026-10-24 +08:00
- 执行方：A30 TEST｜质量
- 输入：`283114941c1d1b7c7ef535970c22772e3b8530b6`
- 分支：`test/final-hardening-004`
- 结论：**M5 硬化 PASS_WITH_CONDITIONS；最终 MVP 仍 FAIL / NOT_READY**

## 真实环境与全量结果

- PostgreSQL 16 / Redis 7 / API / ARQ worker / 独立 scheduler / 真实前端代理 / 受控 provider。
- 后端全量：156 passed；Ruff check/format PASS。
- 前端全量：310 passed；npm ci/build PASS；npm audit 0 漏洞。
- M3：API 54/54、浏览器 13/13。
- M4 条件链路：API 21/21、浏览器 14/14、0 缺口。
- 安全/性能探针：PASS；读 P95 0.031 ms、提交 47 ms、5000 行导入 1.92 s、SSE 首事件 31 ms。
- 迁移：空库 upgrade/check/downgrade/re-upgrade PASS，drift 0。
- 备份恢复：合成数据库 dump/restore 关键表计数一致（14,6,5,1）。
- 基线 CI：run `39999074319` 5/5（含 Compose、迁移、前端、后端、质量清单和 gitleaks）。

## 已关闭门禁

`F-AI-01`、`F-BOOK-01`、`F-MEM-01`、`F-PROFILE-01`、`F-PRACTICE-01`、`F-ANSWER-01`、`F-RECORD-01`、`F-NOTIF-01`、`F-E2E-01`、`F-AI-CONTRACT-01`、`F-SEC-02`、`F-SEC-03`、`F-DOCKER-01`、`F-PERF-01`、`F-MIG-01` 均由真实链路/API/浏览器/构建/迁移证据支持。原有 M4 门禁 `F-COACH-01/02`、`F-CHAL-01`、`F-SHARED-01`、`F-DASH-01`、`F-PRIV-01`、`F-IDEM-01`、`F-FAIL-01` 继续保持 PASS。

## 保留条件/失败

- `F-SEC-01` CONDITIONAL：X-Content-Type-Options、X-Frame-Options、Referrer-Policy 通过，但反向代理未配置 CSP；不能把安全头门禁写成完全 PASS。
- `F-AUDIT-01` CONDITIONAL：合成库恢复演练通过；生产备份审批、RPO/RTO 和 A40 恢复演练尚未完成。
- `F-GIT-01` CONDITIONAL：分支/PR/提交历史可追溯，但版本标签和发布历史未完成。
- `F-DEMO-01` FAIL：缺少可直接执行的比赛演示数据初始化入口与账号说明。
- `F-DOC-01` FAIL：根 README 仍是旧工程骨架状态，未更新 M2–M4 完成能力和完整演示步骤；比赛技术文档正文未交付。
- `F-COMP-01` FAIL：比赛视频、演示截图/清单未完成。
- `F-FINAL-01` FAIL：上述条件与业务外部交付未全部关闭，不能宣称最终 MVP PASS。

## 结论

M5 的代码内能力、全量回归、真实 PG/Redis/ARQ、全链路 E2E、安全边界、性能、迁移和备份恢复已得到可复现证据；但 CSP、生产级备份责任、演示数据、文档和比赛材料仍是明确的非代码/交付阻断项。建议 A01 将 M5 记为 **PASS_WITH_CONDITIONS**，不合并 PR 前由 A00/A40/A50 处理外部交付条件。
