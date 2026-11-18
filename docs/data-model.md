# 数据模型

- 代码基线：`main` @ `1cea3ff` / `v0.1.7`
- 迁移 head：`20261114_0032`（40 个 revision，单头）
- 数据表：59 张（不含 `alembic_version`）
- 数据库：PostgreSQL 16；ORM：SQLAlchemy 2 async；迁移：Alembic

## 1. 表分组

### 身份与审计（6）

| 表 | 用途 |
|---|---|
| `users` | 账号、角色、状态、密码哈希、最后登录 |
| `user_profiles` | 显示名、学习目标、难度偏好、额度覆盖、通知偏好 |
| `refresh_tokens` | Refresh Token 哈希、轮换链、IP/UA、撤销 |
| `personal_access_tokens` | MCP 与外部调用的个人令牌（只存哈希） |
| `audit_logs` | 登录、刷新、管理操作等审计事件 |
| `import_previews` | 成员批量导入的预览与结果 |

### 词书（7）

`wordbooks`、`wordbook_definitions`、`wordbook_entries`、`wordbook_examples`、`wordbook_import_previews`、`wordbook_jobs`、`wordbook_activations`。

- 词书归属用户；内置词书以系统定义形式提供。
- 导入走预览令牌与持久 `wordbook_jobs`；文件落私有卷，库里只存元数据。

### 学习与记忆（10）

`daily_plans`、`daily_plan_words`、`daily_activities`、`learning_heartbeats`、`memory_configs`、`memory_sessions`、`memory_session_items`、`memory_events`、`user_word_states`、`mistake_flags`。

- `user_word_states` 保存每张卡的 FSRS 状态（难度、稳定度、到期时间等）。
- `memory_events` 逐题记录 shown / answer / mastered，带客户端事件键，重复提交不重复推进调度。

### 练习（8）

`practice_sessions`、`practice_questions`、`practice_submissions`、`practice_events`、`practice_generations`、`practice_deletions`、`practice_pool_items`、`practice_conversation_turns`。

- 会话状态：`generating` / `ready` / `submitted` / `failed` / `cancelled`；提交状态：`scoring` / `completed` / `failed`。
- 预生成池按（题型 × 难度 × 来源）存放，新会话优先领取。

### AI 平台（6）

`ai_providers`、`ai_prompts`、`ai_jobs`、`ai_job_events`、`ai_usage_ledger`、`ai_memories`。

- `ai_providers` 按 `owner_id` 归属；`kind` 为 `chat` 或 `embedding`；Key 以 AES-GCM 密文保存。
- `ai_jobs` 保存任务类型、提示词快照、请求哈希、provider、终态与错误码。
- `ai_usage_ledger` 以 `(job_id, quota_item)` 唯一，记录 reserve / consume / release。

### 教练（7）

`coach_conversations`、`coach_messages`、`coach_stream_events`、`coach_attachments`、`coach_action_receipts`、`coach_context_snapshots`、`coach_memories`。

- 消息任务 202；`coach_stream_events` 是 SSE 的持久事件源。
- 受控动作有 before/after 回执，24 小时内可撤销。

### 闯关（5）

`daily_challenge_plans`、`challenge_plan_contexts`、`challenge_nodes`、`challenge_node_progress`、`challenge_boss_results`。

- `(user_id, local_date)` 唯一：每人每天一张图。
- 节点按 `order_index` 与 `client_key` 唯一；计划生成后当日锁定。

### 游戏化（4）

`user_game_stats`、`xp_events`、`daily_quests`、`user_achievements`。

- `xp_events` 记录每次奖励来源，服务端按来源去重，避免重复计分。
- 等级、连续天数、灯油、任务与徽章都从事件与统计表推导。

### 知识库（3）

`knowledge_documents`、`knowledge_chunks`、`knowledge_folders`。

- 文件夹可嵌套；文档有难度、来源与索引状态。
- `knowledge_chunks.embedding` 为可选向量（Postgres 数组），未生成时为空。

### 通知与系统（2 + 1）

`notifications`、`notification_outbox`、`system_metadata`。

- 通知后端完整；个人版前端当前没有通知入口与路由。

## 2. 关键约束与不变量

| 不变量 | 实现 |
|---|---|
| AI 任务幂等 | `ai_jobs` 唯一约束 `(user_id, idempotency_key)` |
| 额度不重复记账 | `ai_usage_ledger` 唯一 `(job_id, quota_item)` |
| provider 名称不重复 | `ai_providers` 唯一 `(owner_id, name_normalized)`；默认 provider 必须 enabled |
| 每日一图 | `daily_challenge_plans` 唯一 `(user_id, local_date)` |
| 节点不重复 | `challenge_nodes` 唯一 `(plan_id, order_index)` 与 `(plan_id, client_key)` |
| 记忆偏好唯一 | `ai_memories` 唯一 `(user_id, memory_key)` |
| 练习池不超发 | 领取时在事务内更新 `practice_pool_items` 状态 |
| FSRS 只在服务端 | 客户端只上报答题结果，间隔与到期由服务端计算 |

## 3. 迁移链

```text
0001 → 0002 → f1b8d947271c → … → 844c0d89f737 → 0003 → … → 0026
      ↘ 20261110_0027（merge 0026 与 844c0d89f737）
        → 0028 conversation practice
        → 0029 embedding provider（ai_providers.kind）
        → 0030 knowledge folders
        → 0031 knowledge nesting
        → 0032 difficulty under goals（当前 head）
```

- 迁移在启动时由 `tests/conftest.py` 或 Compose `migrate` 服务执行；生产部署脚本会在迁移前备份。
- `alembic heads` 必须只有 `20261114_0032`；新增迁移应从该 head 续接，避免多头。

## 4. 隐私与敏感字段

- 密码只存 Argon2id 哈希；Refresh Token 与个人访问令牌只存哈希。
- AI provider Key 以 `SECRET_ENCRYPTION_KEY` 派生的 AES-GCM 密文保存，接口只回掩码。
- 管理看板只返回聚合指标，不返回答题正文、草稿、教练对话或私有词书正文。
- 真实用户数据、密钥与生产连接串不得进入仓库或文档。
