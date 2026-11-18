# AI 链路

- 代码基线：`main` @ `1cea3ff` / `v0.1.7`
- 相关代码：`app/services/ai_jobs.py`、`ai_providers.py`、`ai_security.py`、`ai_prompts.py`、`ai_usage.py`、`knowledge.py`、`coach.py`、`coach_tools.py`、`challenge.py`

## 1. Provider

- 只支持 **OpenAI 兼容**接口：`POST {base_url}/chat/completions`、`GET {base_url}/models`、`POST {base_url}/embeddings`。
- 两种 `kind`：`chat` 与 `embedding`；embedding 任务优先选 embedding provider，缺失时回退到旧 chat provider 的 `embedding_model`。
- **BYOK**：`ai_providers.owner_id` 决定归属。学习者的任务只使用自己的 provider；管理员配置仅供管理员自己。
- 选择顺序：enabled → kind 匹配 → 按 `priority` → `is_default` → `created_at`。
- 结构化输出：优先 `response_format: json_schema`，上游 400/422 时降级为 `json_object`；每个任务最多一次 JSON 修复。
- 安全：Base URL 经过校验，阻止云元数据地址与私有网段（`AI_ALLOW_PRIVATE_PROVIDER_URLS` 仅限受控测试）；重定向限制同源次数。
- 重试：`ai_provider_retry_limit` 默认 2，退避 0.25s；超时按 provider 配置。

## 2. 任务平台

`ai_jobs` 是唯一入口。创建任务时写入：任务类型、prompt 快照、幂等键、请求哈希、provider、额度项与终态。

| 任务类型 | 用途 | 额度类型 |
|---|---|---|
| `practice_generation` | 生成练习题目 | `question_generation` |
| `subjective_grading` | 主观题评分 | `subjective_grading` |
| `coach_reply` | 教练回复 | `coach_messages` |
| `conversation_turn` | 对话型练习的一轮 | `coach_messages` |
| `challenge_plan` | 每日闯关地图 | 不单独计费 |
| `json_repair` | 修复模型输出 | 不单独计费 |

状态：`queued` → `running` → `succeeded` / `failed` / `stale` / `cancelled`。scheduler 会回收超时任务并释放额度。

幂等：`(user_id, idempotency_key)` 唯一；相同键重复提交返回同一任务。

## 3. 提示词

- `ai_prompts` 按 `prompt_key` 存储模板，有版本与启用状态；任务创建时把当时的模板写入 job 快照，之后再改提示词不影响在途任务。
- 管理员可在 `/admin/ai/prompts` 查看与更新；个人版用户不直接编辑。

## 4. 额度与并发

- 额度按**任务次数**计，不按 token 或金额。
- 默认每日本地日：教练消息 100、出题 20、主观评分 50；`user_profiles.ai_quota_limits` 可按用户覆盖，`-1` 为不限。
- 账本：reserve → consume（成功）/ release（失败、取消、stale）；`(job_id, quota_item)` 唯一，防止重复记账。
- 并发：每用户最多 2 个进行中的 AI 任务（Redis ZSET + Lua）；超出的任务排队或返回限流错误。
- 用量查询：`GET /ai/usage/me`、`GET /me/progress`、`GET /admin/ai/usage`。

## 5. RAG 与知识库

### 5.1 书架模型

- 公共书架（管理员维护真题，按难度）与个人书架（学习者自己导入）。
- 检索只读该学习者可读的书架：公共真题架、目标难度架、个人架。

### 5.2 分块与向量

- 题号感知分块：以编号题为单位，长题按 900 字符切分，重叠 120，单文档最多 400 块。
- embedding 可选；未配置 embedding provider 时只用关键词。
- 向量以 Postgres `ARRAY(Float)` 存在 `knowledge_chunks.embedding`，不使用 pgvector。

### 5.3 检索

- 查询时对候选 chunk 逐条打分：`score = 0.6 × max(关键词分, 余弦) + 0.4 × min(关键词分, 余弦)`。
- 阈值 0.12，最多返回 6 条，带文档出处与 chunk 序号。
- 练习生成会引用 3 条片段；教练通过 `search_knowledge` 工具检索。
- 规模边界：线性扫描适合千级 chunk；万级应迁移 pgvector 与 ANN 索引。

## 6. 教练

- 会话、消息、附件、记忆快照、SSE 事件日志全部落库。
- 回复任务 202；前端订阅 `/coach/streams/{message_id}`，支持 `Last-Event-ID` 续传。
- 受控动作共 8 个：

| 工具 | 作用 |
|---|---|
| `adjust_daily_plan` | 调整新词量与学习时长 |
| `search_knowledge` | 检索可读书架的原文片段 |
| `list_knowledge` | 列出可读书架与文档 |
| `read_knowledge_document` | 读取指定文档内容 |
| `start_practice` | 直接开始一组练习 |
| `activate_wordbook` | 启用一本词书 |
| `create_practice_questions` | 按主题生成练习题 |
| `mark_review_focus` | 标记需要重点复习的词 |

- 每个动作生成 before/after 回执，24 小时内可通过 `/coach/action-receipts/{id}/undo` 撤销。

## 7. 闯关生成

- 服务端先准备上下文：今日新词/到期词、合法节点类型、额度、可选支线。
- AI 只决定顺序与文案，节点类型必须落在允许集合：REVIEW / NEW_WORDS / WORD_DRILL / AI_PRACTICE / BOSS / OPTIONAL_SIDE。
- 输出经 Pydantic 与业务校验；计划当日锁定，重生成需显式接口。

## 8. 失败码

| 错误码 | 含义 |
|---|---|
| `AI_PROVIDER_UNAVAILABLE` | 没有可用 provider，或上游 5xx 被归为暂不可用 |
| `AI_PROVIDER_TIMEOUT` | 上游超时 |
| `AI_PROVIDER_NETWORK` | 网络错误 |
| `AI_PROVIDER_AUTH_FAILED` | Key 无效 |
| `AI_PROVIDER_URL_BLOCKED` | URL 命中拦截规则 |
| `AI_OUTPUT_INVALID` | 输出无法通过 schema/业务校验 |
| `AI_JOB_TIMEOUT` / `AI_JOB_STALE` | 任务超时或被回收 |
| `AI_INTERNAL_ERROR` | 其他内部错误 |

> 历史真实数据（2026-11-12 转储）显示失败率约 59%，主要来自第三方中转站的超时与不可达，而不是没有配置 Key。

## 9. 配置项

| 变量 | 默认 | 说明 |
|---|---|---|
| `AI_PROVIDER_RETRY_LIMIT` | 2 | 单 provider 重试次数 |
| `AI_PROVIDER_RETRY_BACKOFF_SECONDS` | 0.25 | 退避 |
| `AI_DAILY_COACH_MESSAGES` | 100 | 教练消息额度 |
| `AI_DAILY_QUESTION_GENERATION` | 20 | 出题额度 |
| `AI_DAILY_SUBJECTIVE_GRADING` | 50 | 主观评分额度 |
| `AI_ALLOW_PRIVATE_PROVIDER_URLS` | false | 允许私有 provider 地址 |

（域名与 Key 在页面配置，不进入环境变量。）
