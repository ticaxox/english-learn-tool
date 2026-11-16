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
| `book-object-{day,night}.png` | 词书封面本体（书架上的立起来的那本） |
| `wordbook-cover-{day,night}.png` | 词书封面平面版（旧的用法） |
| `scroll-{cap-left,middle,cap-right}.png` | 卷轴三件套框 |
| `slab-{cap-left,middle,cap-right}.png` | 石板三件套框 |
| `parchment-{cap-left,middle,cap-right}.png` | 羊皮纸三件套框 |
| `panel-board-{day,night}.png` | 悬浮窗大板：四角铜角/符文夹住撕边，九宫格拉伸 |
| `panel-strip-{day,night}.png` | 决策签条：两端火漆，3.33:1，整张铺底不切 |
| `panel-scrap-{day,night}.png` | 定点碎片：popover / 右键菜单，定尺铺底 |
| `control-button-{day,night}.png` | 凸起的铜牌/石牌：按钮、选中的选项 |
| `control-field-{day,night}.png` | 凹进去的槽：输入框、下拉框、未选中的选项 |
| `control-switch-{off,on}-{day,night}.png` | 开关四态：关/开 × 昼/夜，整张铺底，旋钮画在图里 |
| `control-menu-{day,night}.png` | 下拉菜单面：直边羊皮纸，四角铜片，九宫格 |
| `control-option-on-{day,night}.png` | 菜单里被选中的那一行：琥珀/紫条、双线、左端一颗铜珠 |
| `control-ornament-{day,night}.png` | 花边牌：双线镶边 + 四角小结，无铆钉；选项芯片、模型标签、下拉框共用 |
| `control-badge-{day,night}.png` | 胶囊徽章：两端全圆，给「≈ 1 天」这类小读数 |
| `control-check-{off,on}-{day,night}.png` | 勾选框两态：空框 / 铜底，勾是矢量叠上去的 |
| `control-close-{day,night}.png` | 悬浮窗关闭钮：一枚小方牌，中间的叉仍是矢量图标 |

**悬浮窗的三块板**（`panel-*`）：所有 `[role=dialog]` 都用 `panel-board`——`border-image: url(...) 14% 14% 15% fill round`，边框带 40px，角上留铜角、边条平铺、中间纯平那圈放内容。它不锁比例，34rem 的确认框和 48rem 的详情框共用一张图；框自己不再画圆角、背景和阴影。`panel-scrap` 用 `12% fill stretch`：撕边留在四周切片里，中间随内容伸缩，不再整张拉伸。签条（panel-strip）已废弃——两端火漆在小尺寸下读不出来，确认类浮层改用 `panel-board`。

**控件两件套**（`control-*`）：板子上的零件只有两种状态——按得下去的是凸起的铜牌（按钮、选中的选项），往里放东西的是凹进去的槽（输入框、下拉框、未选中的选项）。两者都是平的、正对着画的，只做横向九宫格：铜牌 `border-image: url(...) 16% 10% fill stretch`、边框 `6px 15px`（铆钉落在左右切片里，按钮多宽都是同一块牌子）；槽 `14% 5% fill stretch`、边框 `6px 10px`。这里用 `stretch` 不用 `round`：控件只有几十像素高，重复的边条会露出接缝。

**开关**（`control-switch-*`）是第三件零件，和前两件不共用一个逻辑：它既不是按下去的，也不是拿来装东西的，而是一颗能在槽里滑到另一头的圆钮。四种状态各一张图，旋钮画在图里，切换时两张图交叉淡出 160ms——不放一个 CSS 假旋钮，也不用滤镜调出另一个状态。四张图都按 2.2:1 交付，框也就定成 2.85rem × 1.3rem；换图不改框，旋钮才不会在切换时变形。

**下拉三件套**（`control-select` / `control-menu` / `control-option`）：下拉框本体、菜单面、菜单里的一行，各画一张。菜单面用九宫格（`8% 14%`，边框 10px），菜单里只有被选中的那一行有框，用 `control-option-on` 整张铺底（行只有三十几像素高，九宫格的角会把左端的铜珠压扁）；没选中的行是干净的一行文字，悬停只变字色。

**两种材质**：白天是**饼干**（烘焙色 `#E8C58A`，压花边、扎孔、掰角），黑夜是**石碑**（深紫 `#3A3254`，凿槽、刻线、符文）。这两套是同一构图的两次独立绘制，不是滤镜。

**卡框用法**：整张作为背景（`z-index: 0`），内容用 CSS 排在 `padding: 11% 13% 12%` 的内区。**比例锁死 2:3**，拉伸到其他比例会变形。卡面文字必须是真 HTML 文字，不要烘焙进图。

**九宫格素材**（`slab-*`、`bar-*`、`chip-*`、`sheet-*`）都是 `border-image` 源：外沿不规则、中间死平。切片值按图上量出来：板 `12%`、条 `8% 4%`、格 `10% 5%`、卷轴 `14% 12%`。

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
