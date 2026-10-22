# 数据模型

- 事实基线：`caa731c`；容器/CI 证据对应 `a5bf49b` / run `39801657963`
- 当前迁移：`backend/alembic/versions/20261022_0001_initial.py`
- 当前 revision：`20261022_0001`

## 1. 当前数据库事实

当前数据库只新增一个技术基线表：

```text
system_metadata
├── id           UUID, primary key
├── key          varchar(100), unique, not null
├── value        jsonb, not null, default {}
├── created_at   timestamptz, not null, default now()
└── updated_at   timestamptz, not null, default now()
```

该表用于验证迁移、SQLAlchemy async session 和数据库基础设施，不是业务实体。除该表外，当前仓库**没有**用户、词书、FSRS、练习、AI、教练或挑战数据表。

## 2. 通用建模约定

规划中的业务表应遵循以下约定：

- 主键统一使用 UUID。
- 时间统一使用 UTC `TIMESTAMPTZ`，API 输出 RFC3339。
- 业务表包含 `created_at`、`updated_at`，需要时增加审计字段。
- 用户删除、练习记录删除等明确要求硬删除的场景不使用软删除替代。
- 字符串枚举同时使用数据库约束和 Pydantic 校验。
- 关键关系必须使用独立列或关联表，不能全部塞进 JSONB。
- JSONB 仅用于模型原始响应、配置快照和非高频筛选上下文。
- 所有模型变化必须通过 Alembic migration，不得只改 ORM。
- 核心唯一约束需要在数据库层面落实，不能只依赖服务层检查。

## 3. 目标业务表（规划中）

以下表来自 v1.1 产品基线，当前**尚未实现**：

| 领域 | 规划表 |
|---|---|
| 账号与系统 | `organization_settings`、`users`、`user_profiles`、`refresh_tokens`、`audit_logs`、`idempotency_keys`、`import_previews` |
| 词书 | `wordbooks`、`wordbook_entries`、`word_senses`、`word_examples` |
| 记忆与计划 | `user_word_states`、`memory_sessions`、`memory_session_items`、`memory_events`、`learning_events`、`study_activity_buckets`、`daily_study_plans`、`daily_plan_words` |
| AI 练习 | `practice_sessions`、`practice_questions`、`practice_answers`、`practice_evaluations` |
| AI 平台 | `ai_providers`、`ai_prompts`、`ai_jobs`、`ai_usage_ledger` |
| AI 教练 | `coach_conversations`、`coach_messages`、`coach_context_snapshots`、`coach_action_receipts` |
| 通知 | `notifications`、`notification_preferences` |
| 每日挑战 | `daily_challenge_plans`、`challenge_nodes`、`challenge_node_progress`、`challenge_plan_contexts`、`challenge_boss_results` |

具体字段、枚举、索引和约束由产品基线与后续任务卡定义；本表不能作为已存在的数据库结构引用。

## 4. 关键关系与约束（目标）

### 用户与权限

- `users.username_normalized` 唯一。
- 系统必须至少保留一个启用管理员。
- 删除用户时事务级清理令牌、私有词书、学习状态、练习、教练对话、通知、AI 任务和挑战记录。
- 管理员审计日志不得保存答题正文、作文、翻译、教练消息或 API Key。

### 词书与记忆

- `wordbook_entries` 在 `(wordbook_id, normalized_headword)` 上唯一。
- 用户单词状态在 `(user_id, wordbook_id, word_entry_id)` 上唯一。
- 同一用户同时只有一本激活主词书；历史进度不因切换而被删除。
- `user_word_states` 保存 FSRS Card 状态、到期时间、算法版本和 mastered/suspended 时间。
- 所有 FSRS 更新必须经过统一服务入口，禁止其他模块直接修改 `due_at`。

### 每日计划

- `daily_study_plans` 在 `(user_id, local_date)` 上唯一。
- 成功生成后当天固定；档案修改从次日生效。
- 新词、到期词和合法任务集合保存快照，刷新不能重新随机。
- 计划快照后的新增到期词作为额外复习，不计入已固定的闯关目标。

### 练习与答案

- 题目、用户答案、草稿和评分分别存储，草稿需要版本号或乐观锁。
- 提交前序列化层必须剥离正确答案、解析和参考内容。
- 提交幂等由 `Idempotency-Key` 与数据库唯一约束共同保证。
- 主观题评分失败不得写入默认分数。

### AI 额度与任务

- `ai_jobs` 是异步任务状态源；Redis 队列不是唯一真相。
- `ai_usage_ledger` 记录 reserve、consume、release。
- worker 崩溃重试不得重复产生付费 AI 调用。
- 管理员只能查看聚合用量，不读取用户正文。

### 挑战

- `daily_challenge_plans` 对 `(user_id, local_date)` 唯一。
- 每张地图只允许一个成功结果；失败可使用同一计划重试。
- 挑战节点引用后端提供的合法词条、会话和任务模板。
- 终点挑战结果用于次日计划参考，不是当天通关门槛。

## 5. 迁移规则

```powershell
cd backend
uv run alembic revision --autogenerate -m "describe change"
uv run alembic upgrade head
uv run alembic check
```

要求：

1. 人工审查自动生成的 migration，确认索引、约束、默认值和命名。
2. 每个 migration 提供可执行的 `downgrade()`。
3. 破坏性变更说明数据迁移、兼容窗口和回滚限制。
4. 合入前在不含业务数据的新库中回放迁移；CI 已在 `a5bf49b` 的干净 runner 上完成容器空库迁移。
5. 不得把 `system_metadata` 当作业务数据的兜底表。

## 6. 当前验证证据

在 `caa731c` 工作树使用一次性独立 PostgreSQL 数据库执行：

- `uv run alembic upgrade head`：从空库升级成功。
- `uv run alembic check`：`No new upgrade operations detected.`
- `uv run pytest`：18 passed，其中数据库测试确认 revision 为 `20261022_0001`，`system_metadata` 存在。

容器内证据：`a5bf49b` 的 GitHub Actions run `39801657963` 第 2 次尝试中，Compose 一次性迁移容器从空库升级成功，数据库 revision 为 `20261022_0001`，并确认 `system_metadata` 表存在。发布镜像和云部署仍不属于已验证范围。
