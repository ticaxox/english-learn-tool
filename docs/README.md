# 文档索引

本目录记录当前代码事实、验证证据、部署边界和比赛交付材料。产品蓝图中的规划能力不能因为写入文档而被视为已实现。

## 状态标记

| 标记 | 含义 |
|---|---|
| **已验证** | 在指定提交上通过代码定位、自动化测试、真实 API/浏览器或固定 CI run 得到证据。 |
| **PASS_WITH_CONDITIONS** | 代码内主链路通过，但仍有明确非代码/生产条件未关闭。 |
| **未验证 / TODO** | 依赖稳定 HTTPS、A00 决策、真实 provider 或最终录屏。 |
| **FAIL / NOT_READY** | 完整 MVP 或质量门禁未通过，不得对外写成完成。 |

当前代码基线：`efc6bcbd2679eca02613a7143c68d04dddc36a59`。临时公网预览：`http://23.94.141.170:18080`（`v0.1.2`，commit `8d5cb83`，主题 Whisker Crumb，HTTP）。迁移 head：`844c0d89f737`。OpenAPI：84 路径 / 153 schema。

## 核心文档

| 文档 | 内容 | 当前状态 |
|---|---|---|
| [架构](architecture.md) | 模块、请求链路、数据/队列、部署与边界 | 临时 HTTP 预览已验证；稳定 HTTPS 未验证 |
| [数据模型](data-model.md) | 46 张应用表（另含 Alembic 版本表）、迁移链、不变量、隐私边界 | 已验证 |
| [API](api.md) | OpenAPI、认证、错误、分页、幂等、202、SSE | 已验证 |
| [AI 链路](ai-pipeline.md) | provider、提示词、额度、练习、教练、挑战 | 已验证（受控 provider） |
| [安全与隐私](security-privacy.md) | 身份、权限、AI Key、容器、CSP/备份条件 | 部分 PASS，仍有 CONDITIONS |
| [测试](testing.md) | QA 证据、命令、性能、门禁和演示数据验证 | M5 PASS_WITH_CONDITIONS |
| [部署](deployment.md) | Compose、CI、GHCR、临时 IP 预览、备份与限制 | 临时 HTTP 预览 PASS；稳定 HTTPS 未验证 |
| [演示](demo.md) | 合成账号、成员端结构、演示路径、失败态和限制 | v0.1.2 成员端结构已上线；最终录屏 TODO |
| [事实核对](fact-check.md) | 文档陈述到代码/证据的映射 | 持续维护 |

## 比赛材料

| 文档 | 用途 | 当前状态 |
|---|---|---|
| [技术文档正文](competition/technical-document.md) | 面向评委的完整技术说明，目标不超过 30 页 | 正文已生成；6 页草稿 PDF 保存在任务证据目录，待最终模板复核 |
| [演示数据与账号](competition/demo-data.md) | 合成数据脚本、账号、重置和验证 | 脚本首次/重复初始化 PASS |
| [演示截图清单](competition/screenshots/README.md) | 7 张 v0.1.2 真实预览截图 + 9 张历史 QA 截图、SHA256、事实边界 | 已准备，临时 HTTP 预览 |
| [视频脚本](competition/demo-video-script.md) | 5–8 分钟普通话真实录屏脚本 | 脚本已准备，最终视频 TODO |
| [最终提交清单](competition/submission-checklist.md) | 仓库、文档、部署、账号、视频和安全检查 | 部分完成；稳定 HTTPS/最终视频/A00 验收待完成 |
| [来源与许可证](competition/licensing.md) | 数据来源、第三方依赖、许可证状态 | 许可证待 A00 决策 |

## 更新规则

1. 先核对代码、命令输出、QA 或部署证据，再修改状态。
2. 新功能必须同时写明实现状态、入口、验证命令和未覆盖范围。
3. 代码行为变化后，更新 `fact-check.md` 和对应专题文档。
4. 容器/CI 结论必须引用固定提交和 Actions run；发布、云部署、TLS、生产恢复必须引用独立证据。
5. 不得在文档中写入真实成员数据、密钥、生产连接串或敏感接入信息。
6. 未完成项保留 `TODO`，不得用占位值、计划或 QA 截图冒充最终完成。
