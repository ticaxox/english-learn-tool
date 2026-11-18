# Grimoire

**个人 AI 英语学习空间。**

选一本词书，按 FSRS 的节奏记单词，用 AI 练习和 AI 教练把词用出去，每天沿着南瓜小径闯一关。界面是一套万圣节的昼夜双态画：白天是奶油纸与黄铜，夜里是深紫与发光的南瓜灯，守着那盏灯的角色叫 Hob。

## 在线演示

**[https://czbdemo.ticax.net/](https://czbdemo.ticax.net/)**

演示环境使用合成数据；AI 功能需要先在「设置 → AI 配置」里添加一个 OpenAI 兼容 provider。

## 功能

- **今日学习**：每日计划、到期复习、任务环、推荐词书、内嵌闯关地图、周报与徽章墙。
- **词书**：内置词书，或导入自己的 CSV / JSON / TXT；支持预览、导入任务、启用、导出与删除。
- **记忆训练**：FSRS 6.3.2 服务端调度，翻卡、选择、拼写三种模块，错词优先级、掌握与恢复。
- **AI 练习**：填空、阅读、翻译、作文、对话、混合六种题型；服务端生成、服务端判分，支持草稿、重生成、交卷、记录与错题。
- **AI 教练 Hob**：多轮对话、流式回复、附件、语音输入，以及带 24 小时撤销的受控动作。
- **每日闯关**：由 AI 编排的节点地图，复习、新词、练习、支线与终点 BOSS。
- **游戏化**：经验、等级（余烬→火舌→熔炉→锻铁→淬火）、灯油、连续天数与冻结、每日任务、23 枚徽章、周报。
- **知识库**：导入真题与资料，练习与教练都能带着出处引用。
- **个人 AI 配置**：自备 OpenAI 兼容 provider，连接测试、模型列表、额度与用量。
- **昼夜主题**：跟随系统或手动切换，素材交叉淡出。

## 技术栈

| 层 | 选型 |
|---|---|
| 前端 | Vue 3.5、TypeScript、Vite 8、Pinia、vue-router 5 |
| 后端 | Python 3.12、FastAPI、Pydantic v2、SQLAlchemy 2 async |
| 数据 | PostgreSQL 16、Alembic |
| 队列 | Redis 7、ARQ |
| 记忆 | fsrs 6.3.2 |
| AI | OpenAI 兼容网关（chat / embedding），Key 加密存储 |

## 快速开始

### Docker Compose

需要 Docker Engine 与 Compose v2。

```bash
cp .env.example .env
chmod 600 .env
# 编辑 .env，替换 POSTGRES_PASSWORD、JWT_SECRET、REFRESH_TOKEN_PEPPER、SECRET_ENCRYPTION_KEY
docker compose up --build -d
docker compose ps
```

Compose 会先执行一次 `alembic upgrade head`，再启动 API、worker、scheduler、frontend 与反向代理。默认入口是 `http://127.0.0.1:8080`。

### 本地开发

后端：

```powershell
cd backend
uv sync --locked --all-groups
Copy-Item .env.example .env
uv run alembic upgrade head
uv run uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

另开两个终端：

```powershell
cd backend
uv run arq app.workers.worker.WorkerSettings
uv run arq app.workers.scheduler.SchedulerSettings
```

前端：

```powershell
cd frontend
npm ci
npm run dev
```

打开 `http://127.0.0.1:5173`，注册账号即可开始。AI 功能需要先在「设置 → AI 配置」里添加一个 provider。

## 配置

根 `.env.example` 只含占位值。常用变量：

| 变量 | 用途 |
|---|---|
| `DATABASE_URL` | PostgreSQL 连接串 |
| `REDIS_URL` | 队列与短期协调 |
| `JWT_SECRET` | Access Token 签名 |
| `REFRESH_TOKEN_PEPPER` | Refresh Token 哈希保护 |
| `SECRET_ENCRYPTION_KEY` | AI provider Key 加密 |
| `CORS_ORIGINS` | 允许的前端来源 |
| `WORDBOOK_STORAGE_DIR` | 词书文件目录（绝对路径） |
| `AI_ALLOW_PRIVATE_PROVIDER_URLS` | 是否允许私有 provider 地址 |

生产环境会拒绝占位密钥与私有 provider 地址。

## 数据库

```powershell
cd backend
uv run alembic upgrade head
uv run alembic heads
```

迁移保持单头；容器空库迁移由 Compose 的 `migrate` 服务完成。

## 测试

```powershell
# 后端（需要 PostgreSQL 16 与 Redis 7）
cd backend
uv run ruff check .
uv run ruff format --check .
uv run pytest

# 前端
cd frontend
npm run build
npm test
```

## 项目结构

```text
backend/          FastAPI 应用、模型、服务、ARQ worker 与迁移
frontend/         Vue 应用、组件、页面、样式与万圣节素材
deploy/           Dockerfile、Compose overlay、部署与备份脚本
docs/             架构、数据模型、API、AI、安全、测试、部署与演示
tests/            质量基线
```

## 文档

- [架构](docs/architecture.md)
- [数据模型](docs/data-model.md)
- [API](docs/api.md)
- [AI 链路](docs/ai-pipeline.md)
- [安全与隐私](docs/security-privacy.md)
- [测试](docs/testing.md)
- [部署](docs/deployment.md)
- [演示](docs/demo.md)

## 贡献

见 [CONTRIBUTING.md](CONTRIBUTING.md)。
