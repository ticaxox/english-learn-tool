# 演示说明

- 交付基线：`efc6bcbd2679eca02613a7143c68d04dddc36a59`
- 临时公网预览：`http://23.94.141.170:18080`（`v0.1.1`，commit `a6ac195`，主题 Whisker Crumb；HTTP，不是稳定 HTTPS）
- 演示数据脚本：[`competition/seed_demo_data.py`](competition/seed_demo_data.py)
- 演示数据说明：[`competition/demo-data.md`](competition/demo-data.md)
- 截图清单：[`competition/screenshots/README.md`](competition/screenshots/README.md)
- 视频脚本：[`competition/demo-video-script.md`](competition/demo-video-script.md)

## 1. 当前可演示范围

已可由真实 API/浏览器展示：

- 管理员登录、成员管理、词书管理、AI provider/提示词、组织看板。
- 成员登录、学习档案、词书激活、今日计划、记忆训练。
- 四类 AI 练习、提交/评分、练习记录、错题。
- AI 教练 SSE、受控 action receipt、撤销。
- 每日闯关、节点状态、BOSS 结果。
- 通知、DND、偏好和未读数。
- 失败态、Request ID、隐私边界和管理员聚合看板。

## 2. 演示账号

脚本创建以下合成账号：

| 用户名 | 角色 | 用途 |
|---|---|---|
| `demo_admin` | admin | 管理员流程、看板、AI 配置 |
| `demo_member` | member | 主要成员闭环 |
| `demo_member2` | member | 组织聚合/多成员对比 |
| `demo_member3` | member | 组织聚合/最小分组 |

公网预览使用 `demo_admin`、`demo_member`；密码只从 A40 的 ACL 本地凭据文件安全获取，不写入仓库/文档/截图/视频。本地脚本仍通过 `DEMO_ADMIN_PASSWORD` 与 `DEMO_MEMBER_PASSWORD` 环境变量设置，不要把真实管理员密码用于演示。

## 3. 初始化

公网预览已由 A40 准备合成数据，不要在远端重复执行 seed。若需要本地/独立环境演示，再执行以下命令。

在一次性或专用演示数据库执行：

```powershell
$env:DEMO_SEED_CONFIRM = 'YES'
$env:DEMO_ADMIN_PASSWORD = '<unique demo admin password>'
$env:DEMO_MEMBER_PASSWORD = '<different unique demo member password>'
uv run --project backend python docs/competition/seed_demo_data.py --apply
```

脚本只删除固定 demo UUID 命名空间内的数据；不会删除非 demo 用户或词书。重复执行会重建同一套合成数据。

## 4. 推荐演示路径

### 管理员（约 3 分钟）

1. 打开 `http://23.94.141.170:18080`，登录 `demo_admin`。
2. 打开成员管理，展示 3 个成员、角色/状态和隐私安全的聚合字段。
3. 打开词书列表，展示 20 词组织词书。
4. 打开 AI provider/提示词页面，展示 Key 掩码、模型、提示词和连接检查入口。
5. 打开组织看板，展示 3 个成员聚合、分组隐私和最小分组抑制。
6. 说明管理员看不到成员答题正文、草稿、教练对话和私有词书正文。

### 成员（约 4 分钟）

1. 登录 `demo_member`。
2. 展示今日计划、到期复习和新词目标。
3. 打开记忆训练，完成一次翻卡/选择/拼写。
4. 打开 AI 练习，展示填空练习、提交前无答案、提交后结果和错题。
5. 打开练习记录，展示已完成 3 题、66.67 分和 1 个错题。
6. 打开 AI 教练，展示 SSE 回复、`adjust_daily_plan` action receipt 和撤销入口。
7. 打开每日闯关，展示 5 个节点、2 个已完成、3 个未完成状态。
8. 打开通知，展示 3 条合成通知和未读数。

## 5. 失败态与边界

可展示：

- AI provider 不可用时的真实错误码和 Request ID。
- 题目生成失败不出现假题。
- 未登录访问受保护页面时跳转登录。
- 成员访问管理员路由被拒绝。
- 管理员看板在成员不足最小分组时抑制分组明细。

不可宣称：

- 稳定 HTTPS、TLS 或长期生产 SLA 已完成；当前只是临时 HTTP IP 预览。
- 最终视频已录制完成。
- 真实生产 AI 模型效果已被验证。
- 完整 MVP 已 PASS。

## 6. 已知差异

`GET /learning/today` 的 `ai_practice` 字段仍返回旧 `not_available`；已实现的 AI 练习从 `/practice` 进入。演示时不要用 Today 摘要证明 AI 练习未实现，也不要把该旧字段说成生产故障已修复。

## 7. 录屏前检查

- 使用合成数据；允许显示本次临时 IP 预览地址，但不得显示 ACL 密码、Token、真实成员或私有正文。
- 不显示 `.env`、Key、密码或令牌。
- 固定 `v0.1.1`、commit `a6ac195` 和演示数据版本。
- 截图/视频与当前代码一致。
- 稳定 HTTPS、最终截图和视频仍保留 `TODO`。
