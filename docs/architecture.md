# 架构与当前边界

- 交付基线：`efc6bcbd2679eca02613a7143c68d04dddc36a59`（T-QA-004 冻结）
- 迁移 head：`844c0d89f737`
- 当前形态：模块化单体 + 独立 worker/scheduler + Vue SPA
- 完整 MVP：`FAIL / NOT_READY`；本文描述的是已实现代码，不是最终验收结论

## 1. 运行拓扑

```text
┌──────────────────────────── Browser ────────────────────────────┐
│ Vue 3 + Vite + Pinia + Vue Router                              │
│ 认证、词书、今日计划、记忆、练习、教练、挑战、通知、管理员页面      │
└──────────────────────────────┬─────────────────────────────────┘
                               │ /api + SSE
                               ▼
┌──────────────────────────── FastAPI ────────────────────────────┐
│ Request ID / 统一错误 / 安全头 / CORS / 认证与 CSRF              │
│ auth · users · wordbooks · learning · memory · practice · ai     │
│ coach · challenges · notifications · dashboard · audit          │
└──────────────┬───────────────────────────────┬──────────────────┘
               │                               │
               ▼                               ▼
       PostgreSQL 16                    Redis 7 + ARQ
       46 张应用表                      wordbook jobs / AI jobs
       SQLAlchemy + Alembic              scheduler / 短期并发
               │
               ▼
       私有词书卷（api / worker / scheduler 共享）
```

反向代理只默认发布 `127.0.0.1:8080`；PostgreSQL、Redis、API、worker、scheduler 和 frontend 不直接发布宿主端口。容器应用以 UID/GID `10001` 运行。

## 2. 模块职责

| 模块 | 主要代码 | 当前职责 |
|---|---|---|
| Auth | `backend/app/api/v1/auth.py`、`services/auth.py` | 登录、Refresh 轮换、CSRF、改密、退出、会话恢复 |
| Identity | `models/identity.py`、`api/v1/admin.py` | 管理员/成员、最后管理员保护、CSV 导入、审计 |
| Wordbooks | `models/wordbooks.py`、`services/wordbooks.py` | 组织/私有词书、预览、导入、导出、删除、持久任务 |
| Learning | `models/learning.py`、`services/learning.py` | 学习档案、今日快照、心跳、统计、每日计划 |
| Memory | `services/memory.py`、`fsrs_scheduler.py` | FSRS 卡片、翻卡/选择/拼写、错词、已记住/恢复 |
| AI | `models/ai.py`、`services/ai_*.py` | provider、提示词、加密 Key、额度、任务、校验、故障切换 |
| Practice | `models/practice.py`、`services/practice.py` | 四类练习、草稿、提交、评分、记录、错题 |
| Coach | `models/coach.py`、`services/coach.py` | 长期对话、SSE、上下文、受控 action、24h 撤销 |
| Challenges | `models/challenge.py`、`services/challenge.py` | 今日地图、节点进度、共享学习进度、BOSS 结果 |
| Notifications | `models/notifications.py`、`services/notifications.py` | 站内通知、偏好、DND、去重、AI 例外 |
| Dashboard | `services/dashboard.py` | 组织聚合指标、最小分组、隐私抑制 |
| Audit | `services/audit.py` | 登录、管理操作、AI action 等安全事件 |

## 3. 关键请求链路

### 认证

1. `POST /auth/login` 校验 Argon2id 密码并签发短时 Access Token。
2. Refresh Token 只存哈希，放在 HttpOnly Cookie；CSRF Token 使用可读 Cookie + `X-CSRF-Token` 双提交。
3. 前端 Access Token 只保存在内存；页面刷新通过 Refresh Cookie 恢复。
4. 管理员重置密码、停用、删除或改密会撤销对应 Refresh 会话。

### 词书

1. 预览接口解析 CSV/JSON/TXT，返回映射、预览 token/hash 和错误。
2. 确认导入写入持久 `wordbook_jobs`，由 ARQ worker 执行。
3. worker/scheduler 共享私有词书卷；PostgreSQL 保存任务状态、进度和结果，Redis 只做队列。
4. 导出/删除同样是持久任务；删除后条目可见性立即被阻断。

### 记忆与今日计划

1. 后端按用户时区计算 `local_date` 和固定快照。
2. FSRS 只由服务端计算卡片状态、`due_at` 和复习间隔；客户端只提交动作/答案。
3. 翻卡、选择、拼写共享同一份学习事件和错词状态。
4. 今日页面读取服务端快照，不把浏览器本地状态当作业务真相。

### AI 练习

1. 成员创建练习，后端解析合法词书/词条上下文并持久化任务。
2. ARQ worker 调用 OpenAI 兼容 provider。
3. Pydantic + 业务校验器校验 JSON、题量、选项、实体 ID、答案和分数范围。
4. 提交前 API 不返回答案、解析或参考内容；提交后客观题由后端判分，主观题进入 AI 评分。
5. 失败保留真实错误和 Request ID，不生成假题或假分数。

### 教练与挑战

- 教练使用 SSE 流式事件，数据库保存事件序号；断线后从 `Last-Event-ID` 恢复。
- 受控 action 写入 receipt，保存前后状态和 24 小时撤销期限。
- 挑战地图由后端生成并锁定；传统学习与地图节点共享同一份计划进度。
- BOSS 提交幂等，刷新页面后仍可读取已完成结果。

## 4. 数据与一致性

- PostgreSQL 是业务权威源；Redis 不保存唯一业务真相。
- 写请求使用幂等键或请求指纹；重复请求返回同一结果或明确冲突。
- 词书、AI、练习评分、通知和挑战任务均有持久状态。
- 数据库迁移必须可回滚；当前 head 为 `844c0d89f737`。
- 备份、恢复、回滚脚本和演示环境演练已由 T-SHIP-002/003 验证；稳定生产 SLA 仍未验证。

## 5. 可观测性与安全

- 所有响应回写 `X-Request-ID`；错误体包含同一 ID。
- 结构化日志记录方法、路径、状态、延迟和必要用户/任务 ID，不记录密码、Key、完整答案或教练正文。
- 管理员操作与 AI 自动写入进入审计记录。
- 安全头已覆盖 `X-Content-Type-Options`、`X-Frame-Options`、`Referrer-Policy`；CSP 仍为 CONDITIONAL。
- 容器非 root、只读根文件系统、`cap_drop: ALL`、`no-new-privileges` 已在 CI 验证。

## 6. 当前限制

- T-SHIP-003 已验证临时 HTTP IP 预览、`v0.1.1` 镜像 digest、备份恢复和机械回滚；稳定 HTTPS/DNS 不在本次授权范围。
- `GET /learning/today` 的 `ai_practice` 摘要仍是旧 `not_available` 字段；已实现 AI 练习从 `/practice` 进入。
- 质量清单仍为 40 PASS / 3 CONDITIONAL / 4 FAIL；不能把 M5 代码内 PASS_WITH_CONDITIONS 写成最终 MVP PASS。
- 前端视觉允许简洁，当前重点是真实业务闭环而不是复杂动画或素材系统。

## 7. 相关文档

- [数据模型](data-model.md)
- [API](api.md)
- [AI 链路](ai-pipeline.md)
- [安全与隐私](security-privacy.md)
- [测试](testing.md)
- [部署](deployment.md)
- [事实核对](fact-check.md)
