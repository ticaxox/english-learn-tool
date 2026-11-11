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
| `card-frame-day.png` | 做题卡日间卡框，2:3，中央完全留空 |
| `card-frame-night.png` | 夜间卡框，深紫 + 薄荷藤蔓 + 四角南瓜灯 |
| `card-back.png` | 翻面卡背，深紫 + 发光南瓜脸 |
| `book-object-{day,night}.png` | 词书封面本体（书架上的立起来的那本） |
| `wordbook-cover-{day,night}.png` | 词书封面平面版（旧的用法） |
| `rune-slab.png` + `rune-chip{,-on}.png` | 填空题的石板（9 宫格切片）与选项芯片 |
| `scroll-{cap-left,middle,cap-right}.png` | 卷轴三件套框 |
| `slab-{cap-left,middle,cap-right}.png` | 石板三件套框 |
| `parchment-{cap-left,middle,cap-right}.png` | 羊皮纸三件套框 |

**卡框用法**：整张作为背景（`z-index: 0`），内容用 CSS 排在 `padding: 11% 13% 12%` 的内区。**比例锁死 2:3**，拉伸到其他比例藤蔓会变形。卡面文字必须是真 HTML 文字，不要烘焙进图。

**三件套框**：两端保留画好的细节，中间是一段可以任意拉长的素面。装在 `Frame3.vue` 里，宽面永远不会被拉变形。

### `char/` — 角色与插画

| 文件 | 用途 |
|---|---|
| `crumbo-{day,night}.png` | Crumbo 主角立绘。教练页 NPC、引导页、奖励页 |
| `empty-{day,night}.png` | 空状态插画。Crumbo 趴在空白书页上，四处空状态共用 |
| `result-{day,night}.png` | 练习结算页顶部插画。奖杯 + Crumbo |
| `brewing-{day,night}.png` | Crumbo 在坩埚边，题目生成中 |
| `empty-search-{day,night}.png` | Crumbo 拿放大镜，错题本为空 |

Crumbo 配色取自 `frontend/src/components/CrumboMark.vue`：金身 `#e9b43b`、苔绿叶帽 `#66753a`、可可眼 `#573022`。

### `char/` — 游戏化层（第二期补齐）

这一批是游戏化功能自己的素材，之前只有白天的画；夜版是后来按同一构图重新生成的。

| 文件 | 用途 |
|---|---|
| `pumpkin-morning.png` / `pumpkin-dusk.png` | 关卡节点：已通关的白昼版与黄昏版 |
| `pumpkin-green.png` / `pumpkin-green-night.png` | 当前所在节点。白天苔绿，夜间深紫 + 薄荷刻脸 |
| `pumpkin-unlit.png` / `pumpkin-unlit-night.png` | 未解锁节点。无刻脸、无光 |
| `pumpkin-boss.png` / `pumpkin-boss-night.png` | 最终关。白天金冠，夜间失光银冠 |
| `pumpkin-branch.png` / `pumpkin-branch-night.png` | 分支关。白天藤蔓，夜间薄荷刻脸 |
| `candle-{day,night}.png` | 周报蜡烛。白天奶白蜡 + 橙焰，夜间紫蜡 + 薄荷焰 |
| `charge-{flame,moon,book,crown,skull,star,owl,hourglass,key}.png` | 徽章中心的徽记（AI 绘制，非 emoji）。夜间为 `-night` 版 |
| `card/book-object-{day,night}.png` | 词书封面本体。白天绿皮卡 + 黄铜，夜间紫皮卡 + 薄荷扣 |

关卡节点在 `ChallengeDslMap.vue` 里按 `--pumpkin-lit / --pumpkin-green / --pumpkin-unlit / --pumpkin-boss / --pumpkin-branch` 五个变量切换，随主题整体换图。

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
- 游戏化层这一批（南瓜、蜡烛、徽记、词书封面）的夜间版是同一构图重新生成的，形状大体一致，但与白天版不是逐像素对齐——同一枚徽记在两种主题下的轮廓会有细微差别

## 来源

本目录素材产自 `ai-workspace/10-collaboration/shared-temp/ui-refactor-20261107/`，生成脚本 `gen/run*.sh` 保留在该目录。
