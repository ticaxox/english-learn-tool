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

2026-10-23 认证域合并后输入为 PR #6（`bd50685`）与 PR #7（`f7bc303`），主线合并提交为 `da24cd2` → `aea77d3`，main push CI `39829763790` 为 5/5 PASS。AUTH-INT-001 真实 API `202/202`、真实浏览器 `32/32`；权威清单共 47 条：16 条 `PASS`、6 条 `CONDITIONAL`、24 条 `FAIL`、1 条 `NOT_RUN`。

- `S-FE-04`、`F-AUTH-01`、`F-ADMIN-01` 已按 AUTH-INT-001 真实证据转为 `PASS`。
- `F-PRIV-01`、`F-E2E-01`、`F-SEC-01`、`F-AUDIT-01` 保留 `CONDITIONAL`，分别等待学习正文域真实数据、完整业务旅程、CSP/安全响应头、审计保留/备份恢复。
- `F-GIT-01` 仍为 `CONDITIONAL`，条件是版本标签与发布历史 `GAP-RELEASE-HISTORY`。
- 最终 MVP 仍为 `FAIL / NOT_READY`；普通清单校验通过只表示结构、证据引用和当前阶段记录一致，不代表最终 PASS。

不能把认证、成员管理、CSV、审计和隐私联调的 `PASS` 解释为词书、FSRS、今日任务、AI、完整 E2E、部署或最终 MVP 已完成。

## 维护规则

1. 门禁 ID 不得重复；新增门禁必须填写来源、责任方、前置条件、测试数据、执行命令和证据路径。
2. 更新证据后同步更新 `updated_at` 与 `reason`，不得只改状态。
3. 阶段门禁与最终门禁分开：`scope: stage` 通过不等于 `scope: final` 通过。
4. 本校验器只负责可追溯性和证据存在性，不能替代 API、E2E、AI 合同、迁移、构建、安全、性能与人工验收。
5. 不记录真实成员数据、密钥、生产连接串或来源不明素材。
