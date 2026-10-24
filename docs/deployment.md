# 部署说明

- 交付基线：`efc6bcbd2679eca02613a7143c68d04dddc36a59`
- 当前临时公网预览：`http://23.94.141.170:18080`（`v0.1.2`，commit `8d5cb83`）
- 主题：Whisker Crumb
- 成员端结构：`member-rail`、`member-topbar`、移动导航、Word shelf、Practice room、Mr. Whisker
- 部署结论：A00 授权的临时 HTTP IP 预览 **PASS**；稳定 HTTPS **未验证/不在本次授权范围**
- 最终 MVP：**FAIL / NOT_READY**，不得把预览通过写成最终验收通过

## 1. 当前运行拓扑

```text
Internet / Reviewer
        │  HTTP（临时预览；不是稳定 HTTPS）
        ▼
reverse-proxy（公网 0.0.0.0:18080）
        ├── frontend（Whisker Crumb + 成员端新骨架）
        ├── /api → API
        └── /health → health routes
                │
        ┌───────┼─────────┐
        ▼       ▼         ▼
   PostgreSQL  Redis    ARQ worker/scheduler
   16          7        共享私有词书卷
```

七个常驻服务为 PostgreSQL 16、Redis 7、API、worker、scheduler、frontend、reverse-proxy；另有一次性 `migrate` 服务。应用容器使用 UID/GID `10001`、只读根文件系统、`cap_drop: ALL` 和 `no-new-privileges`。

## 2. 临时公网预览

- 入口：`http://23.94.141.170:18080`
- 版本：`v0.1.2`
- 源码 commit：`8d5cb83a40eefe5d848a1d9085ed9a7fe149be9a`
- 主题：Whisker Crumb
- 成员端结构：`member-rail`、`member-topbar`、移动导航、Word shelf、Practice room、Mr. Whisker
- 演示用户名：`demo_admin`、`demo_member`
- 密码：只从 A40 的 ACL 本地凭据文件安全获取；不写入仓库、文档、截图、视频或聊天
- 验收结果：七服务 healthy；`/health/live` 返回 `v0.1.2`；`/health/ready` 为 `ready`；登录、Cookie/CSRF、SSE、SPA、成员新骨架、主题资源和真实回滚通过
- 安全边界：临时 HTTP 没有传输加密；响应中的 HSTS 头不能替代 HTTPS；`Secure=false` Cookie 是 `APP_ENV=test` 预览开关的预期结果

T-SHIP-004 证据：

- `ai-workspace/10-collaboration/reports/T-SHIP-004-SHIP.md`
- `ai-workspace/10-collaboration/reports/T-FE-014-VIEW.md`
- `ai-workspace/10-collaboration/sessions/A40-SHIP/test-artifacts/T-SHIP-004-20261024/README.md`
- `.../racknerd/public-smoke.json`
- `.../racknerd/public-headers.txt`
- `.../racknerd/public-routes.txt`
- `.../racknerd/theme-assets.txt`
- `.../racknerd/visual-evidence.json`
- `.../racknerd/screenshots/`
- `.../racknerd/deployment-evidence-v0.1.2.json`
- `.../racknerd/rollback-evidence-v0.1.2.json`

本任务轻量核验：`ai-workspace/10-collaboration/sessions/A50-DOCS/test-artifacts/T-DOC-002/public-preview-check.json`。

## 3. 版本、镜像与发布

- Release：`v0.1.2`
- Release workflow：`40094317102`，success
- GitHub Release：`https://github.com/ticaxox/english-learn-tool/releases/tag/v0.1.2`
- Artifact：`12560168389`，`release-v0.1.2`
- 成员端源码：T-FE-014，PR #38 合并为 `8d5cb83`
- 迁移 head：`844c0d89f737`（成员端结构升级未改变数据库）

应用镜像 digest：

- API：`ghcr.io/ticaxox/english-learn-api@sha256:d2e2e1b1c9b42fb6817c8e6bc3a63d1cb85a9864d756c509361a1990757a3f08`
- Frontend：`ghcr.io/ticaxox/english-learn-frontend@sha256:cbf2d84c1262046bfbfa4accfe397a78d01a4f2a0560d6a2347eeaceade9f3b0`
- Reverse proxy：`ghcr.io/ticaxox/english-learn-reverse-proxy@sha256:4cad0acb21703a942506521d2084a4747686ab3284616e89f4f6eda8a4db68e8`

服务器使用下载并校验后的 release bundle；未使用 GHCR 登录。GHCR 在线拉取流程仍未单独验证。

## 4. 健康检查

- `/health/live`：进程存活，不访问依赖；当前返回 `v0.1.2`。
- `/health/ready`：配置、PostgreSQL、Redis 就绪。
- `/healthz`：反向代理/前端健康入口。
- `/api/v1`：API 元数据；当前返回 `v0.1.2` / `test`。
- `/api/v1/docs`、`/api/v1/openapi.json`：OpenAPI。

失败态返回真实 503/错误码，不返回数据库连接串、Key 或内部堆栈。

## 5. 本地/验收启动

需要 Docker Engine 与 Docker Compose v2：

```bash
cp .env.example .env
chmod 600 .env
# 设置数据库密码、JWT、Refresh Pepper、加密 Key、CORS 等
docker compose up --build -d
docker compose ps
```

默认本地地址：`http://127.0.0.1:8080`。只允许反向代理绑定宿主端口；PostgreSQL、Redis、API、worker、scheduler、frontend 不发布宿主端口。

创建管理员：

```bash
docker compose run --rm \
  -e BOOTSTRAP_ADMIN_USERNAME=admin \
  -e BOOTSTRAP_ADMIN_DISPLAY_NAME='Organization Administrator' \
  -e BOOTSTRAP_ADMIN_PASSWORD='<secret from controlled channel>' \
  api python -m app.cli bootstrap-admin
```

本地合成演示数据：

```powershell
$env:DEMO_SEED_CONFIRM = 'YES'
$env:DEMO_ADMIN_PASSWORD = '<unique demo admin password>'
$env:DEMO_MEMBER_PASSWORD = '<different unique demo member password>'
uv run --project backend python docs/competition/seed_demo_data.py --apply
```

不要在公网预览重复执行 seed；远端演示数据由 A40 准备。完整说明见 [演示数据](competition/demo-data.md)。

## 6. 备份、恢复与回滚

A01 已批准演示/比赛环境策略：RPO 24 小时、RTO 2 小时、备份保留 7 天。

已完成：

- PostgreSQL custom dump + SHA256 sidecar；隔离恢复库的表清单和行数一致；
- 词书卷归档、隔离恢复卷、UID/GID `10001`、mode `0750`、标记完整性；
- 临时恢复库和恢复卷已清理；
- `v0.1.2 → v0.1.1 → v0.1.2` 应用回滚演练通过，数据库 head 未变化；
- 回滚后验证健康、管理员登录、成员新骨架标记存在/不存在及恢复；
- 应用回滚没有反向执行迁移，因为成员端结构升级没有迁移变化。

数据库 dump 与词书归档包含演示私有数据，未复制进 Git、聊天或公开证据。历史兼容业务版本回滚仍未验证；本次只证明版本切换/健康/回切机制。

## 7. 资源与限制

- 目标服务器为 1 vCPU / 约 1 GiB 内存的轻量 profile；实测可运行，但不是标准生产 SLA。
- 临时 HTTP 预览仅用于受控评审；稳定 HTTPS、DNS、WAF、长期监控和公网限流不在本次授权范围。
- 现有 OpenResty/1Panel 的 `80/443/30000` 监听保持不动；临时入口只使用高位端口 `18080`。
- 真实服务器地址、SSH、密码、连接串和私钥只存在于受控接入清单，不复制到仓库。
- 本机 `docker` 是 `wslc`，无 Compose；CI/容器证据来自 GitHub Actions 和 A40 部署记录。
- `write_deployment_receipt.py` 在服务器 Python 3.10 上的 `datetime.UTC` 兼容性问题已记录为非阻断项，后续部署维护任务修复。

## 8. 状态升级规则

只有同时具备固定 SHA、CI run、镜像 digest、部署日志、健康检查、真实 API/浏览器和脱敏证据时，才能把对应部署范围升级为已验证。临时 HTTP 预览通过不等于稳定 HTTPS、长期生产 SLA 或最终 MVP PASS。
