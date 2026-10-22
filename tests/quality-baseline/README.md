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

2026-10-22 的审查输入为后端 PR #2（`01386cb`）和前端 PR #1（`c7fbe02`）。清单共 47 条：10 条 `PASS`、3 条 `CONDITIONAL`、33 条 `FAIL`、1 条 `NOT_RUN`。因此：

- 普通清单校验通过，表示结构、引用和当前阶段记录一致；
- 最终 MVP 判定失败，结论为 `FAIL / NOT_READY`。

不能把 `RESULT=PASS` 的普通校验结果解释为业务功能已经验收通过。

## 维护规则

1. 门禁 ID 不得重复；新增门禁必须填写来源、责任方、前置条件、测试数据、执行命令和证据路径。
2. 更新证据后同步更新 `updated_at` 与 `reason`，不得只改状态。
3. 阶段门禁与最终门禁分开：`scope: stage` 通过不等于 `scope: final` 通过。
4. 本校验器只负责可追溯性和证据存在性，不能替代 API、E2E、AI 合同、迁移、构建、安全、性能与人工验收。
5. 不记录真实成员数据、密钥、生产连接串或来源不明素材。
