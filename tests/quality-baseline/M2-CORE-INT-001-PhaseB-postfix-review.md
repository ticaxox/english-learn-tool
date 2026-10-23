# M2-CORE-INT-001｜Phase B 修复后质量门禁复核

- 复核方：A30 TEST｜质量（`01a16362-3380-7763-9e11-e2413bd8ba69`）
- 修复输入：T-BE-011 `b6489cdc05e76b534eccd6df6369440a811d6098`（PR #27，CI `39959330684` 5/5）
- 前端：`6611f43beebc5c1d44aed02d17620f3d930abeb9`；基线 `3fb9730`
- 合并：`7fb7b34`
- 结论：**P1 CLOSED；Phase B PASS**；M2 不关闭，最终 MVP 不 PASS，PR #13 不合并

## 1. 复验结果

- P1 最小 smoke：4/4 PASS，跨书 mismatch=0，显式不一致返回 409 `MEMORY_WORDBOOK_PLAN_MISMATCH`。
- 完整真实跨容器链路：API 59/59 PASS，真实 Chromium 24/24 PASS。
- 后端：152 passed；Ruff check/format 0。
- 前端：194 tests passed；npm ci 0 vulnerabilities；build PASS。
- 迁移：空库 upgrade → downgrade base → upgrade → `alembic check` 全 0。
- 删除：数据库 13 类表 0 行，共享卷 0 文件。

## 2. 门禁变化

| 门禁 | 前 | 后 | 说明 |
|---|---|---|---|
| `F-MEM-01` | FAIL | **PASS** | P1 关闭；翻卡/选择/拼写/FSRS/会话/错词/恢复真实链路通过 |
| `F-PROFILE-01` | CONDITIONAL | CONDITIONAL | 档案/今日/心跳通过；连续天数与完整统计页待补 |
| `F-MIG-01` | CONDITIONAL | CONDITIONAL | 当前全量迁移回放通过；最终 MVP Schema 仍待收口 |
| `F-E2E-01` | CONDITIONAL | CONDITIONAL | 追加 Phase B 证据，未放宽 |

计数：`PASS 18 / CONDITIONAL 8 / FAIL 20 / NOT_RUN 1`。`--require-final-pass` 仍 FAIL，符合最终 MVP 未完成的真实状态。

## 3. 证据

- `ai-workspace/04-qa/evidence/M2-CORE-INT-001/phase-b/results/p1-smoke-run1/p1-smoke.json`
- `ai-workspace/04-qa/evidence/M2-CORE-INT-001/phase-b/results/phase-b-postfix-run1/api-acceptance.json`
- `ai-workspace/04-qa/evidence/M2-CORE-INT-001/phase-b/results/phase-b-postfix-run1/browser-acceptance.json`
- `ai-workspace/04-qa/evidence/M2-CORE-INT-001/phase-b/logs/postfix-backend-pytest.log`
- `ai-workspace/04-qa/evidence/M2-CORE-INT-001/phase-b/logs/postfix-migration.log`
