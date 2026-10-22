# M2-CORE-INT-001｜Phase A 质量门禁复核（A30 独立）

- 复核方：A30 TEST｜质量（`01a16362-3380-7763-9e11-e2413bd8ba69`）
- 汇报方：A01 SYNC｜协同（`01a16362-2260-7783-920d-be63ed631e77`）
- 复核时间：2026-10-23 07:55 +08:00
- 冻结输入：后端 `22fb8158a675552f444fe92ca01e88600355c978`；前端 `2337ea0d14fb7707a938727cf81a6b12e58c766f`；主线 `3fb9730a1a3a7fe868fc9ea1d3fb6e8afcf0c4d8`
- 合并结果：`test/m2-core-int-001` HEAD `91a71a6d18a5ec1f5bbd0dc3af2a5394357a764c`
- 结论：**Phase A `PASS`**；项目整体仍为 `FAIL / NOT_READY`

## 1. 门禁变化

| 门禁 | 变更前 | 变更后 | 依据 |
|---|---|---|---|
| `F-BOOK-01` | FAIL | **PASS** | 真实跨容器栈 + 真实浏览器全链路，API 80 断言 ×2、浏览器 30 断言 ×2 |
| `F-PRIV-01` | CONDITIONAL | CONDITIONAL（收紧条件） | 词书私有边界已真实 PASS；学习正文域仍未落地 |
| `F-IDEM-01` | FAIL | **CONDITIONAL** | 词书域幂等/冲突/队列恢复真实 PASS；计划/事件/心跳待 Phase B |
| `F-SEC-03` | FAIL | **CONDITIONAL** | 上传/下载/路径穿越/PDF 已真实 PASS；AI 媒体与用户 PDF 解析尚未实现 |
| `F-MIG-01` | CONDITIONAL | CONDITIONAL（扩围） | 当前完整业务迁移链空库 upgrade/downgrade/upgrade + drift check 全 0；Phase B 表未落地 |
| `F-E2E-01` | CONDITIONAL | CONDITIONAL（**不放宽**） | 追加词书浏览器闭环证据，条件不变：仍缺今日计划、记忆/FSRS、练习、AI 教练 |

计数：`PASS 17 / CONDITIONAL 8 / FAIL 21 / NOT_RUN 1`（共 47）。认证域合并后快照为 `PASS 16 / CONDITIONAL 6 / FAIL 24 / NOT_RUN 1`；本轮 `F-BOOK-01` 转 PASS、`F-IDEM-01` 与 `F-SEC-03` 由 FAIL 转 CONDITIONAL、`F-PRIV-01` 与 `F-MIG-01` 维持 CONDITIONAL，`F-E2E-01` 维持 CONDITIONAL。

## 2. 三项必须确认的结论

| 必须确认 | 结论 | 证据 |
|---|---|---|
| 词书导入导出、格式识别、预览映射、激活、删除与权限 | **CLOSED / PASS** | `results/phase-a-api-cleanstack-final1|2/api-acceptance.json`、`results/phase-a-browser-cleanstack-final1|2/browser-acceptance.json` |
| 跨容器共享卷下真实 worker 排队与恢复 | **CLOSED / PASS** | `wordbook.queue.*` 4 项；停 worker 8s 仍 `queued`，Redis ARQ 队列可观测，重启后 succeeded |
| 删除后无幽灵数据（数据库级 + 共享卷） | **CLOSED / PASS** | `wordbook.delete.leaves-no-ghost-rows`、`keeps-minimal-tombstone`、`removes-shared-volume-artifacts` |

## 3. 未关闭条件（写入清单 `conditions`）

- `F-PRIV-01`：学习正文域（答题、草稿、教练对话、会话/事件）私有数据边界回归；M2 记忆正文进入冻结输入后补管理员不可读回归。
- `F-IDEM-01`：今日计划 ensure、训练事件提交、心跳的幂等与并发；M3 批量 AI 操作幂等。
- `F-SEC-03`：AI 素材（图片/SVG）上传消毒与重编码；若支持用户上传 PDF 则补解析隔离。
- `F-MIG-01`：Phase B 记忆/计划/事件/心跳表落地后重跑空库回放与 drift check；最终 MVP 前全量 Schema 演练。
- `F-E2E-01`：今日计划、记忆/FSRS、练习、AI 教练与完整演示旅程（**未放宽**）。

## 4. 验证

- `validate_manifest.py --workspace-root E:\agent workspace\英语学习工具`：`RESULT=PASS`（结构与全部 PASS/CONDITIONAL 证据路径存在）。
- `validate_manifest.py ... --require-final-pass`：`RESULT=FAIL`，30 条 final 门禁未 PASS。该结果正确，不得改成总项目 PASS。
- `python -m unittest discover -s tests\quality-baseline -p "test_*.py"`：5 tests，OK。

## 5. 非阻断观察

1. 冻结前端把学习概览占位页指向 `/learning/today`，冻结后端 OpenAPI（24 paths）无该端点，浏览器控制台出现 2 条 404。属 M0/M1 骨架遗留，Phase A 不允许改业务源码；已在浏览器结果中显式分类为 `pre-existing-scaffold-404` 并保留计数，未过滤。建议 Phase B 派发时一并处理。
2. `git diff --check 3fb9730 22fb815` 因冻结后端字体许可文件 `backend/app/assets/fonts/OFL.txt:21` 行尾空白返回 2；工作树 `git diff --check` 为 0。属继承项，A30 不修改业务源码。
