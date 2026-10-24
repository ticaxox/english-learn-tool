# 数据模型

- 交付基线：`efc6bcbd2679eca02613a7143c68d04dddc36a59`
- 迁移 head：`844c0d89f737`
- 应用表：46 张（另含 Alembic `alembic_version`）
- 权威源：PostgreSQL 16；Redis 只做队列、短期协调和缓存
- 隐私：仓库只包含 schema、迁移和合成数据说明，不包含真实成员数据

## 1. 领域分组

### 系统与审计

- `system_metadata`
- `audit_logs`
- `alembic_version`

### 身份与会话

- `users`
- `user_profiles`
- `refresh_tokens`

### 词书与后台任务

- `wordbooks`
- `wordbook_entries`
- `wordbook_definitions`
- `wordbook_examples`
- `wordbook_activations`
- `wordbook_import_previews`
- `wordbook_jobs`

### 学习、记忆与计划

- `daily_plans`
- `daily_plan_words`
- `daily_activities`
- `learning_heartbeats`
- `memory_configs`
- `memory_sessions`
- `memory_session_items`
- `memory_events`
- `user_word_states`
- `mistake_flags`

### AI 平台

- `ai_providers`
- `ai_prompts`
- `ai_jobs`
- `ai_job_events`
- `ai_usage_ledger`

### 练习

- `practice_sessions`
- `practice_generations`
- `practice_questions`
- `practice_submissions`
- `practice_events`
- `practice_deletions`

### 教练

- `coach_conversations`
- `coach_messages`
- `coach_stream_events`
- `coach_context_snapshots`
- `coach_action_receipts`

### 通知

- `notifications`
- `notification_outbox`

### 每日挑战

- `daily_challenge_plans`
- `challenge_plan_contexts`
- `challenge_nodes`
- `challenge_node_progress`
- `challenge_boss_results`

## 2. 关键不变量

### 身份

- 用户名规范化后唯一。
- 密码只存 Argon2id 哈希。
- 最后一个启用管理员不可删除、停用或降级。
- Refresh Token 只存哈希；轮换/重放检测由服务端完成。

### 词书

- `visibility=organization` 时 `owner_id` 必须为空；私有词书必须有 owner。
- 同一词书内规范化 headword 唯一。
- 删除词书后条目不再可见；后台删除任务保留可追溯状态。
- 词书文件使用私有卷，不通过公开静态目录暴露。

### 学习与 FSRS

- `user_word_states` 对 `(user_id, wordbook_id, entry_id)` 唯一。
- `due_at`、`fsrs_card` 和复习间隔只由后端 FSRS 服务写入。
- 今日计划按用户时区和 `local_date` 固定；档案修改从次日目标生效。
- 学习事件带幂等键，重复提交不能重复推进卡片。

### AI

- provider Key 使用服务端加密；数据库保存密文与掩码，不保存明文。
- AI 任务、额度预留/消费/释放和错误状态持久化。
- 提示词快照在任务创建时冻结；后续提示词修改只影响未来任务。
- 题目提交前不能通过 API 返回答案、解析或参考内容。

### 教练与挑战

- 教练消息和 stream event 按会话/消息序号唯一。
- action receipt 保存 before/after 状态，撤销前重新校验当前状态。
- 每日挑战对 `(user_id, local_date)` 唯一；节点顺序和 client key 唯一。
- BOSS 提交幂等；完成结果刷新后仍可读取。

### 通知

- `(user_id, dedupe_key)` 防止重复通知。
- 非 AI 通知受 DND 与每日上限约束；AI 失败/完成按产品规则保留例外。
- 通知正文按纯文本渲染，不把模型 Markdown 直接注入 HTML。

## 3. 迁移链

```text
20261022_0001
  → 20261022_0002
  → f1b8d947271c
  → 38236bfd0899
  → c5ab093fd0f9
  → fbff60ce778f
  → 297df76b0133
  → cd6e2b2dd57e
  → 0bea27d11d11
  → 844c0d89f737
```

T-QA-004 已执行空库 upgrade、`alembic check`、downgrade 和 re-upgrade，drift 为 0。

## 4. 备份、恢复与删除

- 合成库 `pg_dump`/`pg_restore` 已验证关键表计数一致。
- 演示环境备份/RPO/RTO 与数据库/词书恢复已由 T-SHIP-002/003 验证；稳定生产 SLA 和主密钥分离仍需最终复核。
- 应用回滚不等于数据库回滚；结构不兼容时必须停止并走单独批准的数据恢复流程。
- 词书卷是私有数据资产，必须与 PostgreSQL 备份策略一起设计。
- 删除演示数据时只删除固定 demo 命名空间，不执行全库清理。

## 5. 隐私边界

| 数据 | 成员本人 | 管理员 |
|---|---|---|
| 账号状态、学习档案 | 可读/可改 | 可读必要聚合/管理字段 |
| 私有词书正文 | 可读本人 | 不可读 |
| 答题、作文、翻译正文 | 可读本人 | 不可读 |
| 未提交草稿 | 可读本人 | 不可读 |
| 教练消息与 action 正文 | 可读本人 | 不可读 |
| 组织学习时长/完成率 | 可读本人 | 可读聚合，低于最小分组时抑制 |

## 6. 演示数据

可执行脚本：[`competition/seed_demo_data.py`](competition/seed_demo_data.py)

脚本只创建固定 demo UUID 命名空间内的数据，支持重复初始化；不会删除非 demo 用户或词书。验证记录见 `ai-workspace/10-collaboration/sessions/A50-DOCS/test-artifacts/T-DOC-002/seed-verification.json`。
