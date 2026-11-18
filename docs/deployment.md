# 部署说明

- 代码基线：`main` @ `1cea3ff` / `v0.1.7`（2026-11-18）
- 部署形态：单机 Docker Compose；可选生产、轻量、隧道三种 overlay

## 1. 服务与端口

| 服务 | 作用 | 端口 |
|---|---|---|
| `postgres` | PostgreSQL 16 | 内部 5432 |
| `redis` | Redis 7 | 内部 6379 |
| `migrate` | 一次性 `alembic upgrade head` | — |
| `api` | FastAPI / uvicorn | 内部 8000 |
| `worker` | ARQ：AI、词书、练习池 | — |
| `scheduler` | ARQ cron：每日计划、通知、回收 | — |
| `frontend` | nginx 提供静态 dist | 内部 8080 |
| `reverse-proxy` | nginx 统一入口 | 宿主 `${EDGE_BIND_ADDRESS:-127.0.0.1}:${EDGE_PORT:-8080}` |

命名卷：`postgres-data`、`redis-data`、`wordbook-data`、`coach-data`。应用容器只读根文件系统、UID 10001。

## 2. Overlay

| 文件 | 用途 |
|---|---|
| `deploy/compose.prod.yml` | 固定镜像 digest、`pull_policy: always`、日志滚动 |
| `deploy/compose.lightweight.yml` | 1 vCPU / 1 GiB 环境的每服务内存与 CPU 上限、Redis/Postgres 调参 |
| `deploy/compose.tunnel.yml` | 可选 cloudflared Quick Tunnel，为临时预览提供 HTTPS 入口 |

## 3. 启动与部署

### 本地 / 验收

```bash
cp .env.example .env
# 替换 POSTGRES_PASSWORD、JWT_SECRET、REFRESH_TOKEN_PEPPER、SECRET_ENCRYPTION_KEY
docker compose up --build -d
docker compose ps
```

`deploy/scripts/start-stack.sh` 会拒绝占位密钥、构建镜像、起 PostgreSQL/Redis、执行迁移、启动应用并运行 `verify-stack.sh` 与 `verify-database`。

### 生产

```bash
deploy/scripts/deploy.sh <version>
```

流程：校验 release manifest 与端口/内存 → 迁移前备份 → 拉取固定镜像 → 迁移 → 启动 → `verify-stack.sh` / `verify-public.sh`。

### 备份与恢复

- `deploy/scripts/backup-db.sh` / `restore-db.sh`：PostgreSQL dump 与校验和。
- `deploy/scripts/backup-wordbooks.sh` / `restore-wordbooks.sh`：词书卷。
- `deploy/scripts/verify-database-restore.sh`：恢复后计数校验。
- RPO/RTO 仍标记 PENDING（见 `deploy/BACKUP-AND-RECOVERY.md`），尚未形成生产承诺。

## 4. CI

`.github/workflows/ci.yml` 在 PR、push main 与手动触发时运行五个阻塞作业：

| 作业 | 内容 |
|---|---|
| backend | uv sync → 建测试库 → ruff lint → ruff format check → pytest（PG16 + Redis7 service） |
| frontend | npm ci → build（vue-tsc + vite）→ vitest |
| quality | 质量清单 unittest + 结构校验 |
| security | gitleaks 扫描 Git 历史 |
| compose | compose config、22 个部署测试、安全头合同、起栈、词书卷探针 |

## 5. 发布

`.github/workflows/release.yml` 在 `v*.*.*` 标签或手动触发时：

1. 构建并推送 `ghcr.io/ticaxox/english-learn-api`、`-frontend`、`-reverse-proxy`（linux/amd64，带 provenance 与 SBOM）。
2. 生成 `release-manifest.json`、镜像 bundle 与 `SHA256SUMS`。
3. 创建 GitHub Release。

已发布标签：`v0.1.0`–`v0.1.7`。

## 6. 部署现状

- 推荐路径是 Docker Compose；生产叠加 `deploy/compose.prod.yml`。
- 公网部署需要自备域名、TLS 与反向代理；仓库不记录托管地址或访问凭据。
- 版本标签用于发布镜像；部署方按自己的环境选择版本。

## 7. 已知缺口

1. 生产备份的 RPO/RTO 与恢复演练未正式归档。
2. 本机无 Docker 时只能验证前端；后端测试需要自备 PostgreSQL/Redis。
3. CI 的 backend 作业会因 ruff 未清零而停在上游，pytest 不会执行。
4. 没有蓝绿或滚动发布，回滚依赖镜像版本与数据库备份。
5. 预览版本与最新标签之间存在未核实间隔。
