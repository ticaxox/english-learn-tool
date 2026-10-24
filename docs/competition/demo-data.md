# 演示数据与账号说明

- 脚本：[`seed_demo_data.py`](seed_demo_data.py)
- 数据性质：合成演示数据；不含真实成员、真实对话、真实词书正文或真实 Key
- 已验证：一次性 PostgreSQL 数据库首次初始化、重复初始化、真实 API 读取
- 证据：`ai-workspace/10-collaboration/sessions/A50-DOCS/test-artifacts/T-DOC-002/seed-verification.json`
- 临时公网预览：`http://23.94.141.170:18080`（`v0.1.1`，commit `a6ac195`，主题 Whisker Crumb；HTTP）

## 1. 账号

| 用户名 | 角色 | 用途 |
|---|---|---|
| `demo_admin` | admin | 管理员配置、成员、词书、AI provider、看板 |
| `demo_member` | member | 主要成员闭环、练习、教练、挑战、通知 |
| `demo_member2` | member | 多成员组织聚合 |
| `demo_member3` | member | 最小分组/组织看板 |

远端预览使用 `demo_admin`、`demo_member`。密码不写入仓库/文档/证据；只从 A40 的 ACL 本地凭据文件安全获取。

本地/独立环境脚本仍要求：

- `DEMO_ADMIN_PASSWORD`
- `DEMO_MEMBER_PASSWORD`

两个密码必须不同、至少 12 字符，并由受控渠道交付给评审或演示者。演示密码不得与真实管理员密码相同。

## 2. 数据内容

脚本创建：

- 4 个合成账号与学习档案。
- 1 本 20 词组织词书，含英文/中文释义和合成例句。
- 60 个记忆状态（new/learning/review/mastered）。
- 3 个今日计划。
- 1 个已完成 3 题填空练习、66.67 分、1 个错题。
- 1 个教练会话、2 条消息、SSE 事件和 `adjust_daily_plan` receipt。
- 1 个 5 节点挑战地图（复习、新词、词义训练、AI 练习、BOSS）。
- 3 条站内通知和 DND/偏好数据。
- 最近 4 天的合成学习活动，用于管理员聚合看板。

## 3. 初始化

> 公网预览已由 A40 准备合成数据；不要在远端重复执行 seed。以下命令用于本地/独立环境。

### 前置

- 数据库已执行 `alembic upgrade head`，revision 为 `844c0d89f737`。
- 使用一次性数据库或专用演示数据库，不使用真实成员数据库。
- 不把密码写入命令历史、脚本或 Git。

### 命令

```powershell
$env:DEMO_SEED_CONFIRM = 'YES'
$env:DEMO_ADMIN_PASSWORD = '<unique demo admin password>'
$env:DEMO_MEMBER_PASSWORD = '<different unique demo member password>'
uv run --project backend python docs/competition/seed_demo_data.py --apply
```

从后端目录运行：

```powershell
cd backend
uv run python ../docs/competition/seed_demo_data.py --apply
```

脚本会先检查：

1. `DEMO_SEED_CONFIRM=YES`。
2. 两个密码存在且不同。
3. 数据库 revision 为 `844c0d89f737`。
4. 已存在的 demo 用户名/词书 ID 没有被非 demo 数据占用。

## 4. 重复初始化

脚本默认是可重复的：

- 只删除固定 demo UUID 命名空间内的用户、词书和关联数据。
- 不删除非 demo 用户、词书或任务。
- 重新创建同一套账号、词书、练习、教练、挑战和通知。

首次初始化和重复初始化均在一次性独立数据库中返回 `PASS`。

## 5. 验证

初始化后可以执行：

```powershell
Invoke-RestMethod -Uri 'http://127.0.0.1:8080/health/ready'
```

真实 API 验证范围：

- 管理员：登录、看板、成员、词书。
- 成员：登录、今日计划、档案、挑战、练习记录、练习详情、教练会话、教练消息、未读数。
- 13 项检查全部返回 200。

管理员看板显示 3 个活跃成员和 1 个隐私安全分组，不返回成员正文。练习详情包含 3 题和 1 个错题；教练消息包含 applied receipt；挑战地图包含 5 个节点。

## 6. 已知差异

- `GET /learning/today` 的 `ai_practice` 字段仍返回旧 `not_available`；已实现 AI 练习从 `/practice` 使用。
- 脚本创建的是可展示的合成数据，不代表真实生产 provider 或公网部署已完成。
- 最终评审账号由 T-SHIP-003/受控渠道交付；不要把密码写进公开视频、截图或 Git。

## 7. 清理

只清理演示数据库或演示环境中的 demo 命名空间。不要对共享测试库执行全库 drop，也不要删除未知词书卷。生产环境清理必须另立任务并由 A40 批准。
