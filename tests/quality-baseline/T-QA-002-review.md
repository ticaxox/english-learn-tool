# T-QA-002｜M3 质量门禁复核

- 复核方：A30 TEST｜质量
- 冻结输入：后端 `2f9c194`、前端 `60ed005`
- 结论：**M3 内部闭环 PASS**；M4/M5 和最终 MVP 不 PASS

## 1. 通过项

- `F-AI-01`：provider CRUD、Key 掩码/密文、真实连接、模型列表、默认/备用切换、元数据 URL 拦截、结构化生成、JSON repair once、额度释放、并发上限、取消和 failover。
- `F-PRACTICE-01`：填空/阅读/翻译/作文四类真实生成与评分、草稿/冲突/重生成、记录/错题/批量删除。
- `F-ANSWER-01`：提交前无答案/解析/参考内容/分数，提交后展示。
- `F-RECORD-01`：记录、错题、结果详情、本人批量删除、跨用户隔离、管理员不可读正文。
- `F-NOTIF-01`：收件箱/游标/未读数/已读/偏好/DND/类别/AI 例外/dedupe/AI 完成失败/live scheduler 三类学习通知。
- `F-AI-CONTRACT-01`：OpenAPI 3.1.0 67 paths / 124 schemas，结构化任务边界与响应摘要通过。
- `F-IDEM-01`：AI job 同键同体、异体冲突、并发上限、取消释放、worker 重启、草稿版本冲突、提交幂等、通知 dedupe。

## 2. 保留条件

- `F-FAIL-01` CONDITIONAL：AI 失败态与无伪造题目/分数已通过；词书/记忆训练的失败态浏览器连续回归待补。
- `F-PRIV-01` CONDITIONAL：M3 练习/通知/额度/provider 隐私已通过；M4 教练正文与完整学习正文域待补。
- `F-MIG-01` CONDITIONAL：当前 M3 全量迁移空库回放与 drift 通过；M4/M5 Schema 待收口。
- `F-E2E-01` CONDITIONAL：M3 浏览器闭环通过；M4/M5 完整旅程、部署和最终 MVP 未完成。

## 3. 验证

- `validate_manifest.py --workspace-root E:\\agent workspace\\英语学习工具`：PASS。
- `--require-final-pass`：预期 FAIL。
- `python -m unittest discover -s tests\\quality-baseline -p "test_*.py"`：5 tests OK。

## 4. 证据

- `ai-workspace/04-qa/evidence/T-QA-002/README.md`
- `results/m3-run8/api-acceptance.json`
- `results/m3-run8/browser-acceptance.json`
- `results/m3-scheduler-run2/scheduler-notifications.json`
- `logs/backend-pytest.log`、`logs/frontend-npm-test.log`、`logs/migration.log`
