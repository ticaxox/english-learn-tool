# AI 英语学习工具｜比赛技术文档

- 文档版本：T-DOC-002 / 2026-10-24
- 代码基线：`efc6bcbd2679eca02613a7143c68d04dddc36a59`
- 迁移 head：`844c0d89f737`
- 结论：M5 代码内硬化 `PASS_WITH_CONDITIONS`；完整 MVP `FAIL / NOT_READY`
- 页数：6 页（ReportLab 草稿 PDF 保存在任务证据目录，未纳入 Git；最终比赛模板复核 TODO）

## 摘要

AI 英语学习工具是面向学校、企业培训项目或学习组织内部成员的私有学习平台。产品把词书、FSRS 间隔复习、四类 AI 练习、AI 教练、每日闯关、通知和组织聚合看板整合为一个真实闭环。首版不开放自助注册，不支持陌生人社交或公开排行榜。

系统采用模块化单体：Vue 3 前端通过 `/api` 访问 FastAPI；PostgreSQL 是业务权威源，Redis 与 ARQ 承担队列、任务调度和短期并发协调；worker 与 scheduler 共享私有词书卷。管理员可以管理成员、词书和 AI 平台，但看不到成员答题正文、草稿、教练对话或私有词书正文。

本交付已完成认证、成员、词书、记忆、AI 平台、四类练习、教练 SSE/撤销、挑战、通知和看板，并通过真实 PostgreSQL/Redis/ARQ、API 和浏览器验证。容器/CI 基线已通过七服务健康、空库迁移、非 root 和回环端口检查。生产 URL、TLS、GHCR digest、生产备份恢复和最终视频仍未完成，因此不能把本文当作最终 MVP 验收通过。

## 1. 背景与目标

### 1.1 问题

组织内部英语学习常见问题包括：

- 词书、复习、练习和反馈分散在多个工具中，学习闭环不连续。
- 学习计划依赖人工安排，到期复习、今日新词和练习量缺少统一事实。
- AI 容易生成不可校验的题目、泄露答案或产生不可追溯的自动操作。
- 管理员需要组织级学习指标，但不应看到成员私密答题和对话正文。
- 比赛要求真实代码、真实数据、容器部署和可复现演示，不能用静态 mock。

### 1.2 目标

1. 提供管理员和成员两个真实角色闭环。
2. 用 FSRS 管理复习时间，用 AI 管理生成、评分和受控编排。
3. 用结构化 schema、业务校验和持久任务降低 AI 不确定性。
4. 用权限、审计、加密和聚合抑制保护组织隐私。
5. 用 Docker Compose、CI、迁移和可执行演示数据支持可复现验收。

### 1.3 非目标

- 不做公开注册、陌生人社交、公开排行榜。
- 不让 AI 直接写数据库或修改 FSRS `due_at`。
- 不把 mock、静态题、假评分或 PPT 当作产品演示。
- 不在本任务中修改业务源码、部署实现或质量门禁。

## 2. 角色与闭环

### 2.1 管理员

管理员可以：

- 登录、首次改密、刷新会话和退出。
- 创建/批量导入成员、启停成员、重置密码、调整角色。
- 保护最后一个启用管理员，避免组织失去管理入口。
- 创建或导入组织词书，查看持久导入/导出/删除任务。
- 配置 OpenAI 兼容 provider、模型、提示词、优先级和额度。
- 查看组织聚合学习指标和隐私安全分组。
- 查看审计记录和 AI 聚合用量。

管理员不能读取：

- 成员答题正文、作文、翻译或未提交草稿。
- AI 教练消息与 action 正文。
- 成员私有词书正文。
- AI provider 明文 Key。

### 2.2 成员

成员可以：

- 登录、首次改密、设置学习档案和通知偏好。
- 选择主词书、导入个人词书。
- 查看今日新词、到期复习和固定计划快照。
- 完成翻卡、选择、拼写三类记忆训练，真实更新 FSRS 状态。
- 完成填空、阅读、翻译、作文四类 AI 练习，保存草稿、提交、评分、查看记录和错题。
- 使用 AI 教练读取合法上下文、接收 SSE 回复、执行受控动作并撤销。
- 完成每日闯关、共享进度和终点 BOSS，接收通知并设置 DND。

### 2.3 端到端闭环

```text
管理员配置组织/成员/词书/provider
  → 成员激活词书并生成今日计划
  → 记忆训练更新 FSRS
  → AI 练习生成/提交/评分/错题
  → 教练读取上下文并执行受控动作
  → 每日闯关同步传统学习进度
  → 通知与组织聚合看板
```

## 3. 系统架构

### 3.1 运行拓扑

```text
Vue 3 / Vite / Pinia
        │ /api + SSE
        ▼
FastAPI /api/v1
  ├── auth / identity / audit
  ├── wordbooks / imports / exports
  ├── learning / memory / FSRS
  ├── ai / practice / coach / challenges
  ├── notifications / dashboard
  ├── PostgreSQL 16（权威数据）
  ├── Redis 7（队列/短期协调）
  └── ARQ worker + scheduler
        │
        └── 私有词书卷
```

反向代理默认只发布 `127.0.0.1:8080`。应用容器 UID/GID `10001`，使用只读根文件系统、`tmpfs /tmp`、`cap_drop: ALL` 和 `no-new-privileges`。

### 3.2 为什么是模块化单体

- 比赛交付周期短，单体更容易保持事务、权限和错误契约一致。
- AI、词书、练习和挑战共享同一套身份、计划和学习事件。
- worker/scheduler 独立部署，避免长任务阻塞 API。
- 后续可以按领域拆分，但当前不引入微服务分布式复杂度。

### 3.3 一致性

- PostgreSQL 保存业务状态、任务状态、额度和审计。
- Redis 只做队列、短期并发和缓存；不是唯一业务真相。
- 写操作使用幂等键/请求指纹。
- 词书、AI、练习评分、通知和挑战均有持久任务状态。

## 4. 数据模型

当前有 46 张应用表（另含 Alembic `alembic_version`），核心分组：

| 分组 | 代表表 | 作用 |
|---|---|---|
| 身份 | `users`、`user_profiles`、`refresh_tokens` | 账号、档案、会话 |
| 词书 | `wordbooks`、`wordbook_entries`、`wordbook_jobs` | 词书、条目、持久任务 |
| 学习/记忆 | `daily_plans`、`memory_sessions`、`user_word_states` | 计划、训练、FSRS |
| AI | `ai_providers`、`ai_prompts`、`ai_jobs`、`ai_usage_ledger` | provider、提示词、任务、额度 |
| 练习 | `practice_sessions`、`practice_questions`、`practice_submissions` | 四类练习和评分 |
| 教练 | `coach_conversations`、`coach_messages`、`coach_action_receipts` | 对话、SSE、撤销 |
| 通知 | `notifications`、`notification_outbox` | 收件箱、DND、去重 |
| 挑战 | `daily_challenge_plans`、`challenge_nodes`、`challenge_boss_results` | 地图、节点、BOSS |
| 审计 | `audit_logs` | 安全和操作追溯 |

关键不变量：

- 用户名规范化唯一；密码只存 Argon2id 哈希。
- 最后启用管理员不可删除、停用或降级。
- 同一词书内规范化 headword 唯一。
- `user_word_states` 对用户/词书/词条唯一。
- 每日计划对用户/日期唯一；每日挑战对用户/日期唯一。
- 通知对用户/dedupe key 唯一。
- 练习提交前不返回答案、解析或参考内容。

迁移链终点为 `844c0d89f737`；T-QA-004 已验证空库 upgrade/check/downgrade/re-upgrade，drift 为 0。

## 5. 身份、权限与安全

### 5.1 会话

- Access Token 15 分钟，前端只保存在内存。
- Refresh Token 30 天、随机、数据库只存哈希，HttpOnly Cookie，按 family 轮换。
- Cookie 写请求校验 Origin 与 CSRF 双提交。
- 改密、重置、停用、删除会撤销 Refresh 会话。
- 最后管理员保护在服务层和数据库测试中验证。

### 5.2 授权

- 角色守卫只用于前端体验，后端服务层再次校验。
- 私有词书、练习正文、草稿和教练消息按用户所有权隔离。
- 管理员看板只返回聚合；低于最小分组时抑制明细。
- 审计记录登录、管理操作和 AI action，不保存隐私正文。

### 5.3 AI 与上传安全

- provider Key 服务端加密，接口只返回掩码。
- Base URL 阻止云元数据地址、非法内网和重定向绕过。
- 上传使用随机文件名、大小/行数/解析限制；路径穿越返回 422。
- 模型输出经过 Pydantic 和业务校验，不直接作为 HTML 注入。
- 教练自动写入必须走受控 action receipt，支持 24h 撤销。

### 5.4 当前安全条件

- CSP 未配置：`F-SEC-01` CONDITIONAL。
- 生产备份审批/RPO/RTO 与恢复演练未完成：`F-AUDIT-01` CONDITIONAL。
- 版本标签/发布历史未完成：`F-GIT-01` CONDITIONAL。
- 公网 TLS、域名、WAF/边缘限流未验证。

## 6. 词书、FSRS 与今日计划

### 6.1 词书

- 支持组织词书和私有词书。
- CSV/JSON/TXT 预览、列映射、预览 token/hash、错误行报告。
- 确认导入写入持久任务，worker 处理，scheduler 回收 stale/中断任务。
- 导出支持 CSV、TXT、字体完整 PDF；删除后条目可见性立即阻断。
- 词书文件在 api/worker/scheduler 共享私有卷中，重启后保留。

### 6.2 FSRS

- FSRS 是复习时间唯一决策者。
- 服务端保存原始卡片 payload、算法版本、`due_at`、复习/遗忘次数。
- 翻卡、选择、拼写都提交学习事件；客户端不提交稳定性、难度或到期时间。
- 已记住/恢复使用服务端安全重排，避免恢复后立刻 overdue。

### 6.3 今日计划

- 按用户时区计算 `local_date`，固定新词/复习目标和计划快照。
- 档案修改从次日目标生效，不改变今天已固定计划。
- 今日任务、统计和挑战共享同一份学习事件/计划事实。
- 当前 `ai_practice` 摘要仍为旧 `not_available` 字段；真实 AI 练习入口是 `/practice`。

## 7. AI 平台

### 7.1 Provider

- OpenAI 兼容 provider：Base URL、模型、优先级、超时、默认/备用、连接检查。
- Key 加密保存，列表只返回掩码。
- provider 故障可切换备用；失败不返回假题或假评分。

### 7.2 提示词与任务

- 五类提示词：练习生成、主观评分、教练回复、挑战编排、JSON 修复。
- 管理员修改只影响未来任务；任务保存提示词快照。
- 任务保存输入上下文、幂等键、请求哈希、尝试/修复次数和错误。
- JSON 非法最多修复一次；逻辑不合法按上限重生成。
- 任务状态持久化，worker 重启后可恢复/回收。

### 7.3 额度与并发

- 教练消息、题目生成、主观评分分别计算每日额度。
- 额度账本记录 reserve、consume、release。
- 每人最多 2 个并发 AI 任务；取消/失败释放槽。
- 幂等重放不重复扣额度。

## 8. 四类 AI 练习

| 类型 | 生成 | 判分 | 防泄露 |
|---|---|---|---|
| 填空 | 结构化生成 | 后端客观判分 | 提交前不返回正确选项/解析 |
| 阅读 | 结构化生成 | 后端客观判分 | 文章/问题数量、实体 ID 校验 |
| 翻译 | 结构化生成 | AI 主观评分 | 提交前不返回参考译文/维度分 |
| 作文 | 结构化生成 | AI 主观评分 | 提交前不返回参考范文/评分 |

练习支持：

- 草稿版本和旧标签页冲突提示。
- 提交幂等、记录筛选、错题本、本人批量删除。
- 低于 60 分的主观题进入错题。
- 失败态保留真实错误码和 Request ID，不生成假题/假分数。

## 9. AI 教练

- 长期会话、消息游标、202 消息任务、SSE 增量、usage 和断线恢复。
- 合法上下文：当前页面、实体 ID、本人学习事件、今日计划、FSRS 概况和主动输入。
- 禁止上下文：其他成员数据、Key、密码、令牌、管理员配置。
- 受控 action 示例：调整今日计划、调整通知偏好、开始练习、激活词书、标记复习重点。
- action receipt 保存 before/after 状态、摘要和 24h 撤销期限。
- 撤销前重新校验；状态冲突返回解释，不强行回滚。

## 10. 每日闯关与共享进度

- 后端先计算今日新词、到期词、合法实体和练习额度。
- AI 只编排节点顺序、词条分配、可选支线和文案。
- 节点类型：复习、新词、词义训练、AI 练习、BOSS、可选支线。
- 地图生成后当天锁定；失败显示真实失败和重试。
- 传统学习完成会同步节点进度；BOSS 提交幂等，刷新后仍可读取结果。
- T-QA-004 已验证 5 节点地图、2 个完成状态、BOSS 结果持久化与刷新重入。

## 11. 通知、看板与隐私

### 11.1 通知

- 游标分页、未读筛选、单条/全部已读、未读数和类别偏好。
- DND、每日非 AI 上限、AI 完成/失败例外。
- `dedupe_key` 防止重复；正文按纯文本渲染。
- AI 失败通知保留真实错误，不伪装成功。

### 11.2 管理员看板

- 组织聚合：成员数、活跃率、学习时长、计划完成率、练习提交/正确率、错题、AI 任务、挑战完成。
- 分组按部门/学习组聚合；最小分组为 3，低于阈值抑制。
- 管理员只看到聚合，不看到成员答题正文、草稿、教练对话或私有词书。

### 11.3 演示数据

可执行脚本 `docs/competition/seed_demo_data.py` 创建：

- `demo_admin`、`demo_member`、`demo_member2`、`demo_member3`。
- 20 词合成组织词书、60 个记忆状态、3 个每日计划。
- 1 个已完成 3 题练习、1 个教练会话、5 个挑战节点、3 条通知。

脚本只删除固定 demo UUID 命名空间内的数据，支持重复初始化；密码从环境变量读取，不提交到仓库。

## 12. 测试、性能与部署

### 12.1 全量验证

- 后端：156 passed，Ruff lint/format PASS。
- 前端：310 passed，`npm ci`/build PASS，0 已知漏洞。
- M3：API 54/54，浏览器 13/13。
- M4R：API 21/21，浏览器 14/14。
- 性能：读 P95 0.031 ms、提交 47 ms、5000 行导入 1.92 s、SSE 首事件 31 ms。
- 迁移/备份：空库迁移、downgrade/re-upgrade、合成库恢复通过。
- 47 门禁：40 PASS / 3 CONDITIONAL / 4 FAIL / 0 NOT_RUN。

### 12.2 演示数据验证

- 首次初始化和重复初始化 PASS。
- 一次性独立数据库 revision `844c0d89f737`。
- 13 项真实 API 读取均返回 200。
- 管理员看板 3 个活跃成员、1 个隐私分组。
- 练习详情 3 题、1 个错题；教练消息含 applied receipt；挑战 5 节点。

### 12.3 部署状态

- Compose/CI 已验证七服务、空库迁移、非 root、回环端口和健康路由。
- T-SHIP-002 仍 RUNNING；公网 URL、TLS、GHCR digest、生产备份恢复和回滚未冻结。
- 本机 `docker` 是 `wslc`，无 Compose；容器运行证据来自 GitHub Actions 干净 runner。

## 13. 创新点

1. **FSRS 与 AI 决策分离**：AI 负责生成、评分和编排，FSRS 保留复习时间唯一决策权。
2. **结构化 AI 合同**：JSON Schema + Pydantic + 业务校验 + 持久任务，失败不产生假题。
3. **受控可撤销教练**：AI action 有 receipt、before/after 和 24h 撤销，不是无限权限代理。
4. **共享学习事实**：传统学习、今日计划、挑战和看板共享事件/快照，不是多套数据。
5. **隐私优先看板**：管理员看聚合，不看正文；小分组自动抑制。
6. **可复现比赛交付**：真实 Git/PR/CI、Compose、合成数据脚本、QA 截图和视频脚本。

## 14. 局限与后续

- T-SHIP-002 未完成：无公网 URL、TLS、GHCR digest、生产恢复和回滚证据。
- CSP、生产备份、版本发布仍为 CONDITIONAL。
- Today 页面 AI 摘要仍是旧字段；修复需代码任务。
- 最终视频、公网截图和评审账号未完成。
- 许可证未选择，公开提交前需 A00 决策。
- 完整 MVP 仍为 `FAIL / NOT_READY`，本文不替代 A00 最终验收。

## 15. 证据索引

- T-QA-004 报告：`ai-workspace/10-collaboration/reports/T-QA-004-TEST.md`
- T-QA-004 证据：`ai-workspace/04-qa/evidence/T-QA-004/README.md`
- 演示数据验证：`ai-workspace/10-collaboration/sessions/A50-DOCS/test-artifacts/T-DOC-002/seed-verification.json`
- 截图清单：`docs/competition/screenshots/README.md`
- API：`backend/openapi.json` / `docs/api.md`
- 迁移：`backend/alembic/versions/`
- 质量门禁：`tests/quality-baseline/acceptance-gates.json`

## 附录：术语

- **FSRS**：服务端间隔复习调度算法。
- **DND**：免打扰时间。
- **SSE**：Server-Sent Events，用于教练流式回复。
- **receipt**：AI 受控 action 的可追溯回执。
- **202**：任务已接受，不代表业务已完成。
