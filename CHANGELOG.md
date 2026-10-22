# Changelog

本文件记录可公开的仓库级变更。产品规划本身不等于已交付功能；未验证的部署或业务能力必须继续标记为待验证。

## [Unreleased]

### Added

- 根级交付文档入口、协作指南和文档结构。
- 架构、数据模型、API、AI 链路、安全隐私、测试、部署、演示和事实核对文档。
- 比赛技术文档与演示视频的章节骨架。
- GitHub Actions 五作业 CI、Docker Compose 空库迁移与七服务健康检查基线。
- GHCR 发布工作流，以及生产覆盖、启动、验证、备份、部署和回滚脚本。

### Verified at `caa731c`

- 后端 `uv sync --locked --all-groups`、Ruff lint、Ruff format check 通过。
- 后端真实 PostgreSQL/Redis 测试 18 项通过；复测使用一次性独立数据库。
- 本地 Alembic `upgrade head` 与 `check` 通过。
- 前端 `npm ci`、11 项测试和生产构建通过。
- Vite `/api` 代理到 FastAPI 的 `/api/v1` 冒烟返回 `200`。
- ARQ worker/scheduler 心跳入口完成启动冒烟，随后停止进程。

### Verified container/CI baseline at `a5bf49b`

- GitHub Actions run `39801657963` 第 2 次尝试 5/5 作业通过：后端、前端、质量清单、敏感信息扫描和 Compose 集成。
- Compose 在干净 runner 上从空库迁移到 revision `20261022_0001`，确认 `system_metadata` 存在。
- PostgreSQL、Redis、API、worker、scheduler、frontend 和 reverse proxy 七个常驻服务健康。
- API、worker、scheduler、frontend 和 reverse proxy 以 UID/GID `10001` 非 root 运行；只有反向代理默认绑定 `127.0.0.1:8080`。
- 反向代理 `/health/live`、`/health/ready` 与 `/api/v1` 验证通过。

### Pending

- GHCR release workflow 仅通过静态检查，尚未实际触发；三个发布镜像尚未推送。
- 未部署云服务器，未配置域名、TLS、公网入口或评审账号。
- 备份、部署和回滚脚本未做生产恢复演练；应用回滚不自动反向迁移数据库。
- 真实认证、成员管理、词书、FSRS、AI 练习、AI 教练和每日闯关：尚未实现。
- 比赛技术文档正文和录制视频：尚未交付；整体 MVP 仍为 `FAIL / NOT_READY`。

## [0.1.0-foundation] - 2026-10-22

### Added

- FastAPI 应用、统一错误响应、Request ID、健康检查和服务元数据。
- PostgreSQL async 基础设施和 `system_metadata` 初始迁移。
- Redis 就绪检查、ARQ worker/scheduler 心跳入口。
- Vue 3、Vite、TypeScript、Pinia、Vue Router 前端壳层与测试基线。
- 阶段验收门禁清单和工程基线 PR #1、#2、#3。
- 容器、部署资产、CI 与 GHCR 发布工作流 PR #4；合并提交 `caa731c`。

### Notes

- 该版本是工程基线，不是完整产品发布。
- `tests/quality-baseline` 中最终 MVP 门禁仍为 `FAIL / NOT_READY`。
