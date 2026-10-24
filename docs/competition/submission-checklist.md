# 比赛最终提交清单

- 版本：T-DOC-002 / 2026-10-24
- 代码基线：`efc6bcbd2679eca02613a7143c68d04dddc36a59`
- 临时公网预览：`http://23.94.141.170:18080`（`v0.1.2`，commit `8d5cb83`，主题 Whisker Crumb）
- 当前状态：**部分完成**；临时 HTTP 预览已 PASS，稳定 HTTPS/最终视频/A00 最终验收未完成
- 使用规则：只有证据可回读时才能把 `TODO` 改为完成

## 1. 代码与仓库

| 项目 | 状态 | 证据/动作 |
|---|---|---|
| Git 仓库与分支历史 | 完成 | `ticaxox/english-learn-tool`，真实分支/PR/提交 |
| 本任务分支 | 完成 | `docs/competition-delivery-002` |
| 本任务 PR | 完成 | PR #35，OPEN/MERGEABLE/未合并；CI 5/5（最终 run 见 PR） |
| 版本标签/Release | 完成 | `v0.1.2`；release workflow `40094317102` success |
| 许可证 | TODO | A00 决策，见 `licensing.md` |
| 当前质量门禁 | 保留 FAIL/CONDITIONAL | 47 门禁 40/3/4/0；不得改写成 PASS |

## 2. 文档

| 项目 | 状态 | 路径 |
|---|---|---|
| 根 README | 完成 | `README.md` |
| 架构/数据/API/AI/安全/测试/部署/演示 | 完成 | `docs/` |
| 技术文档正文 | 完成 | `docs/competition/technical-document.md` |
| 技术文档页数 | 草稿已生成 | 6 页草稿 PDF 保存在任务证据目录；最终模板复核 TODO |
| API/OpenAPI | 完成 | `docs/api.md`、`backend/openapi.json` |
| 事实核对 | 完成 | `docs/fact-check.md` |
| 来源/许可证说明 | 部分完成 | `docs/competition/licensing.md`；许可证待 A00 |

## 3. 演示数据与账号

| 项目 | 状态 | 证据 |
|---|---|---|
| 可执行初始化脚本 | 完成 | `docs/competition/seed_demo_data.py` |
| 首次初始化 | PASS | 一次性独立 PostgreSQL |
| 重复初始化 | PASS | 同一 demo 命名空间重建 |
| 合成管理员/成员/词书/练习/对话/挑战 | 完成 | `demo-data.md` |
| 远端预览账号 | 完成 | `demo_admin`、`demo_member` |
| 密码交付 | 受控 | 只从 A40 的 ACL 本地凭据文件安全获取；不写入仓库/文档/证据 |
| 评审账号实际交付 | 部分完成 | 用户名和 ACL 路径已说明；密码由受控渠道交付 |

## 4. 截图与视频

| 项目 | 状态 | 证据/动作 |
|---|---|---|
| v0.1.2 公网截图 | 完成 | 7 张 Whisker Crumb 真实截图，含 SHA256 |
| 历史 QA 功能截图 | 完成 | 9 张，保留 AI/教练/BOSS 证据 |
| 事实清单 | 完成 | `screenshots/README.md` |
| 5–8 分钟视频脚本 | 完成 | `demo-video-script.md` |
| 1080p 最终视频 | TODO | 使用临时预览录制，完成后补路径 |
| 稳定 HTTPS 截图 | TODO | 当前只有临时 HTTP IP 截图 |
| 视频安全审查 | TODO | 录屏后执行 |

## 5. 部署与发布

| 项目 | 状态 | 证据/动作 |
|---|---|---|
| Compose/CI 七服务与迁移 | 完成 | T-SHIP-001 run `39801657963` |
| 临时 HTTP 公网预览 | 完成 | `http://23.94.141.170:18080`；`v0.1.2`；commit `8d5cb83` |
| 七个服务健康/登录/Cookie/CSRF/SSE/SPA/主题 | 完成 | T-SHIP-004 public-smoke/visual evidence |
| 成员端结构重构 | 完成 | `member-rail`、`member-topbar`、移动导航、Word shelf、Practice room、Mr. Whisker；T-FE-014 |
| 不可变镜像 tag + digest | 完成 | release manifest；三镜像 digest |
| GHCR 发布 | 完成 | release workflow `40094317102` |
| GHCR 在线拉取 | 未单独验证 | 服务器使用校验后的 release bundle |
| 稳定 HTTPS/TLS/DNS | 范围外/未验证 | A00 只授权临时 HTTP IP 预览 |
| 备份/RPO/RTO/恢复 | 完成 | RPO 24h / RTO 2h / 保留 7 天；数据库与词书恢复 |
| 机械回滚 | PASS_WITH_LIMITS | 无历史兼容业务版本，不能宣称旧业务回归 |
| CSP/安全响应头 | 预览存在 | `F-SEC-01` 仍待 A30/A01 重新分类 |
| 临时端口清理 | TODO | 预览结束/评审完成后由 A40 关闭 |

## 6. 最终安全检查

- [x] 当前树和本提交无 `sk-`、API Key、密码、私钥、连接串或真实成员数据
- [x] 截图/视频脚本无 Token、真实成员或私有正文
- [x] 演示密码与真实管理员密码不同
- [x] 公开材料不复制 A40 ACL 密码
- [x] 固定 SHA、Actions run、镜像 digest 和预览证据
- [ ] 文档状态与质量门禁最终复核
- [ ] A30/A01 最终复核
- [ ] A00 最终比赛验收

## 7. 当前不可宣称

- 稳定 HTTPS、TLS 或长期生产 SLA 已完成。
- 历史兼容业务版本回滚已通过。
- 最终视频已录制；稳定 HTTPS 截图已取得。
- 完整 MVP 已 PASS。

## 8. 完成定义

只有以下同时满足，才可把比赛提交标记为完成：

1. PR 合并且 `main` CI 5/5。
2. 固定 `v0.1.2` 镜像 digest 和可回读部署证据。
3. 临时预览入口/SSE/账号可用；若 A00 要求稳定 HTTPS，则另立任务完成。
4. 备份恢复和机械回滚证据已归档。
5. 1080p 最终视频完成；临时 HTTP 公网截图已归档，稳定 HTTPS 截图按 A00 要求补充。
6. A30/A01 复核，A00 最终验收。
