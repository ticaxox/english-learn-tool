# 万圣节素材集 · Halloween asset set

昼夜双态位图素材，供 CrumbTrail 前端在 `frontend/src/assets/halloween/**` 下直接引用。

- 生成模型：`gpt-image-2.6-sunburst`（1024×1024 / 1024×1536 / 1536×1024）
- 交付处理：按真实使用尺寸 ×2 DPI 缩放；平涂色量化到 64 色（边缘抗锯齿保留，软化带 0.6%–0.7%）；PNG 透明底
- 体积：源 25.0 MB → 交付 9.2 MB（30 个文件）

## 命名规则

`<类别>-<变体>-<day|night>.png`

`day` 与 `night` 是**同一构图的两次独立生成**，不是滤镜。切换主题时两图交叉淡出，不要用 CSS `filter` 去模拟夜晚。

## 目录

### `book/` — 七种练习入口

真实题型共七种，分两组。每个题型一本书，昼夜各一版。

| 文件 | 题型 | 皮色 | 纹章 |
|---|---|---|---|
| `book-flashcard-{day,night}.png` | 翻卡 FLASHCARD | 暖南瓜橙 | 两张叠放的卡片 |
| `book-choice-{day,night}.png` | 选择 CHOICE | 苔绿 | 三行选项，中间选中 |
| `book-spelling-{day,night}.png` | 拼写 SPELLING | 羊皮浅褐 | 四格字母，一格空着 |
| `book-cloze-{day,night}.png` | 填空 FILL BLANK | 莓红 | 句中缺一格 |
| `book-reading-{day,night}.png` | 阅读 READING | 深青 | 翻开的书页 + 下箭头 |
| `book-translation-{day,night}.png` | 翻译 TRANSLATION | 石板蓝 | A ↔ 汉字块 |
| `book-writing-{day,night}.png` | 作文 WRITING | 可可棕 | 羽毛笔压在横线上 |

书形统一：四道凸起书脊竹节、皮革包角、书口皮带扣、封面凸起内嵌板。白天配件为黄铜，夜间为失光紫银且纹章发光。

> `book-cloze-*` 的文件名沿用生成时的叫法，实际对应产品的 **填空 / fill_blank**。

### `card/` — 做题卡

| 文件 | 用途 |
|---|---|
| `card-frame-day.png` | 做题卡日间卡框，2:3：饼干切口，压花边、扎孔、四角掰掉一块 |
| `card-frame-night.png` | 夜间卡框，2:3：石碑，双层凿槽、上下刻线、四角符文 |
| `card-back.png` | 翻面卡背，深紫 + 发光南瓜脸 |
| `slab-{biscuit,stele}.png` | 记忆练习的大板：选择/拼写题卡的外框 |
| `bar-{biscuit,stele}[-on].png` | 选择题的答案条，`-on` 是选中态（槽里填赭黄颜料） |
| `chip-{biscuit,stele}[-on].png` | 拼写的字母格 |
| `cell-{given,right,wrong}-{biscuit,stele}.png` | 字母格的四种状态：给定 / 正确 / 错误 |
| `sheet-{day,night}.png` | AI 练习的横向卷轴，两端各一根木轴 |
| `sheet-flat-{day,night}.png` | 无轴的撕边纸片：阅读正文、作文题目 |

**两种材质**：白天是**饼干**（烘焙色 `#E8C58A`，压花边、扎孔、掰角），黑夜是**石碑**（深紫 `#3A3254`，凿槽、刻线、符文）。这两套是同一构图的两次独立绘制，不是滤镜。

**卡框用法**：整张作为背景（`z-index: 0`），内容用 CSS 排在 `padding: 11% 13% 12%` 的内区。**比例锁死 2:3**，拉伸到其他比例会变形。卡面文字必须是真 HTML 文字，不要烘焙进图。

**九宫格素材**（`slab-*`、`bar-*`、`chip-*`、`sheet-*`）都是 `border-image` 源：外沿不规则、中间死平。切片值按图上量出来：板 `12%`、条 `8% 4%`、格 `10% 5%`、卷轴 `14% 12%`。

### `char/` — 角色与插画

| 文件 | 用途 |
|---|---|
| `crumbo-{day,night}.png` | Crumbo 主角立绘。教练页 NPC、引导页、奖励页 |
| `empty-{day,night}.png` | 空状态插画。Crumbo 趴在空白书页上，四处空状态共用 |
| `result-{day,night}.png` | 练习结算页顶部插画。奖杯 + Crumbo |

Crumbo 配色取自 `frontend/src/components/CrumboMark.vue`：金身 `#e9b43b`、苔绿叶帽 `#66753a`、可可眼 `#573022`。

### `icon/` — 图标拼版

| 文件 | 内容 |
|---|---|
| `badges-{day,night}.png` | 六枚成就徽章，三列两行：蜡烛 / 书堆 / 南瓜灯 / 皇冠 / 闪电 / 星 |
| `dock-{day,night}.png` | 移动端 dock 四枚，横排等距：今日 / 学习 / 词书 / 设置 |
| `actions-{day,night}.png` | 六枚动作图标，三列两行：关闭 / 刷新 / 编辑 / 删除 / 保存 / 提交 |

**这三张是拼版，不是雪碧图**。它们是设计参照：告诉你每个符号该长什么样、线宽多少、配色怎么落。

实际落地建议**照它们描成 SVG**：

- 拼版没有提供切图坐标，模型每次生成的边距都不一样
- `actions` 这六个动作在源码里出现 40+ 次，每次都加载位图不划算
- 24–28px 下位图会糊

`dock-*` 例外：已缩到 28px 测过仍可辨认，只给移动端底部导航用的话可以直接切图。

### `brand/` — 应用图标

| 文件 | 用途 |
|---|---|
| `appicon.png` | 512×512，无透明、满幅。cookie 脸 + 礼帽 + 卷胡子 |

这是**唯一需要无透明底**的素材。当前 `frontend/index.html` 里没有任何 icon 声明——没有 favicon、没有 apple-touch-icon、没有 theme-color、没有 manifest，标签页是默认白纸。

接入时从这张派生：

```
favicon.ico          32×32 / 48×48
apple-touch-icon.png 180×180
icon-192.png         192×192
icon-512.png         512×512
```

## 接入约定

```vue
<img :src="isNight ? nightSrc : daySrc" alt="" />
```

- 所有素材都是**装饰性**的（`alt=""`）；语义由相邻文字或 `aria-label` 承担
- 切换用**交叉淡出**，时长 520ms，缓动 `cubic-bezier(.2,.9,.25,1.05)`
- 尊重 `prefers-reduced-motion`：该断点下直接切换，不加过渡
- 不要给这些图加 CSS `filter: drop-shadow` 去模拟发光——夜间版本身已经画好了发光

## 已知不足

- `card/card-back.png` 南瓜灯的光晕是柔的，与其余硬边素材不齐。要彻底干净需手绘或描成 SVG
- 夜间版书比白天版略瘦，因为两版是独立生成的。肉眼可辨但不影响使用
- `icon/` 下三张拼版的元素间距每次生成会有差异，不能当雪碧图切

## 来源

本目录素材产自 `ai-workspace/10-collaboration/shared-temp/ui-refactor-20261107/`，生成脚本 `gen/run*.sh` 保留在该目录。
