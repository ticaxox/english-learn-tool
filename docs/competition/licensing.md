# 来源、许可证与素材边界

- 更新：2026-11-18
- 仓库：`ticaxox/english-learn-tool`，当前**公开可见**
- LICENSE：**尚未添加**（GitHub API `license: null`）

## 1. 当前状态

仓库已公开，但没有 LICENSE 文件。公开可见 + 无许可证意味着默认保留所有权利：他人可以阅读，但不能复制、修改或再分发。这对比赛评审通常不构成障碍，但对开源使用是明确缺口。

此前文档里的「仓库为 Private，许可证待 A00 决策」已过期：仓库现在是公开的，决策仍未做。

## 2. 可选的三种处理

| 方案 | 适用 | 影响 |
|---|---|---|
| 保留所有权利（不加 LICENSE） | 只用于比赛展示 | 最保守；评审可读，但不能复用 |
| MIT / Apache-2.0 | 希望被复用或作为作品集 | 允许他人使用与修改；需保留版权声明 |
| 自定义许可 | 有商业计划 | 需明确条款，成本最高 |

无论选哪种，都需要仓库所有者决定；本文档不代替该决策。

## 3. 第三方依赖与素材

- 后端依赖见 `backend/pyproject.toml`（FastAPI、SQLAlchemy、fsrs、ARQ 等），均为开源许可；发布镜像时应保留 SBOM。
- 前端依赖见 `frontend/package.json`；字体许可见 `frontend/src/assets/fonts/OFL-*.txt` 与 `backend/app/assets/fonts/OFL.txt`。
- 万圣节素材为项目自制/AI 生成并在仓库内分发；使用规则见 `frontend/src/assets/halloween/README.md`。
- 演示数据为合成数据，不含真实用户内容。

## 4. 数据与隐私边界

- 仓库不含真实用户数据、生产连接串或 provider Key。
- 本地 `.scratch/db-backup/` 下的历史库转储不属于仓库，也不应随代码或比赛材料分发；其中含可解密 Key 密文与口令哈希。
- 演示账号密码只通过受控渠道交付。

## 5. 待办

1. 决定许可证并添加 `LICENSE`。
2. 在 README 中写明许可证与素材使用范围。
3. 比赛提交前确认评审访问方式与账号交付渠道。
