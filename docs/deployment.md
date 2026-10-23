# 部署说明

- 交付基线：`efc6bcbd2679eca02613a7143c68d04dddc36a59`
- 容器/CI 已验证：T-SHIP-001，代码 `a5bf49b`，Actions run `39801657963`
- 生产部署状态：**未完成**；T-SHIP-002 正在执行
- 公网 URL、TLS、GHCR digest、生产备份恢复和回滚：**TODO**

## 1. 当前运行拓扑

```text
Internet / Reviewer
        │  HTTPS（尚未验证）
        ▼
reverse-proxy（默认仅 127.0.0.1:8080）
        ├── frontend
        ├── /api → API
        └── /health → health routes
                │
        ┌───────┼─────────┐
        ▼       ▼         ▼
   PostgreSQL  Redis    ARQ worker/scheduler
   16          7        共享私有词书卷
```

Compose 定义七个常驻服务：PostgreSQL、Redis、API、worker、scheduler、frontend、reverse-proxy；另有一次性 `migrate` 服务。应用容器使用 UID/GID `10001`、只读根文件系统、`cap_drop: ALL` 和 `no-new-privileges`。

## 2. 本地/验收启动

需要 Docker Engine 与 Docker Compose v2：

```bash
cp .env.example .env
chmod 600 .env
# 设置数据库密码、JWT、Refresh Pepper、加密 Key、CORS 等
docker compose up --build -d
docker compose ps
```

默认地址：`http://127.0.0.1:8080`。只允许反向代理绑定宿主端口；PostgreSQL、Redis、API、worker、scheduler、frontend 不发布宿主端口。

创建管理员：

```bash
docker compose run --rm   -e BOOTSTRAP_ADMIN_USERNAME=admin   -e BOOTSTRAP_ADMIN_DISPLAY_NAME='Organization Administrator'   -e BOOTSTRAP_ADMIN_PASSWORD='<secret from controlled channel>'   api python -m app.cli bootstrap-admin
```

初始化合成演示数据：

```powershell
$env:DEMO_SEED_CONFIRM = 'YES'
$env:DEMO_ADMIN_PASSWORD = '<unique demo admin password>'
$env:DEMO_MEMBER_PASSWORD = '<different unique demo member password>'
uv run --project backend python docs/competition/seed_demo_data.py --apply
```

完整说明见 [演示数据](competition/demo-data.md)。

## 3. 健康检查

- `/health/live`：进程存活，不访问依赖。
- `/health/ready`：配置、PostgreSQL、Redis 就绪。
- `/healthz`：反向代理/前端健康入口。
- `/api/v1`：API 元数据。
- `/api/v1/docs`、`/api/v1/openapi.json`：OpenAPI。

失败态返回真实 503/错误码，不返回数据库连接串、Key 或内部堆栈。

## 4. 已通过的 CI/Compose 证据

T-SHIP-001 run `39801657963` 第 2 次尝试：

- Backend、Frontend、Quality、Security、Compose 五类作业全部 PASS。
- Compose 在 GitHub 托管干净 runner 上构建镜像、空库迁移、启动七服务。
- API、worker、scheduler、frontend、reverse-proxy UID 为 `10001` 非 root。
- 只有反向代理默认绑定 `127.0.0.1:8080`。
- `/health/live`、`/health/ready`、`/api/v1`、`/healthz` 与 `/` 通过。
- 数据库 revision 为 `20261022_0001`；后续 QA 已推进到当前迁移 head `844c0d89f737`。
- 第 1 次失败来自 Docker Hub 临时 `500`，不是配置回归。

本机 `docker` 实际是 `wslc`，没有 Docker Compose；本地只做配置/静态检查。真实容器运行证据来自 Actions 干净 runner，不能写成“本机 Compose 已验证”。

## 5. GHCR 发布设计

`.github/workflows/release.yml` 设计为：

- 语义版本 tag 或手动触发。
- 构建 API、frontend、reverse-proxy 三个镜像。
- 每个镜像附加完整 Git SHA；版本 tag 同时产生语义版本和 `latest`。
- 部署脚本拒绝 `local`、`latest` 等可变 tag。

当前**未**创建版本 tag、未触发 release、未推送 GHCR、未取得 digest、未验证拉取凭据。

## 6. 生产前置条件

T-SHIP-002 必须完成或明确记录：

1. 目标服务器容量、磁盘、内存和现有 OpenResty/1Panel 端口边界。
2. 固定不可变镜像 tag + digest，三镜像可拉取。
3. PostgreSQL/Redis 不暴露公网；密钥通过环境/Secret 注入。
4. 域名、TLS、反向代理、SSE 不缓冲和公网入口。
5. 词书卷跨 api/worker/scheduler 共享，重启后保留。
6. 生产备份审批、RPO/RTO、恢复演练和镜像回滚。
7. CSP 安全头、日志轮转、监控、限流和故障告警。
8. 评审账号与合成演示数据通过受控渠道交付。

## 7. 备份、恢复与回滚

- 部署前备份运行中数据库；备份文件不进入 Git。
- 加密主密钥与数据库备份分离。
- 应用回滚不自动反向迁移数据库；结构不兼容时停止并走单独批准的数据恢复流程。
- `rollback.sh` 只回滚应用镜像，不自动删除词书卷或生产数据。
- 生产恢复演练未完成前，`F-AUDIT-01` 保持 CONDITIONAL。

## 8. 资源与限制

- 现有共享服务器容量不足，不能直接压入完整 Compose 栈。
- 不得修改现有 OpenResty、1Panel、80/443/30000 站点或其他未知生产数据。
- WSL 可用于本地构建/集成验证，但不能替代云服务器生产验证。
- 真实服务器地址、SSH、密码、连接串和私钥只存在于受控接入清单，不复制到仓库。

## 9. 状态升级规则

只有同时具备固定 SHA、CI run、镜像 digest、部署日志、健康检查、真实 API/浏览器和脱敏证据时，才能把生产部署从 `TODO` 升级为已验证。T-SHIP-002 完成前，所有公网入口、TLS、评审账号和最终视频均保持未完成。
