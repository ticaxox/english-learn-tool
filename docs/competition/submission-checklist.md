# 比赛最终提交清单

- 版本：T-DOC-002 / 2026-10-24
- 代码基线：`efc6bcbd2679eca02613a7143c68d04dddc36a59`
- 当前状态：**部分完成**；T-SHIP-002 和 A00 最终验收未完成
- 使用规则：只有证据可回读时才能把 `TODO` 改为完成

## 1. 代码与仓库

| 项目 | 状态 | 证据/动作 |
|---|---|---|
| Git 仓库与分支历史 | 完成 | `ticaxox/english-learn-tool`，真实分支/PR/提交 |
| 本任务分支 | 完成 | `docs/competition-delivery-002` |
| 本任务 PR | 待创建/待 CI | 创建指向 `main` 的 PR，保持 5/5，不自行合并 |
| 版本标签/Release | TODO | T-SHIP-002 / A01 协调 |
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
| 演示账号说明 | 完成 | 用户名固定；密码由环境变量/受控渠道 |
| 评审账号实际交付 | TODO | T-SHIP-002/受控渠道 |

## 4. 截图与视频

| 项目 | 状态 | 证据/动作 |
|---|---|---|
| QA 合成截图 | 完成 | `screenshots/` 9 张，含 SHA256 |
| 事实清单 | 完成 | `screenshots/README.md` |
| 5–8 分钟视频脚本 | 完成 | `demo-video-script.md` |
| 1080p 最终视频 | TODO | T-SHIP-002 后录制 |
| 公网截图 | TODO | 需真实 URL/TLS |
| 视频安全审查 | TODO | 录屏后执行 |

## 5. 部署与发布

| 项目 | 状态 | 证据/动作 |
|---|---|---|
| Compose/CI 七服务与迁移 | 完成 | T-SHIP-001 run `39801657963` |
| 生产服务器容量决策 | TODO | T-SHIP-002 |
| 不可变镜像 tag + digest | TODO | T-SHIP-002 |
| GHCR 推送/拉取 | TODO | T-SHIP-002 |
| 公网 URL、TLS、SSE 不缓冲 | TODO | T-SHIP-002 |
| 生产备份/RPO/RTO/恢复 | TODO | T-SHIP-002 |
| 回滚演练 | TODO | T-SHIP-002 |
| CSP | TODO | 反向代理安全头 |

## 6. 最终安全检查

- [ ] 当前树和历史无 `sk-`、API Key、密码、私钥、连接串或真实成员数据
- [ ] 截图/视频无 Token、真实服务器地址、私有正文或真实对话
- [ ] 演示密码与真实管理员密码不同
- [ ] 公开材料不复制 `ai-workspace` 接入信息
- [ ] 固定 SHA、Actions run、镜像 digest 和部署证据
- [ ] 文档状态与质量门禁一致
- [ ] A30/A01 事实复核
- [ ] A00 最终比赛验收

## 7. 当前不可宣称

- 公网演示已完成。
- GHCR 镜像已推送或 digest 已取得。
- 生产 TLS/备份/恢复/回滚已完成。
- 最终视频已录制。
- 完整 MVP 已 PASS。

## 8. 完成定义

只有以下同时满足，才可把比赛提交标记为完成：

1. PR 合并且 `main` CI 5/5。
2. 固定镜像 digest 和可回读部署证据。
3. 公网入口/TLS/SSE/评审账号可用。
4. 生产备份恢复和回滚演练完成。
5. 1080p 最终视频和公网截图完成。
6. A30/A01 复核，A00 最终验收。
