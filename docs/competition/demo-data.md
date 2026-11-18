# 演示数据与账号说明

- 脚本：[`seed_demo_data.py`](seed_demo_data.py)
- 代码基线：`main` @ `1cea3ff` / `v0.1.7`
- 迁移 head：`20261114_0032`
- 数据性质：合成演示数据；不含真实用户、真实对话、真实词书正文或真实 Key

## 1. 账号

| 用户名 | 角色 | 用途 |
|---|---|---|
| `demo_admin` | admin | 管理端、AI provider、知识库 |
| `demo_member` | member | 主演示账号：今日、记忆、练习、教练、闯关 |
| `demo_member2` / `demo_member3` | member | 多成员与看板数据 |

密码不写入仓库、文档或证据，只能由环境变量提供；两个主密码必须不同、至少 12 字符。

## 2. 脚本创建的内容

- 4 个合成账号与学习档案。
- 演示词书与词条（包含合成例句）。
- 若干记忆状态（new / learning / review / mastered）与今日计划。
- 一组已完成练习、得分与错题。
- 一个教练会话、消息、SSE 事件与动作回执。
- 一张含复习、新词、词义训练、AI 练习与 BOSS 的闯关地图。
- 最近几天的学习活动，用于周报与统计。

> 脚本最初按组织版 schema 编写，包含通知与看板数据。当前 schema 为个人版 + 知识库 + 游戏化；head 常量已更新为 `20261114_0032`，但**尚未在当前代码上执行验证**。

## 3. 执行

### 前置

- 一次性或专用演示数据库，已执行 `alembic upgrade head`。
- 不要在已部署预览库或真实用户库上执行。
- 不把密码写进命令历史、脚本或 Git。

### 命令

```powershell
$env:DEMO_SEED_CONFIRM = 'YES'
$env:DEMO_ADMIN_PASSWORD = '<unique demo admin password>'
$env:DEMO_MEMBER_PASSWORD = '<different unique demo member password>'
uv run --project backend python docs/competition/seed_demo_data.py --apply
```

脚本在写入前会校验 `alembic_version`，不匹配即退出。重复执行应保持幂等（以脚本实现为准，执行前先在临时库验证）。

## 4. 验证清单

执行后至少核对：

1. `demo_admin` 能登录并打开 `/admin/users`。
2. `demo_member` 能登录并看到今日计划、推荐词书与闯关地图。
3. `/practice` 能打开练习入口，`/coach` 能新建会话。
4. `/me/progress` 有等级、灯油与徽章数据。
5. `/settings/wordbooks` 能看到演示词书。

## 5. 如果脚本失败

- 先确认数据库 head 为 `20261114_0032`。
- 若报列缺失或非空约束，说明脚本与当前 schema 不一致；此时以代码为准更新脚本，不要改数据库绕过。
- 失败时不要使用旧截图代替演示；记录失败原因并在提交清单中标注。
