# Backend

Grimoire 的后端：FastAPI 模块化单体 + 两个 ARQ 进程，为个人版英语学习应用提供认证、词书、FSRS 记忆、AI 练习、教练、闯关、游戏化与知识库。

## 技术栈

- Python 3.12（`>=3.12,<3.13`）
- FastAPI / Pydantic v2 / SQLAlchemy 2 async（asyncpg）
- PostgreSQL 16、Redis 7、ARQ 0.26
- Alembic（40 个 revision，head `20261114_0032`）
- `fsrs==6.3.2`、Argon2id、pyjwt、cryptography、httpx、pypdf、reportlab

## 目录

| 路径 | 内容 |
|---|---|
| `app/main.py` | 应用工厂、lifespan（ARQ、Redis、engine、存储）、中间件 |
| `app/api/v1/` | 20 个路由模块，117 条路径 |
| `app/services/` | 业务逻辑：记忆、练习、教练、闯关、游戏化、知识库、AI 任务 |
| `app/models/` | 59 张表，13 个模块 |
| `app/schemas/` | Pydantic 请求/响应模型 |
| `app/workers/` | `worker.py`（AI/词书/练习池）、`scheduler.py`（cron） |
| `alembic/` | 迁移 |
| `tests/` | 40 个文件、209 个测试函数，打真实 PostgreSQL/Redis |

## 运行

```powershell
uv sync --locked --all-groups
Copy-Item .env.example .env   # 编辑密钥
uv run alembic upgrade head
uv run uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

另开终端：

```powershell
uv run arq app.workers.worker.WorkerSettings
uv run arq app.workers.scheduler.SchedulerSettings
```

## 测试

```powershell
uv run ruff check .
uv run ruff format --check .
uv run pytest
```

测试必须先有可用的 PostgreSQL 16 与 Redis 7；`tests/conftest.py` 会在会话开始时执行迁移，每个用例事务回滚。

## 关键实现

- **认证**：JWT + HttpOnly Refresh Cookie（哈希、轮换、15 秒复用宽限）+ CSRF 双提交。2026-11-18 起 Origin 校验为空实现，CORS 反射任意来源。
- **FSRS**：只在服务端计算，两档评分（again/good），禁用 fuzz。
- **AI 平台**：`ai_jobs` 持久任务、幂等键、provider 降级、额度预扣/结算/释放、每用户 2 个并发上限。
- **练习**：六种题型、预生成池、服务端判客观题、AI 判主观题。
- **教练**：SSE 事件日志、8 个受控动作、24 小时撤销。
- **知识库**：书架模型、题号感知分块、可选 embedding、线性检索。

## 契约

`openapi.json` 是路由的产物快照，必须与 `app.openapi()` 一致；改路由后重新生成（命令见 `docs/api.md`）。
