# 演示说明

- 代码基线：`main` @ `1cea3ff` / `v0.1.7`（2026-11-18）
- 演示形态：个人版；一个账号走完「词书 → 记忆 → 练习 → 教练 → 闯关 → 设置」

## 1. 本地演示

```powershell
# 后端
cd backend
uv sync --locked --all-groups
uv run alembic upgrade head
uv run uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload

# 另开终端
uv run arq app.workers.worker.WorkerSettings
uv run arq app.workers.scheduler.SchedulerSettings

# 前端
cd frontend
npm ci
npm run dev
```

访问 `http://127.0.0.1:5173`，注册一个账号即可开始。AI 功能需要先在「设置 → AI 配置」里添加一个 OpenAI 兼容 provider 并测试连接。

## 2. 演示账号

首次环境可以直接注册。若需要预置数据，可用：

```powershell
$env:DEMO_SEED_CONFIRM = 'YES'
$env:DEMO_ADMIN_PASSWORD = '<unique demo admin password>'
$env:DEMO_MEMBER_PASSWORD = '<different unique demo member password>'
uv run --project backend python docs/competition/seed_demo_data.py --apply
```

脚本创建 `demo_admin`、`demo_member`、`demo_member2`、`demo_member3` 四个账号。密码只从环境变量读取，不写入仓库。

> **注意**：脚本原先硬校验迁移 head `844c0d89f737`，已改为 `20261114_0032`；它包含组织版时代的通知、看板等数据，**尚未在当前 schema 上执行验证**。演示前请在一次性数据库上先跑一遍，不要直接打生产库。

## 3. 页面走查（约 6 分钟）

1. **登录 / 注册**：昼夜两版登录页，Hob 在左侧；动作牌按钮。
2. **今日学习** `/overview`：任务环、今日任务、推荐词书、内嵌闯关地图、周报与徽章墙。
3. **词书** `/settings/wordbooks`：启用内置词书或导入自己的 CSV/JSON/TXT，查看导入任务与词条。
4. **记忆训练** `/practice` 顶部书架：翻卡、选择、拼写三种模块，看 FSRS 到期与错词。
5. **AI 练习** `/practice`：六种题型；生成、作答、交卷、评分、记录与错题。
6. **Hob（教练）** `/coach`：多轮对话、流式回复、附件、动作回执与撤销。
7. **设置** `/settings`：学习目标、AI 配置（BYOK、连接测试、额度）、账户与安全、知识库。
8. **昼夜**：侧栏底部开关（手机在个人资料菜单）；切换时素材 520ms 交叉淡出。

## 4. 演示时要讲清的边界

- 所有业务状态以服务端为准：FSRS 调度、判分、队列、额度都不在前端计算。
- AI 任务返回 `202`，界面会显示任务进度；没有 provider 时会明确失败。
- 知识库检索是带出处的小规模实现，适合演示真题引用，不适合宣称海量检索。
- 管理端页面仍存在，但个人版主导航不暴露；演示以成员身份为主。
- 线上预览版本以部署核实为准，不要用旧截图冒充当前界面。

## 5. 失败态

| 场景 | 界面 |
|---|---|
| 没有可用 AI provider | 练习/教练提示配置 provider，任务失败并释放额度 |
| 上游超时 | 任务失败，可重试；额度按失败释放 |
| 知识库为空 | 检索返回空结果，教练明说没有找到出处 |
| 数据库未迁移 | 后端启动失败；Compose 的 `migrate` 服务会先执行迁移 |
