# AUTH-INT-001｜合并后质量门禁复核

- 复核方：A01 SYNC｜协同（`01a16362-2260-7783-920d-be63ed631e77`）
- 证据执行方：A30 TEST｜质量（`01a16362-3380-7763-9e11-e2413bd8ba69`）
- 复核时间：2026-10-23 02:19 +08:00
- 冻结输入：后端 `bd50685d726faa1207b7aef78feb159716823c1c`；前端 `f7bc303fac7896006955e574d93d7ba5418f1c11`
- 主线：`da24cd2ee4c3ac88e0d4801ed13ca37a51b73cd3` → `aea77d3f1c8143f576bd543f4ea774aba2873098`
- main push CI：`39829763790`，5/5 PASS
- 结论：认证域 `PASS`；项目仍为 `FAIL / NOT_READY`

## 1. 证据映射

| 门禁 | 状态 | 依据 | 未关闭条件 |
|---|---|---|---|
| `S-FE-04` | PASS | 前端单元测试 + AUTH-INT 真实 API/浏览器会话恢复与角色守卫 | 无 |
| `F-AUTH-01` | PASS | 真实 API 202/202；真实浏览器 32/32；登录、强制改密、Refresh 轮换/重放撤销、logout | 无 |
| `F-ADMIN-01` | PASS | 成员创建、CSV 原子导入、启停删、重置密码、角色修改、最后管理员并发保护 | 无 |
| `F-PRIV-01` | CONDITIONAL | 管理 API/Schema/页面/审计未暴露学习私有正文；身份表无学习正文列 | 学习正文域落地后重新执行真实私有数据隐私回归 |
| `F-E2E-01` | CONDITIONAL | 认证与成员管理浏览器闭环 32/32 | 词书、记忆/FSRS、练习与完整业务演示旅程 |
| `F-SEC-01` | CONDITIONAL | 认证、CSRF/Origin、限流、Cookie、Refresh 重放、越权检查通过 | CSP 与安全响应头 |
| `F-AUDIT-01` | CONDITIONAL | 51 条审计事件、21 条账号写事件；无秘密或私有学习正文 | 保留策略/轮转、备份恢复演练 |
| `F-GIT-01` | CONDITIONAL | PR #6/#7 顺序合并；main 与 CI 可追溯 | 版本标签、发布历史 `GAP-RELEASE-HISTORY` |

## 2. 计数变化

| 快照 | PASS | CONDITIONAL | FAIL | NOT_RUN | 合计 |
|---|---:|---:|---:|---:|---:|
| T-QA-001 基线 | 13 | 3 | 30 | 1 | 47 |
| AUTH-INT-001 合并后 | 16 | 6 | 24 | 1 | 47 |

`--require-final-pass` 仍返回 `RESULT=FAIL`，因为词书、FSRS、今日任务、AI、部署、文档、发布与最终 MVP 等最终门禁尚未完成。该结果正确，不得改成总项目 PASS，也不得把 M2 标为完成。

## 3. 验证

- `validate_manifest.py --workspace-root E:\agent workspace\英语学习工具`：结构、证据路径和状态语义 `RESULT=PASS`。
- `validate_manifest.py --workspace-root E:\agent workspace\英语学习工具 --require-final-pass`：`RESULT=FAIL`，保留 31 个未 PASS 的 final 门禁。
- `python -m unittest discover -s tests\quality-baseline -p "test_*.py"`：5 tests，OK。
- A01 机器记录：`ai-workspace/10-collaboration/sessions/A01-SYNC/test-artifacts/T-SYNC-001/auth-int-001-quality-gates-20261023-0219/`。

## 4. 非阻断观察

`OBS-001`：Redis 不可用时登录返回通用 `500 INTERNAL_SERVER_ERROR`。真实失败态未伪造成功，request ID 完整；建议后续 A10 评估映射为 `503` 或明确的依赖错误码。该观察不阻塞认证域合并。

## 5. 范围边界

本次只完成认证、权限、成员管理、CSV、审计与当前身份域隐私联调的证据映射。词书、导入导出、FSRS、今日任务、AI 练习、教练、挑战、通知、部署和最终演示仍由后续任务完成。
