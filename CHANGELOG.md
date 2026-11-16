# Changelog

## 2026-10-24｜v0.1.2 成员端结构重构预览

- 临时 HTTP IP 预览升级到 `v0.1.2`，commit `8d5cb83`，Whisker Crumb 主题。
- 成员端新骨架 `member-rail`、`member-topbar`、移动导航、Word shelf、Practice room、Mr. Whisker 上线。
- Today、Word shelf、Practice、Mr. Whisker 使用真实 API 数据；7 张真实截图，page errors/request failures/external requests 均为 0。
- release workflow `40094317102` success；三应用镜像 digest 已记录。
- `v0.1.2 → v0.1.1 → v0.1.2` 应用回滚通过，数据库 head 未变化。
- 仍是临时 HTTP 预览；稳定 HTTPS、最终视频和最终 MVP 验收未完成。

## 2026-10-24｜v0.1.1 Whisker Crumb 主题预览

- 临时 HTTP IP 预览升级到 `v0.1.1`，commit `a6ac195`，主题 Whisker Crumb。
- 七服务健康、`/health/live` v0.1.1、管理员/成员登录、CSRF、SSE、SPA 和主题资源通过。
- 5 张真实截图：登录、成员概览、成员词书、移动端概览、管理员看板。
- release workflow `40066904977` success；API/frontend/reverse-proxy 三镜像 digest 已记录。
- `v0.1.1 → v0.1.0 → v0.1.1` 应用回滚通过，数据库 head 未变化。
- 仍是临时 HTTP 预览；稳定 HTTPS、最终视频和最终 MVP 验收未完成；5 张公网预览截图已归档。

## 2026-10-24｜v0.1.0 临时 HTTP IP 预览

- A00 授权的临时公网预览已通过：`http://23.94.141.170:18080`，版本 `v0.1.0`，commit `4ee1a71`。
- 七个服务 healthy；健康、登录、Cookie/CSRF、SSE、SPA 路径、共享词书卷和备份恢复通过。
- 记录 API/frontend/reverse-proxy 三镜像 digest；release workflow `40023555751` success。
- 明确这是临时 HTTP 预览：稳定 HTTPS、DNS 和长期生产 SLA 未验证，最终 MVP 仍为 `FAIL / NOT_READY`。

## 2026-10-24｜M5 比赛交付文档与演示材料

- 将根 README 从旧工程骨架更新为 M2–M5 真实能力、启动、演示、安全和部署边界。
- 更新架构、数据模型、API、AI 链路、安全隐私、测试、部署、演示和事实核对文档。
- 增加 46 张表的领域分组、84 个 OpenAPI 路径和迁移 head `844c0d89f737` 的事实说明。
- 增加可执行的合成演示数据初始化脚本，并记录首次/重复初始化与真实 API 读取证据。
- 增加 9 张来自 T-QA-004 的合成演示截图、事实清单、完整技术文档、5–8 分钟视频脚本和最终提交清单。
- 保留 T-SHIP-002 未完成的公网 URL、镜像 digest、TLS、生产恢复和最终视频 `TODO`。
- 保留完整 MVP `FAIL / NOT_READY`、47 门禁 40 PASS / 3 CONDITIONAL / 4 FAIL 的结论。

## 2026-10-23｜M2–M5 功能与硬化基线

- 实现认证、成员管理、词书、今日计划、FSRS 记忆、AI provider、提示词、额度、四类 AI 练习、教练 SSE/撤销、通知、每日闯关和组织看板。
- 完成真实 PostgreSQL/Redis/ARQ、API、浏览器、性能、迁移和备份恢复验证。
- T-QA-004 冻结为 M5 代码内 `PASS_WITH_CONDITIONS`；最终 MVP 仍不通过。

## 2026-10-22｜容器与 CI 基线

- 建立 Docker Compose、CI、GHCR 发布工作流、迁移、健康检查、备份和回滚脚本。
- Compose 在干净 runner 完成空库迁移、七服务健康、非 root 和回环端口验证。
- 建立交付文档结构、API/架构/安全/测试/部署/演示基础文档。
