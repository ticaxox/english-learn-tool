# 质量基线清单

本目录用于维护 T-QA-001 的验收门禁，不属于应用功能测试。

- `acceptance-gates.json`：USER-DELIVERY-001 与 v1.1 的验收门禁、执行条件、证据路径、责任角色和当前状态。
- `validate_manifest.py`：仅依赖 Python 标准库的清单校验器，检查结构并按需确认证据文件存在。
- `test_validate_manifest.py`：校验器自身的 `unittest`，不替代后端、前端或 E2E 测试。

## 使用方式

在包含本质量清单的代码工作树中执行；`--workspace-root` 必须指向项目根目录。

```powershell
# 校验结构，并检查 PASS/CONDITIONAL 门禁引用的证据文件
python tests\quality-baseline\validate_manifest.py --workspace-root ..\..

# 运行校验器自身测试
python -m unittest discover -s tests\quality-baseline -p "test_*.py"

# 最终 MVP 验收；当前应为 FAIL，这是防误判门禁
python tests\quality-baseline\validate_manifest.py --workspace-root ..\.. --require-final-pass
```

`--workspace-root` 应指向能够解析 `ai-workspace/...` 证据路径的项目根目录；只检查清单结构时可省略。

## 状态语义

| 状态 | 含义 |
|---|---|
| `PASS` | 已按明确命令执行，并有可定位证据。 |
| `CONDITIONAL` | 有条件通过；必须在 `conditions` 中列出剩余条件。 |
| `FAIL` | 契约或实现未通过。 |
| `BLOCKED` | 因前置依赖缺失而无法执行。 |
| `NOT_RUN` | 当前尚不具备可执行条件。 |

`PASS` 与 `CONDITIONAL` 必须包含非空 `evidence`；`CONDITIONAL` 还必须包含非空 `conditions`。`--require-final-pass` 要求所有 `scope: final` 门禁均为 `PASS`，用于防止把阶段完成误报为最终 MVP 完成。

## 当前快照

2026-10-23 M2-CORE-INT-001 Phase A 摘要（词书冻结输入：后端 `22fb815`、前端 `2337ea0`，主线 `3fb9730`；测试分支 `test/m2-core-int-001` HEAD `91a71a6`）。真实跨容器栈（PostgreSQL 16.15 / Redis 7.0.15 / ARQ worker + scheduler / 共享可写卷）上连续两轮 API 80 断言 PASS、连续两轮真实浏览器 30 断言 PASS，另含后端 81 passed ×2、状态性隔离 2 passed ×2、迁移空库 upgrade/downgrade/upgrade 与 drift check 全 0、前后端依赖审计 0 漏洞。权威清单共 47 条：17 条 `PASS`、8 条 `CONDITIONAL`、21 条 `FAIL`、1 条 `NOT_RUN`。

- `F-BOOK-01` 由 `FAIL` 转为 `PASS`（导入→映射→激活→导出→删除全链路，含成员私有词书与删除后无幽灵数据）。
- `F-IDEM-01`、`F-SEC-03` 由 `FAIL` 转为 `CONDITIONAL`（词书域已真实通过；计划/事件/心跳与 AI 媒体上传尚未覆盖）。
- `F-PRIV-01`、`F-MIG-01` 保持 `CONDITIONAL`，条件分别收紧/扩围到学习正文域与 Phase B 迁移。
- `F-E2E-01` 保持 `CONDITIONAL` **未放宽**：完整业务旅程仍缺今日计划、记忆/FSRS、练习与 AI 教练。
- 最终 MVP 仍为 `FAIL / NOT_READY`；普通清单校验通过只表示结构、证据引用和当前阶段记录一致，不代表最终 PASS。

Phase A 只是 M2 的第一阶段，`M2-CORE-INT-001` 未关闭、M2 未 PASS；Phase B 需在 T-BE-004 / T-FE-004 冻结后由 A01 追加。

## 维护规则

1. 门禁 ID 不得重复；新增门禁必须填写来源、责任方、前置条件、测试数据、执行命令和证据路径。
2. 更新证据后同步更新 `updated_at` 与 `reason`，不得只改状态。
3. 阶段门禁与最终门禁分开：`scope: stage` 通过不等于 `scope: final` 通过。
4. 本校验器只负责可追溯性和证据存在性，不能替代 API、E2E、AI 合同、迁移、构建、安全、性能与人工验收。
5. 不记录真实成员数据、密钥、生产连接串或来源不明素材。
