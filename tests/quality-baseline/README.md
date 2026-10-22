# 质量基线清单

本目录用于维护 T-QA-001 的验收门禁，不属于应用功能测试。

- `acceptance-gates.json`：USER-DELIVERY-001 与 v1.1 的验收门禁、执行条件、证据路径、责任角色和当前状态。
- `validate_manifest.py`：仅依赖 Python 标准库的清单校验器，检查结构并按需确认证据文件存在。
- `test_validate_manifest.py`：校验器自身的 `unittest`，不替代后端、前端或 E2E 测试。

## 使用方式

在任务工作树 `E:\agent workspace\英语学习工具\worktrees\A30-TEST` 中执行：

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

2026-10-22 二次复审输入为后端 PR #2（`9ac4590`）和前端 PR #1（`9718fc2`）。旧证据仍在 `04-qa/evidence/T-QA-001/`；本轮证据在 `04-qa/evidence/T-QA-001/retest-20261022-2146/`。清单共 47 条：13 条 `PASS`、3 条 `CONDITIONAL`、30 条 `FAIL`、1 条 `NOT_RUN`。

- QA-D-001、QA-D-002、QA-D-003 均已关闭；Stage A 工程基线为 `PASS`。
- `S-FE-04` 仍为 `CONDITIONAL`，条件是 `AUTH-INT-001` 的真实认证联调；该条件是已登记后续依赖，不是本轮三项缺陷或新阻断。
- 最终 MVP 仍为 `FAIL / NOT_READY`；普通清单校验通过只表示结构、引用和当前阶段记录一致。

不能把 Stage A 的 `PASS` 解释为真实认证、完整业务闭环、E2E、AI、容器、CI、部署或最终 MVP 已完成。

## 维护规则

1. 门禁 ID 不得重复；新增门禁必须填写来源、责任方、前置条件、测试数据、执行命令和证据路径。
2. 更新证据后同步更新 `updated_at` 与 `reason`，不得只改状态。
3. 阶段门禁与最终门禁分开：`scope: stage` 通过不等于 `scope: final` 通过。
4. 本校验器只负责可追溯性和证据存在性，不能替代 API、E2E、AI 合同、迁移、构建、安全、性能与人工验收。
5. 不记录真实成员数据、密钥、生产连接串或来源不明素材。
