# 架构与当前边界

- 代码基线：`main` @ `1cea3ff` / `v0.1.7`（2026-11-18）
- 形态：模块化单体（FastAPI）+ 两个 ARQ 进程 + PostgreSQL 16 + Redis 7
- 前端：Vue 3.5 + TypeScript + Vite 8 + Pinia + vue-router 5

## 1. 运行时拓扑

```text
Browser
  │  HTTPS/HTTP
  ▼
reverse-proxy (nginx) ── frontend (nginx, dist) ── api (uvicorn :8000)
                                   │
                                   ├── PostgreSQL 16
                                   ├── Redis 7
                                   ├── worker  (ARQ: AI / 词书 / 练习池)
                                   ├── scheduler (ARQ cron: 计划 / 通知 / 回收)
                                   └── 私有卷 /app/var/{wordbooks,coach}
```

- 只有 `reverse-proxy` 发布宿主端口（默认 `127.0.0.1:8080`）。
- 应用容器以 UID 10001 运行，根文件系统只读，`cap_drop: ALL`，`no-new-privileges`。
- `api`、`worker`、`scheduler` 共享数据库、Redis 与词书/教练文件卷。

## 2. 后端分层

| 层 | 目录 | 职责 |
|---|---|---|
| 传输 | `app/api/v1/*` | 路由、依赖注入、鉴权、把服务异常映射为 HTTP |
| 服务 | `app/services/*` | 全部业务逻辑：记忆、练习、教练、闯关、游戏化、知识库、AI 任务 |
| 模型 | `app/models/*` | SQLAlchemy 2 映射，59 张表、13 个模块 |
| 契约 | `app/schemas/*` | Pydantic v2 请求/响应模型 |
| 基础设施 | `app/core`、`app/db`、`app/workers` | 配置、安全、数据库会话、ARQ |

`app/main.py` 的 lifespan 负责创建 ARQ pool、Redis、engine、session factory 与本地文件存储；中间件包括 CORS、安全响应头与 `X-Request-ID`。

## 3. 关键请求链路

### 3.1 认证

`POST /auth/login` → 校验 Argon2id → 签发短时 Access Token（响应体）+ HttpOnly Refresh Cookie（服务端存哈希、轮换，15 秒复用宽限）→ 写请求携带 `X-CSRF-Token`。2026-11-18 起不再校验 Origin 白名单，CSRF 仍是写请求的防线。

### 3.2 记忆训练（FSRS）

`GET /learning/today` 给出新词与到期词 → `POST /memory/sessions` 建会话 → 逐题 `POST /memory/sessions/{id}/events`（幂等）→ 服务端用 `fsrs==6.3.2` 计算 `due_at`/间隔，只接受 again/good 两档，禁用 fuzz → `complete` 后落 `user_word_states`。

### 3.3 AI 练习

`POST /practice/sessions` 先尝试领取预生成池；未命中则创建 `generating` 会话与 `practice_generation` 任务（202）→ worker 调 provider → Pydantic + 业务校验、最多一次 JSON 修复 → 题目落库，答案在交卷前不下发 → `submit` 同步判客观题，主观题走一次 `subjective_grading` 任务。

### 3.4 AI 教练

`POST /coach/conversations/{id}/messages` 建 202 消息任务 → worker 生成回复并写 `coach_stream_events` → 前端通过 SSE 端点按 `Last-Event-ID` 续传；控制器输出的 8 个受控动作先落 `coach_action_receipts`，24 小时内可撤销。

### 3.5 每日闯关

`POST /challenges/today/generate` 建 `challenge_plan` 任务；服务端准备上下文（新词、到期词、额度、合法实体），AI 只编排顺序与文案；计划生成后当日锁定，节点开始/完成与 BOSS 提交都幂等。

### 3.6 知识库检索

导入 → 分块（题号感知，900/120，单文档 ≤400 块）→ 可选 embedding → `GET /knowledge/search` 或教练 `search_knowledge` 触发检索：Python 线性扫描，余弦与关键词取高低分混合（0.6·max + 0.4·min），阈值 0.12，最多 6 条，返回出处。检索范围限于该学习者可读的书架（公共真题架、目标难度架、个人架）。

## 4. AI 任务平台

- `ai_jobs` 保存任务类型、提示词快照、幂等键与请求哈希、provider、终态与错误码。
- 任务类型：`practice_generation`、`subjective_grading`、`coach_reply`、`challenge_plan`、`json_repair`、`conversation_turn`。
- provider 选择：enabled + kind=chat + owner=调用者，按 priority → is_default → created_at 排序，失败自动降级到下一个。
- 额度：reserve → consume / release；三类计数（教练 100、出题 20、主观评分 50 / 日）。
- 并发：每用户最多 2 个进行中的 AI 任务（Redis ZSET + Lua）。
- scheduler 定期回收 stale 任务并释放额度。

## 5. 前端分层

| 层 | 位置 | 说明 |
|---|---|---|
| 入口 | `src/main.ts` | 先定 surface（`/m` 手机树），预涂主题，再依次加载 10 张全局样式表 |
| 路由 | `src/router/index.ts` | 30 条 path / 24 个命名路由，全部静态加载；守卫负责会话恢复、强制改密、adminOnly |
| 外壳 | `src/components/MemberShell.vue` | 左侧 rail（等级板、四项导航、昼夜开关、折叠把手）+ 顶栏二级页签 + 手机底部导航 + 教练抽屉 |
| API | `src/api/client.ts` | 唯一 fetch 封装：Bearer + CSRF、401 单次刷新、GET 重试、错误规整 |
| 契约 | `src/api/contract-adapter.ts` | 后端 snake_case 与前端类型的唯一映射层 |
| 状态 | `src/stores/auth.ts` + composables | 只有 auth 是 Pinia store，其余为模块级 composable |
| 样式 | 18 张 CSS | `game-ui.css` 令牌与游戏层、`controls.css` 控件套件、`game-shell.css` 外壳；页面级样式由各视图 import |

主题：`useTheme.ts` 读写 cookie `crumb_theme`、首次跟随 `prefers-color-scheme`，把 `data-theme` 写到 `<html>`；`ArtImage.vue` 在同一格叠 day/night 两张图，切换时 520ms 交叉淡出。

## 6. 数据与队列边界

- PostgreSQL 是业务权威；Redis 只做队列、并发锁与短期协调，丢失可从数据库恢复。
- 词书文件与教练附件在私有卷，数据库只存元数据与路径。
- 所有异步任务都可在数据库中查询终态；`202` 只代表已接收。

## 7. 已知边界

1. RAG 检索是线性扫描，规模适合千级 chunk；万级需要 pgvector。
2. 夜间样式是 `html[data-theme='night']` 逐条覆盖（约 262 条），不是令牌翻面，新组件容易漏。
3. 个人版没有删除管理端接口，`/admin/*` 仍可访问，只是成员端导航不暴露。
4. `GET /learning/today` 的 `ai_practice` 摘要仍固定返回 `not_available`。
5. 全部路由静态加载，构建产物约 894KB JS + 801KB CSS（2026-11-17 实测）。
