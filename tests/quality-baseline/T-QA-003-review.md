# T-QA-003｜M4 独立复审记录

- 日期：2026-10-24 +08:00
- 执行方：A30 TEST｜质量
- 结论：**M4 集成链路 PASS_WITH_CONDITIONS**
- 边界：不关闭 M5、生产部署或最终 MVP；PR 不自行合并。

## 输入与工作树

- 后端冻结：`b6489cdc05e76b534eccd6df6369440a811d6098`
- 前端冻结：`66672a267a939d4c8a600f0e338b61fbd18a404e`
- 基线：`3fb9730a1a3a7fe868fc9ea1d3fb6e8afcf0c4d8`
- 分支：`test/m4-learning-int-003`
- 合并提交：`d728136`（前端）、`0c466ff`（后端）
- 工作树只新增 `tests/m4-learning-int/**` 与测试/证据资产；未修改 backend/app、迁移或 frontend/src 业务实现。

## 真实闭环结果

- API：36/36 checks PASS，179 个请求记录。
- 浏览器：20/20 checks PASS，131 个 API 调用，11 张截图。
- 后端：`152 passed`（真实 PG16 / Redis7）。
- 前端：`306 passed`，`npm run build` PASS。
- 依赖审计：后端 0 已知漏洞；前端 0 漏洞。
- 迁移：空库 upgrade → check（0 drift）→ downgrade base → re-upgrade PASS。

## 覆盖要点

- 教练：会话生命周期、真实 SSE、断线 `Last-Event-ID`、动作回执、撤销、重复撤销幂等、24h 过期、提示词注入、跨用户与管理员隔离、provider 失败、额度耗尽。
- 闯关：今日计划、AI 地图、刷新不重复 AI、3–6 主线、末尾 BOSS、最多 1 支线、新词覆盖、传统学习同步、BOSS 5–10 题、答案防泄露、提交幂等、失败重试、跨日只读。
- 看板：管理员聚合、Core/Small 过滤、最小样本隐私抑制、零成员 API 范围、成员 403、日期范围 422、源事件一致、正文/标题/私有词书零泄露。
- 浏览器：管理员看板、成员教练 SSE/撤销/刷新、地图生成、真实记忆节点、BOSS 提交、刷新完成态、跨日只读。

## 条件与缺口

1. **P2 UI 缺口**：BOSS 提交返回 200 且服务端/历史状态为 `completed`，但提交后父页面重新加载导致结果面板未保留，页面显示 0/5 题已作答。最小复现和页面文本在 `browser-acceptance.json.gaps`。责任方：A20 VIEW｜前端。该项不阻断服务端完成态，但阻断“提交后立即看到结果”的完整体验。
2. **空态口径**：零成员筛选被服务端优先归入隐私抑制，浏览器无法稳定触发独立“当前范围没有可展示数据”空态；API 已验证零成员返回 `total_members=0`。责任方：A20/A10 需确认这是产品预期还是空态不可达。
3. 前端测试夹具原先硬编码 2026-10-23，跨日后导致 2 个 ChallengeView 测试误判为跨日只读；已在 `frontend/src/tests/challenge-view.spec.ts` 改为按 Asia/Shanghai 动态日期，复跑 306/306 PASS。这是测试资产修正，不改变业务实现。

## 门禁映射

| 门禁 | 结论 | 依据 |
|---|---|---|
| F-COACH-01 | PASS | 会话、SSE、刷新与动作回执真实链路 |
| F-COACH-02 | PASS | 动作白名单、撤销、过期与隔离 |
| F-CHAL-01 | PASS | 地图合同、唯一生成、节点、BOSS、历史 |
| F-SHARED-01 | PASS | 记忆节点与传统学习进度同步 |
| F-DASH-01 | PASS | 聚合、筛选、分页、源事件一致 |
| F-PRIV-01 | PASS | 跨用户、管理员、看板正文零泄露 |
| F-IDEM-01 | PASS | 教练消息、撤销、BOSS 提交幂等/冲突 |
| F-FAIL-01 | PASS | provider 失败、额度、重试、跨日失败态 |
| F-MIG-01 | PASS | 空库升级/回滚/再升级/drift 0 |
| F-E2E-01 | CONDITIONAL | BOSS 结果面板缺口与空态口径 |
| F-AI-CONTRACT-01 | CONDITIONAL | M4 只验证 coach_reply/challenge_plan 子集 |

## 结论

M4 的服务端闭环、权限、幂等、隐私、迁移和真实浏览器主链路均通过；因存在一个非阻断的 BOSS 结果 UI 缺口和两个覆盖条件，本任务只给出 **PASS_WITH_CONDITIONS**，不宣称最终 MVP PASS，也不合并 PR。
