# Changelog

本文件记录可公开的仓库级变更。产品规划本身不等于已交付功能；未验证的部署或业务能力必须继续标记为待验证。

## [Unreleased]

### Added

- 根级交付文档入口、协作指南和文档结构。
- 架构、数据模型、API、AI 链路、安全隐私、测试、部署、演示和事实核对文档。
- 比赛技术文档与演示视频的章节骨架。

### Verified at `c3b2a50`

- 后端 `uv sync --locked --all-groups`、Ruff lint、Ruff format check 通过。
- 后端真实 PostgreSQL/Redis 测试 18 项通过。
- 本地 Alembic `upgrade head` 与 `check` 通过。
- 前端 `npm ci`、11 项测试和生产构建通过。
- Vite `/api` 代理到 FastAPI 的 `/api/v1` 冒烟返回 `200`。
- ARQ worker/scheduler 心跳入口完成启动冒烟，随后停止进程。

### Pending

- Docker、Compose、CI、空库容器迁移和容器健康检查：待 T-SHIP 验证。
- 真实认证、成员管理、词书、FSRS、AI 练习、AI 教练和每日闯关：尚未实现。
- 比赛演示账号、公网部署、技术文档正文和录制视频：尚未交付。

## [0.1.0-foundation] - 2026-10-22

### Added

- FastAPI 应用、统一错误响应、Request ID、健康检查和服务元数据。
- PostgreSQL async 基础设施和 `system_metadata` 初始迁移。
- Redis 就绪检查、ARQ worker/scheduler 心跳入口。
- Vue 3、Vite、TypeScript、Pinia、Vue Router 前端壳层与测试基线。
- 阶段验收门禁清单和工程基线 PR #1、#2、#3。

### Notes

- 该版本是工程基线，不是完整产品发布。
- `tests/quality-baseline` 中最终 MVP 门禁仍为 `FAIL / NOT_READY`。
