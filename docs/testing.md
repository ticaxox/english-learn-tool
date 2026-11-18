# 测试与验证记录

- 代码基线：`main` @ `1cea3ff` / `v0.1.7`（2026-11-18）
- 原则：测试结论必须可复现；没有执行证据的能力不标记为「已验证」。

## 1. 测试清单

| 套件 | 规模 | 环境 | 说明 |
|---|---|---|---|
| 后端 pytest | 40 个文件 / 209 个测试函数 | 真实 PostgreSQL 16 + Redis 7 | `conftest.py` 在会话开始时执行 `alembic upgrade head`；每用例事务回滚、Redis flush |
| 前端 vitest | 58 个 spec / 446 个 `it` | jsdom + @vue/test-utils | 无浏览器布局测试 |
| 质量清单 | 5 个 unittest + 1 个校验器 | 纯标准库 | `tests/quality-baseline/` |
| 部署测试 | 22 个 unittest | 纯标准库 | `deploy/tests/`，含 nginx 安全头与 Compose 合同 |
| 手工 E2E | `tests/m4-learning-int`、`tests/m4-condition-recheck-003r`、`tests/m5-hardening-004` | 一次性容器栈 + Playwright/Edge | 不在 CI，路径绑本机，换机不可直接复现 |

后端覆盖域：认证与 CSRF、成员管理、词书导入导出任务、学习计划与心跳、FSRS 记忆与 cloze、六类练习、教练 SSE/附件/撤销、每日闯关与 BOSS、通知、看板、AI provider/提示词/额度/任务/记忆、知识库、MCP、健康、日志、数据库、worker 队列。

前端覆盖域：API 契约、认证、词书、学习训练器、练习、教练、闯关地图、通知、管理员页、个人 AI、游戏化、万圣节素材契约、主题与路由守卫、生产代码禁用项（localStorage、答案字段、mock 数据）。

## 2. 命令

```powershell
# 后端（需要真实 PostgreSQL 与 Redis）
cd backend
uv sync --locked --all-groups
uv run ruff check .
uv run ruff format --check .
uv run pytest

# 前端
cd frontend
npm ci
npm run build
npm test

# 质量清单
python -m unittest discover -s tests/quality-baseline -p "test_*.py"
python tests/quality-baseline/validate_manifest.py --workspace-root .
```

后端可用 `TEST_DATABASE_URL` / `TEST_REDIS_URL` 指向一次性资源；测试不会自动创建数据库。

## 3. 最近一次执行

| 时间 | 基线 | 项目 | 结果 |
|---|---|---|---|
| 2026-11-17 | `d90778d` | 前端 `npm run build` | 通过，1.93s，产物约 894KB JS + 801KB CSS |
| 2026-11-17 | `d90778d` | 前端 `npm test` | **58 文件 / 442 用例全过** |
| 2026-11-18 | `1cea3ff` | 后端 `ruff check` | **5 处告警**（`coach_tools.py:52` E501 + 4 个迁移文件 I001）；`ruff format --check` 尚有 1 个文件待格式化 |
| 2026-11-17 | `d90778d` | 后端 `pytest` | **未执行**：本机无 PostgreSQL/Redis，conftest 在连接阶段失败 |
| 2026-11-17 | `d90778d` | `alembic heads` | 单头 `20261114_0032` |
| 2026-11-17 | `d90778d` | `alembic upgrade head --sql` | 离线渲染通过：39 次升级、60 条 CREATE TABLE |
| 2026-11-17 | `d90778d` | `uv lock --check` | 通过 |

历史 QA 证据不在本仓库内，且对应更早的代码，不能代表当前状态。

## 4. 质量门禁

`tests/quality-baseline/acceptance-gates.json` 仍是 2026-10-24 的 47 条（40 PASS / 3 CONDITIONAL / 4 FAIL），描述的是组织版交付。它与当前产品已错位：

- 仍把「成员管理、看板、通知」记为 PASS，而个人版已从导航移除；
- 未覆盖 11 月新增的知识库/RAG、MCP、游戏化、对话练习；
- `F-SEC-01` 的 CSP 条件已被实现覆盖，但没有重新分类；
- `F-DEMO-01` 依赖的 seed 脚本刚刚对齐迁移 head，尚未执行验证。

**结论**：门禁清单需要按个人版重写；在此之前不要用它对外声明完成度。

## 5. 已知缺口

1. 后端 209 个测试在当前 schema 上从未执行过；40 条迁移也从未在真实 PostgreSQL 上完整 upgrade。
2. 没有自动化浏览器 E2E，也没有视觉回归；昼夜、移动端断点只能靠人眼与手工探针。
3. 前端测试有相当一部分把 CSS/源码当文本断言，选择器重命名会误报。
4. CI 的 backend job 会先跑 ruff，若 lint 未清零则 pytest 不会执行。
5. 没有覆盖率统计。
