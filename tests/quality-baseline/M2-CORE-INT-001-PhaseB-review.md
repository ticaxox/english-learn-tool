# M2-CORE-INT-001｜Phase B 质量门禁复核（A30 独立）

- 复核方：A30 TEST｜质量（`01a16362-3380-7763-9e11-e2413bd8ba69`）
- 汇报方：A01 SYNC｜协同（`01a16362-2260-7783-920d-be63ed631e77`）
- 复核时间：2026-10-23 12:35 +08:00
- 冻结输入：后端 `25ad69f3c2c9ad29c01df6afa88b87e18404361e`；前端 `6611f43beebc5c1d44aed02d17620f3d930abeb9`；基线 `3fb9730a1a3a7fe868fc9ea1d3fb6e8afcf0c4d8`
- 测试分支：`test/m2-core-int-001`，Phase B merge：`404e37a`（前端）→ `3f8791e`（后端）
- 结论：**Phase B `FAIL`，发现 1 个 P1**；Phase A 保持 PASS，任务不关闭，M2 不 PASS，PR #13 不合并

## 1. P1 摘要

- **激活词书切换后新训练会话污染跨词书数据**。
- `POST /memory/sessions` 会把旧 plan 的 primary 词条挂到新 small 词书 session 下；数据库级 7 条 session items 与 7 条 user word states 的 `wordbook_id` 与 entry 所属词书不一致。
- 严重级别：P1（学习数据正确性/一致性）。
- 最小复现与 SQL：`ai-workspace/04-qa/evidence/M2-CORE-INT-001/phase-b/p1/wordbook-switch-session-contamination.md`。
- 原始结果：`ai-workspace/04-qa/evidence/M2-CORE-INT-001/phase-b/results/phase-b-run8/api-acceptance.json`。

## 2. 通过项摘要

- API 主链路：58 项中 55 项 PASS；除词书切换一致性外全部通过。
- 真实浏览器主链路：24/24 PASS；含档案、今日快照、翻卡 Again/重学、刷新恢复、30 秒心跳与暂停、选择/拼写、错词/恢复、小词书 2 options。
- 后端测试：106 passed（真实 PG16/Redis7）；Ruff check/format、uv lock --check 全 0。
- 前端：194 tests passed；`npm ci` 0 vulnerabilities；生产构建 PASS。
- 迁移：空库 upgrade → downgrade base → upgrade → `alembic check` 全 0，无 drift。
- 删除：primary 与 small 均零残留，数据库 13 类表 0 行，共享卷 0 文件。

## 3. 门禁变化

| 门禁 | 前 | 后 | 说明 |
|---|---|---|---|
| `F-MEM-01` | FAIL | FAIL（原因/证据更新） | P1 导致真实记忆链路不可判 PASS；不得关闭 |
| `F-PROFILE-01` | FAIL | **CONDITIONAL** | 档案/今日计划/心跳已真实验证；连续天数与完整统计页未验证 |
| `F-MIG-01` | CONDITIONAL | CONDITIONAL（证据/条件更新） | 当前完整业务迁移链空库回放通过；后续里程碑表尚未冻结 |
| `F-E2E-01` | CONDITIONAL | CONDITIONAL（证据追加，未放宽） | Phase B 浏览器闭环补证据，但仍缺完整 MVP 旅程 |

计数：`PASS 17 / CONDITIONAL 9 / FAIL 20 / NOT_RUN 1`（47）。`--require-final-pass` 仍 `RESULT=FAIL`，该结果正确。

## 4. 验证

- `validate_manifest.py --workspace-root E:\agent workspace\英语学习工具`：`RESULT=PASS`。
- `validate_manifest.py ... --require-final-pass`：`RESULT=FAIL`，保留 30 个未 PASS final 门禁。
- `python -m unittest discover -s tests\quality-baseline -p "test_*.py"`：5 tests，OK。
